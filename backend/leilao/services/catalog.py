"""Catálogo de camisas, local primeiro (D-03 da 002): responde do banco enquanto a cópia tiver
menos de `ttl_hours`; só então consulta a fonte. Toda camisa exibida fica salva com dados e
imagem (FR-007), e falha da fonte só degrada a busca com um aviso (FR-008, Const. Art. 6)."""

import hashlib
import re
import unicodedata
from typing import TYPE_CHECKING, Any

from leilao.db import Row
from leilao.lib.errors import AppError
from leilao.lib.jsjson import js_collapse_ws, js_trim
from leilao.lib.unicode_diacritic import DIACRITIC_RE
from leilao.services.thesportsdb import Failure, Ok, RateLimited, Unavailable

if TYPE_CHECKING:
    from leilao.services.context import AppContext

KIND_LABELS = {
    '1st': 'Titular',
    '2nd': 'Reserva',
    '3rd': 'Terceira',
    '4th': 'Quarta',
    'gk': 'Goleiro',
    'goalkeeper': 'Goleiro',
}


def kind_label(kind: str | None) -> str | None:
    if not kind:
        return None
    return KIND_LABELS.get(js_trim(kind).lower(), kind)


def normalize_term(raw: str) -> str:
    """Termo de busca: sem espaços nas pontas, minúsculo, espaços simples."""
    term = js_collapse_ws(js_trim(raw)).lower()
    if not term:
        raise AppError('VALIDATION', 'Digite o nome de um time', {'issues': {'q': ['Digite o nome de um time']}})
    return term


def strip_diacritics(s: str) -> str:
    """`s.normalize('NFD').replace(/\\p{Diacritic}/gu, '')`."""
    return DIACRITIC_RE.sub('', unicodedata.normalize('NFD', s))


def _comparable(s: str) -> str:
    return js_collapse_ws(js_trim(strip_diacritics(s))).lower()


def _to_notice(res: Failure) -> dict[str, Any]:
    if isinstance(res, RateLimited):
        return {'code': 'UPSTREAM_RATE_LIMITED', 'retry_after_seconds': res.retry_after_seconds}
    return {'code': 'UPSTREAM_UNAVAILABLE'}


def _js_or_none(v: Any) -> Any:
    """`valor || null` do JavaScript."""
    return v if v not in (None, '', 0, False) else None


# ---------------------------------------------------------------- times


def _to_team(r: Row) -> dict[str, Any]:
    return {
        'id': r['external_id'],
        'name': r['name'],
        'league': r['league'],
        'country': r['country'],
        'badge_url': r['badge_url'],
    }


