"""Gera a chave Ed25519 da auditoria no formato esperado por AUDIT_PRIVATE_KEY_PEM
(`uv run python -m scripts.keygen`)."""

import sys

from leilao.services.audit import AuditSigner


def main() -> None:
    signer = AuditSigner.ephemeral()
    pem = signer.private_key_pem().strip().replace('\n', '\\n')
    print(f'AUDIT_PRIVATE_KEY_PEM="{pem}"')
    print('\nChave pública (publique para auditores):\n' + signer.public_key_pem, file=sys.stderr)


if __name__ == '__main__':
    main()
