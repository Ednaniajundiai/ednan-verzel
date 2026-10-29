"""Compatibilidade cruzada com o backend Node (spec 005, T016 e SC-003).

`fixtures/node-trail.json` foi gravado pelo backend Node antes da remoção: uma trilha assinada,
a linha da testemunha, um hash de senha e um token. O Python precisa (1) aceitar tudo isso e
(2) gravar os mesmos bytes para os mesmos eventos com a mesma chave (Ed25519 é determinístico).
"""

import json

from leilao.http.app import verify_token
from leilao.lib.crypto import canonical_json, verify_password
from leilao.lib.jsjson import js_json_parse
from leilao.services.audit import GENESIS_HASH, AuditSigner, classify_trail, entry_hash, verify_chain
from leilao.services.witness import verify_witness, witness_message
from tests.helpers import FIXTURES

NODE = json.loads((FIXTURES / 'node-trail.json').read_text(encoding='utf-8'))


def test_trilha_gravada_pelo_node_e_integra_no_python() -> None:
    chain = verify_chain(NODE['entries'], NODE['public_key_pem'])
    assert chain == {'valid': True, 'entries': 5, 'headHash': NODE['entries'][-1]['hash']}
    witness = js_json_parse(NODE['witness_line'])
    assert verify_witness(witness, NODE['public_key_pem']) is True
    assert classify_trail(NODE['entries'], NODE['public_key_pem'], witness) == {
        'failure_kind': None,
        'broken_at_seq': None,
        'failure_reason': None,
        'witness_ok': True,
    }


def test_python_grava_os_mesmos_bytes_com_a_mesma_chave() -> None:
    signer = AuditSigner.load(NODE['private_key_pem'], FIXTURES)
    assert signer.public_key_pem == NODE['public_key_pem']
    prev = GENESIS_HASH
    for i, (event, node_entry) in enumerate(zip(NODE['events'], NODE['entries'], strict=True)):
        payload_canonical = canonical_json(event['payload'])
        digest = entry_hash(prev, node_entry['lot_id'], i + 1, event['event_type'], payload_canonical)
        assert payload_canonical == node_entry['payload_canonical']
        assert digest == node_entry['hash']
        assert signer.sign(digest) == node_entry['signature']
        prev = digest
    witness = js_json_parse(NODE['witness_line'])
    assert signer.sign_message(witness_message(witness)) == witness['sig']
    assert json.dumps(witness, separators=(',', ':')) == NODE['witness_line']


async def test_senha_e_token_do_node_continuam_validos() -> None:
    assert await verify_password(NODE['password']['plain'], NODE['password']['hash']) is True
    assert await verify_password('outra-senha', NODE['password']['hash']) is False
    claims = verify_token(NODE['jwt']['secret'], NODE['jwt']['token'])
    assert claims == {'userId': '7d1f0f0e-1b2c-4d3e-9f40-5a6b7c8d9e0f', 'role': 'bidder'}
