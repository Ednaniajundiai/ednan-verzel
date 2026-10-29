"""Camisas de reserva do seed: usadas quando a TheSportsDB não responde, para a demonstração nunca
subir vazia. A imagem é um SVG simples nas cores do time."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Colors:
    body: str
    sleeve: str
    stripe: str | None = None


@dataclass(frozen=True)
class LocalJersey:
    key: str
    team: str
    league: str
    season: str
    kind: Literal['1st', '2nd']
    colors: Colors


LOCAL_JERSEYS = [
    LocalJersey(
        'flamengo-2019-1st',
        'Flamengo',
        'Brazilian Serie A',
        '2019-2020',
        '1st',
        Colors('#c8102e', '#111111', '#111111'),
    ),
    LocalJersey('palmeiras-2021-1st', 'Palmeiras', 'Brazilian Serie A', '2021', '1st', Colors('#006437', '#ffffff')),
    LocalJersey(
        'corinthians-2012-1st', 'Corinthians', 'Brazilian Serie A', '2012', '1st', Colors('#ffffff', '#111111')
    ),
    LocalJersey(
        'sao-paulo-2005-1st', 'São Paulo', 'Brazilian Serie A', '2005', '1st', Colors('#ffffff', '#ffffff', '#d71920')
    ),
    LocalJersey(
        'santos-2011-2nd', 'Santos', 'Brazilian Serie A', '2011', '2nd', Colors('#111111', '#111111', '#ffffff')
    ),
]


def jersey_svg(j: LocalJersey) -> str:
    c = j.colors
    stripes = (
        ''.join(
            f'<rect x="{x}" y="70" width="18" height="250" fill="{c.stripe}" clip-path="url(#body)"/>'
            for x in (70, 110, 150, 190, 230)
        )
        if c.stripe
        else ''
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 340" role="img" aria-label="Camisa {j.team}">
  <defs><clipPath id="body"><path d="M80 60 L130 40 Q160 60 190 40 L240 60 L240 320 L80 320 Z"/></clipPath></defs>
  <rect width="320" height="340" fill="#eef1f5"/>
  <path d="M80 60 L20 110 L50 160 L80 140 Z" fill="{c.sleeve}" stroke="#333" stroke-width="3"/>
  <path d="M240 60 L300 110 L270 160 L240 140 Z" fill="{c.sleeve}" stroke="#333" stroke-width="3"/>
  <path d="M80 60 L130 40 Q160 60 190 40 L240 60 L240 320 L80 320 Z" fill="{c.body}" stroke="#333" stroke-width="3"/>
  {stripes}
  <path d="M130 40 Q160 75 190 40" fill="none" stroke="#333" stroke-width="4"/>
</svg>'''
