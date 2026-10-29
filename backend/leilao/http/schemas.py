"""Schemas das rotas (os `schemas` do `app.ts` do Node), com as mesmas regras e mensagens."""

import re

from leilao.lib import validation as z
from leilao.services.users import ROLES

DEPOSIT_LIMIT = 'O depósito deve ser entre R$ 1,00 e R$ 100.000,00, com até duas casas decimais'


def cents() -> z.Rule:
    return z.number().integer().gt(0).le(1_000_000_000_00)  # até R$ 1 bi


username = (
    z.string()
    .trim()
    .min_length(3)
    .max_length(32)
    .matches(re.compile(r'[A-Za-z0-9_-]+'), 'Use apenas letras, números, _ e -')
)

register = z.Schema(
    'Register',
    username=username,
    password=z.string().min_length(8).max_length(200),
    role=z.enum(ROLES, 'Escolha um papel: leiloeiro (auctioneer) ou licitante (bidder)'),
)
login = z.Schema('Login', username=z.string().trim().min_length(1), password=z.string().min_length(1))
# FR-009 da 004: de R$ 1,00 a R$ 100.000,00 por depósito, em centavos inteiros.
deposit = z.Schema(
    'Deposit',
    amount_cents=z.number(DEPOSIT_LIMIT).integer(DEPOSIT_LIMIT).ge(100, DEPOSIT_LIMIT).le(10_000_000, DEPOSIT_LIMIT),
)
bid = z.Schema('Bid', amount_cents=cents())
idempotency_key = z.string().min_length(1).max_length(100).optional()
catalog_query = z.Schema(
    'CatalogQuery',
    q=z.string().trim().min_length(1, 'Digite o nome de um time').max_length(60, 'Use até 60 caracteres'),
)
team_id = z.string().matches(re.compile(r'[0-9]{1,12}'), 'Time inválido')
uuid = z.uuid()