async def _teams_by_ids(ctx: 'AppContext', ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    res = await ctx.db.query(
        """SELECT t.* FROM unnest($1::text[]) WITH ORDINALITY AS s(id, pos)
       JOIN catalog_teams t ON t.external_id = s.id ORDER BY s.pos""",
        [ids],
    )
    return [_to_team(r) for r in res.rows]


async def _teams_by_name(ctx: 'AppContext', term: str) -> list[dict[str, Any]]:
    """Reserva para termo nunca buscado: times já salvos cujo nome contém o termo."""
    pattern = '%' + re.sub(r'[\\%_]', lambda m: '\\' + m.group(0), term) + '%'
    res = await ctx.db.query('SELECT * FROM catalog_teams WHERE lower(name) LIKE $1 ORDER BY name LIMIT 20', [pattern])
    return [_to_team(r) for r in res.rows]


async def _save_teams(ctx: 'AppContext', term: str, teams: list[dict[str, Any]]) -> None:
    for t in teams:
        await ctx.db.query(
            """INSERT INTO catalog_teams (external_id, name, league, country, badge_url, fetched_at)
       VALUES ($1, $2, $3, $4, $5, now())
       ON CONFLICT (external_id) DO UPDATE SET
         name = EXCLUDED.name, league = EXCLUDED.league, country = EXCLUDED.country,
         badge_url = EXCLUDED.badge_url, fetched_at = now()""",
            [
                t['idTeam'],
                t['strTeam'],
                _js_or_none(t.get('strLeague')),
                _js_or_none(t.get('strCountry')),
                _js_or_none(t.get('strBadge')),
            ],
        )
    await ctx.db.query(
        """INSERT INTO catalog_team_searches (term_normalized, team_external_ids, fetched_at) VALUES ($1, $2, now())
     ON CONFLICT (term_normalized) DO UPDATE SET team_external_ids = EXCLUDED.team_external_ids, fetched_at = now()""",
        [term, [t['idTeam'] for t in teams]],
    )


async def search_teams(ctx: 'AppContext', raw_term: str) -> dict[str, Any]:
    term = normalize_term(raw_term)
    cached = await ctx.db.query(
        """SELECT team_external_ids AS ids, fetched_at > now() - $2 * interval '1 hour' AS fresh
       FROM catalog_team_searches WHERE term_normalized = $1""",
        [term, ctx.catalog.ttl_hours],
    )
    hit = cached.rows[0] if cached.rows else None

    source = 'cache'
    notice: dict[str, Any] | None = None
    if hit and hit['fresh']:
        teams = await _teams_by_ids(ctx, hit['ids'])
    else:
        res = await ctx.catalog.client.search_teams(term)
        if isinstance(res, Ok):
            await _save_teams(ctx, term, res.data)
            teams = await _teams_by_ids(ctx, [t['idTeam'] for t in res.data])
            source = 'live'
        else:
            notice = _to_notice(res)
            teams = await _teams_by_ids(ctx, hit['ids']) if hit else await _teams_by_name(ctx, term)

    # Abertura direta (cenário 2.1 da 002): um único time, ou um de nome exatamente igual ao termo.
    if len(teams) == 1:
        selected: dict[str, Any] | None = teams[0]
    else:
        selected = next((t for t in teams if _comparable(t['name']) == _comparable(term)), None)
    jerseys: list[dict[str, Any]] | None = None
    if selected:
        listed = await list_jerseys(ctx, selected['id'])
        jerseys = listed['jerseys']
        if not notice and listed.get('notice'):
            notice = listed['notice']
            source = 'cache'
    out: dict[str, Any] = {'source': source}
    if notice:
        out['notice'] = notice
    out.update({'teams': teams, 'selected_team_id': selected['id'] if selected else None, 'jerseys': jerseys})
    return out


# ---------------------------------------------------------------- camisas

JERSEY_SELECT = """SELECT i.id, i.team_external_id, t.name AS team_name, t.league, i.season, i.kind, i.title,
       i.image_path, i.image_source_url
  FROM items i LEFT JOIN catalog_teams t ON t.external_id = i.team_external_id"""


def to_jersey(r: Row) -> dict[str, Any]:
    return {
        'id': r['id'],
        'team_id': r['team_external_id'],
        'team_name': r['team_name'],
        'league': r['league'],
        'season': r['season'],
        'kind': r['kind'],
        'kind_label': kind_label(r['kind']),
        'title': r['title'],
        'image_url': f'/images/{r["image_path"]}' if r['image_path'] else None,
        'image_status': 'saved' if r['image_path'] else 'image_pending' if r['image_source_url'] else 'no_image',
    }


async def _jerseys_of_team(ctx: 'AppContext', team_id: str) -> list[dict[str, Any]]:
    res = await ctx.db.query(
        f"""{JERSEY_SELECT} WHERE i.team_external_id = $1
      ORDER BY i.season DESC NULLS LAST, i.kind NULLS LAST, i.external_id""",
        [team_id],
    )
    return [to_jersey(r) for r in res.rows]


def _trim_or_none(v: Any) -> str | None:
    """`e.campo?.trim() || null`."""
    return js_trim(v) or None if isinstance(v, str) else None


def _jersey_title(team: str, e: dict[str, Any]) -> str:
    label = kind_label(e.get('strType'))
    season = js_trim(e['strSeason']) if isinstance(e.get('strSeason'), str) else None
    return ' '.join(p for p in ['Camisa', team, season, label.lower() if label else None] if p)


async def list_jerseys(ctx: 'AppContext', team_id: str) -> dict[str, Any]:
    res = await ctx.db.query(
        "SELECT *, jerseys_fetched_at > now() - $2 * interval '1 hour' AS fresh FROM catalog_teams WHERE external_id = $1",
        [team_id, ctx.catalog.ttl_hours],
    )
    if not res.rows:
        raise AppError('NOT_FOUND', 'Time não encontrado. Busque o time pelo nome primeiro.')
    team_row = res.rows[0]
    team = _to_team(team_row)
    if team_row['fresh']:
        return {'source': 'cache', 'team': team, 'jerseys': await _jerseys_of_team(ctx, team_id)}

    found = await ctx.catalog.client.lookup_equipment(team_id)
    if not isinstance(found, Ok):
        return {
            'source': 'cache',
            'notice': _to_notice(found),
            'team': team,
            'jerseys': await _jerseys_of_team(ctx, team_id),
        }

    for e in found.data:
        image_url = _trim_or_none(e.get('strEquipment'))
        await ctx.db.query(
            """INSERT INTO items (external_id, source, title, description, image_source_url, team_external_id, season, kind, fetched_at)
       VALUES ($1, 'thesportsdb', $2, '', $3, $4, $5, $6, now())
       ON CONFLICT (external_id) DO UPDATE SET
         title = EXCLUDED.title,
         -- Imagem nova na fonte: a cópia antiga deixa de valer para o catálogo (lotes têm a própria).
         image_path = CASE WHEN items.image_source_url IS NOT DISTINCT FROM EXCLUDED.image_source_url
                           THEN items.image_path END,
         image_source_url = EXCLUDED.image_source_url,
         team_external_id = EXCLUDED.team_external_id,
         season = EXCLUDED.season,
         kind = EXCLUDED.kind,
         fetched_at = now()""",
            [
                f'tsdb-equipment:{e["idEquipment"]}',
                _jersey_title(team['name'], e),
                image_url,
                team_id,
                _trim_or_none(e.get('strSeason')),
                _trim_or_none(e.get('strType')),
            ],
        )
    await ctx.db.query('UPDATE catalog_teams SET jerseys_fetched_at = now() WHERE external_id = $1', [team_id])

    # Imagens baixadas na hora (FR-007). Limite da fonte: para e deixa o resto pendente.
    pending = await ctx.db.query(
        """SELECT id, image_source_url FROM items
      WHERE team_external_id = $1 AND image_path IS NULL AND image_source_url IS NOT NULL ORDER BY external_id""",
        [team_id],
    )
    for item in pending.rows:
        result = await _download_image(ctx, item['id'], item['image_source_url'])
        if isinstance(result, RateLimited):
            break
    return {'source': 'live', 'team': team, 'jerseys': await _jerseys_of_team(ctx, team_id)}


async def list_saved_jerseys(ctx: 'AppContext') -> dict[str, Any]:
    """Camisas com imagem já salva: dá para criar lote com a fonte fora do ar (SC-001 da 002)."""
    res = await ctx.db.query(
        f"""{JERSEY_SELECT} WHERE i.image_path IS NOT NULL
      ORDER BY i.fetched_at DESC NULLS LAST, i.created_at DESC, i.external_id LIMIT 200"""
    )
    return {'jerseys': [to_jersey(r) for r in res.rows]}


# ---------------------------------------------------------------- imagens

EXTENSIONS = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
}


