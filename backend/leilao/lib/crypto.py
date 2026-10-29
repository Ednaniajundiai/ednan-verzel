import asyncio
import hashlib
import hmac
import os

from leilao.lib.jsjson import b64, canonical_json, node_b64decode

__all__ = ['bidder_pseudonym', 'canonical_json', 'hash_password', 'sha256_hex', 'verify_password']

# Parâmetros padrão do `crypto.scrypt` do Node: hashes antigos continuam valendo.
_SCRYPT = {'n': 16384, 'r': 8, 'p': 1, 'dklen': 64, 'maxmem': 32 * 1024 * 1024}


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode('utf-8', 'surrogatepass')).hexdigest()


def bidder_pseudonym(secret: str, user_id: str, lot_id: str) -> str:
    """Pseudônimo do licitante (P5): estável no lote, não correlacionável entre lotes."""
    return hmac.new(secret.encode(), f'{user_id}:{lot_id}'.encode(), hashlib.sha256).hexdigest()[:16]


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode('utf-8', 'surrogatepass'), salt=salt, **_SCRYPT)


async def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = await asyncio.to_thread(_scrypt, password, salt)
    return f'scrypt${b64(salt)}${b64(key)}'


async def verify_password(password: str, stored: str) -> bool:
    parts = stored.split('$')
    scheme, salt_b64, key_b64 = ([*parts, '', '', ''])[:3]
    if scheme != 'scrypt' or not salt_b64 or not key_b64:
        return False
    expected = node_b64decode(key_b64)
    actual = await asyncio.to_thread(_scrypt, password, node_b64decode(salt_b64))
    return len(actual) == len(expected) and hmac.compare_digest(actual, expected)
