"""Verificador independente (RB11): baixa a trilha pública e a chave pública de uma instância e
verifica a cadeia localmente — sem confiar na rota /verify do próprio servidor. Desde a spec 004,
confere também a testemunha assinada (fora do banco), quando ela vem na resposta.

    uv run python -m scripts.verify_audit <lotId> [baseUrl]
"""

import json
import sys

import httpx

from leilao.services.audit import classify_trail, verify_chain
from leilao.services.witness import verify_witness


def main(argv: list[str]) -> int:
    if not argv:
        print('uso: uv run python -m scripts.verify_audit <lotId> [baseUrl]', file=sys.stderr)
        return 2
    lot_id = argv[0]
    base_url = argv[1] if len(argv) > 1 else 'http://localhost:3000'

    with httpx.Client(base_url=base_url, timeout=30) as http:
        public_key = http.get('/audit/public-key').text
        trail = http.get(f'/audit/lots/{lot_id}').json()
        lot = http.get(f'/lots/{lot_id}').json()

    result = verify_chain(trail['entries'], public_key)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result['valid']:
        return 1

    witness = trail.get('witness')
    if witness and not verify_witness(witness, public_key):
        print('testemunha com assinatura inválida: ignorada', file=sys.stderr)
    classification = classify_trail(trail['entries'], public_key, witness)
    if classification['failure_kind']:
        print(
            f'adulterado ({classification["failure_kind"]}) no evento {classification["broken_at_seq"]}: '
            f'{classification["failure_reason"]}',
            file=sys.stderr,
        )
        return 1
    if result['headHash'] != lot['lot']['audit_head_hash']:
        print('cadeia íntegra, mas a cabeça publicada difere — trilha truncada?', file=sys.stderr)
        return 1
    print(
        f'✔ trilha íntegra, assinada pela casa e contém o último elo testemunhado (seq {witness["seq"]})'
        if classification['witness_ok']
        else '✔ trilha íntegra e assinada pela casa (sem testemunha para conferir)'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