async def _download_image(ctx: 'AppContext', item_id: str, url: str) -> Ok[str] | Failure:
    res = await ctx.catalog.client.fetch_image(url)
    if not isinstance(res, Ok):
        return res
    ext = EXTENSIONS.get(res.data.content_type)
    if not ext:
        return Unavailable(f'tipo de imagem não aceito ({res.data.content_type})')
    # Nome pelo conteúdo: a mesma imagem não duplica arquivos e nunca é sobrescrita por outra.
    name = f'{hashlib.sha256(res.data.body).hexdigest()}.{ext}'
    directory = ctx.catalog.storage_dir / 'images'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(res.data.body)
    await ctx.db.query('UPDATE items SET image_path = $2 WHERE id = $1', [item_id, name])
    return Ok(name)


async def ensure_image(ctx: 'AppContext', item_id: str) -> None:
    """Antes de criar um lote (FR-013 da 002): garante a imagem local da camisa, tentando baixar
    uma pendente. Chamado fora da transação do lote."""
    res = await ctx.db.query('SELECT image_path, image_source_url FROM items WHERE id = $1', [item_id])
    if not res.rows:
        raise AppError('NOT_FOUND', 'Camisa não encontrada')
    item = res.rows[0]
    if item['image_path']:
        return
    if not item['image_source_url']:
        raise AppError('ITEM_WITHOUT_IMAGE', 'Esta camisa não tem imagem na fonte e não pode virar lote')
    downloaded = await _download_image(ctx, item_id, item['image_source_url'])
    if not isinstance(downloaded, Ok):
        raise AppError(
            'IMAGE_UNAVAILABLE',
            'A imagem desta camisa está indisponível agora. Tente de novo em instantes.',
            {'retry_after_seconds': downloaded.retry_after_seconds} if isinstance(downloaded, RateLimited) else None,
        )
