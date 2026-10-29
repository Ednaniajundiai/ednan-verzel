"""Login e cadastro por nome de usuário (spec 005, troca do e-mail): unicidade sem diferenciar
maiúsculas, formato do usuário, mensagem única de credencial inválida e criação do admin."""

import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from leilao.http import schemas
from leilao.lib.errors import AppError
from leilao.services.context import AppContext
from leilao.services.users import authenticate
from tests.helpers import TEST_DB, Api, reset_db, running_server

JWT = 'test-jwt-username'
SENHA = 'senha-forte-123'


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    async with running_server(ctx, JWT) as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


def novo(username: str, role: str = 'bidder') -> dict[str, str]:
    return {'username': username, 'password': SENHA, 'role': role}


async def test_cadastra_e_entra_pelo_usuario_sem_diferenciar_maiusculas(api: Api) -> None:
    nome = f'Ana_{secrets.token_hex(3)}'
    status, reg = await api('POST', '/auth/register', novo(nome))
    assert status == 201
    assert reg['user']['username'] == nome and 'email' not in reg['user']
    status, login = await api('POST', '/auth/login', {'username': nome.upper(), 'password': SENHA})
    assert status == 200 and login['user']['id'] == reg['user']['id']


async def test_usuario_repetido_ignora_maiusculas(api: Api) -> None:
    assert (await api('POST', '/auth/register', novo('Bruno-1')))[0] == 201
    status, body = await api('POST', '/auth/register', novo('bruno-1'))
    assert status == 409 and body['error']['message'] == 'Usuário já cadastrado'


async def test_credencial_invalida_tem_uma_so_mensagem(api: Api) -> None:
    await api('POST', '/auth/register', novo('carla'))
    errada = await api('POST', '/auth/login', {'username': 'carla', 'password': 'errada-errada'})
    inexistente = await api('POST', '/auth/login', {'username': 'ninguem', 'password': SENHA})
    assert errada[0] == inexistente[0] == 401
    assert errada[1] == inexistente[1]


@pytest.mark.parametrize('username', ['ab', 'a' * 33, 'com espaco', 'com@arroba', 'acentuação', ''])
async def test_usuario_com_formato_invalido_e_recusado(api: Api, username: str) -> None:
    assert (await api('POST', '/auth/register', novo(username)))[0] == 400


def test_schema_remove_espacos_das_pontas() -> None:
    assert schemas.register.parse(novo('  dora  '))['username'] == 'dora'


async def test_create_admin_cria_uma_vez_e_nao_troca_a_senha(
    ctx: AppContext, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import create_admin

    monkeypatch.setenv('ADMIN_USERNAME', 'admin_ednan')
    monkeypatch.setenv('ADMIN_PASSWORD', 'primeira-senha')
    monkeypatch.setenv('DATABASE_URL', TEST_DB)
    assert await create_admin.main() == 0
    monkeypatch.setenv('ADMIN_PASSWORD', 'outra-senha-xx')
    assert await create_admin.main() == 0
    assert 'já existe' in capsys.readouterr().out

    user = await authenticate(ctx.db, 'ADMIN_ednan', 'primeira-senha')
    assert user['role'] == 'auctioneer'
    with pytest.raises(AppError):
        await authenticate(ctx.db, 'admin_ednan', 'outra-senha-xx')


async def test_create_admin_sem_senha_nao_cria_conta(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import create_admin

    monkeypatch.setenv('ADMIN_USERNAME', 'admin_ednan')
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    assert await create_admin.main() == 1
