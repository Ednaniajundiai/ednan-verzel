import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _required(name: str, dev_fallback: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    if os.environ.get('NODE_ENV') == 'production':
        raise RuntimeError(f'Variável de ambiente obrigatória ausente: {name}')
    return dev_fallback


@dataclass(frozen=True)
class Config:
    port: int
    database_url: str
    jwt_secret: str
    pseudonym_secret: str
    # Token do link público do comprovante (spec 004, S-07).
    receipt_secret: str
    # PEM PKCS#8 da chave Ed25519. Em dev, gerada e persistida em storage/ (ver audit.py).
    audit_private_key_pem: str | None
    settlement_interval_ms: int
    # Fonte das camisas (D-03 da 002): chave gratuita `123`, ~10 consultas/min.
    thesportsdb_base_url: str
    catalog_ttl_hours: float
    storage_dir: Path
    # Testemunha da trilha fora do banco (spec 004, S-05).
    witness_file: Path
    migrations_dir: Path
    db_pool_max: int


def load_config() -> Config:
    storage_dir = Path(os.environ.get('STORAGE_DIR') or ROOT / 'storage')
    pem = os.environ.get('AUDIT_PRIVATE_KEY_PEM', '').replace('\\n', '\n')
    return Config(
        port=int(os.environ.get('PORT', '3000')),
        database_url=os.environ.get('DATABASE_URL', 'postgres://postgres@localhost:5432/leilao'),
        jwt_secret=_required('JWT_SECRET', 'dev-jwt-secret'),
        pseudonym_secret=_required('PSEUDONYM_SECRET', 'dev-pseudonym-secret'),
        receipt_secret=_required('RECEIPT_SECRET', 'dev-receipt-secret'),
        audit_private_key_pem=pem or None,
        settlement_interval_ms=int(os.environ.get('SETTLEMENT_INTERVAL_MS', '1000')),
        thesportsdb_base_url=os.environ.get('THESPORTSDB_BASE_URL', 'https://www.thesportsdb.com/api/v1/json/123'),
        catalog_ttl_hours=float(os.environ.get('CATALOG_TTL_HOURS', '24')),
        storage_dir=storage_dir,
        witness_file=Path(os.environ.get('WITNESS_FILE') or storage_dir / 'audit-witness.jsonl'),
        migrations_dir=ROOT / 'migrations',
        db_pool_max=int(os.environ.get('DB_POOL_MAX', '20')),
    )
