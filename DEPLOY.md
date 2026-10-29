# Deploy em VPS (Dokploy + Docker Compose)

Usa o `docker-compose.prod.yml`: dois serviços (`leilao-api` e `leilao-web`), sem porta
publicada no host e **sem Postgres próprio**: o banco é o Postgres criado no Dokploy, acessado
pela URL interna. O Traefik do Dokploy recebe o domínio, termina o HTTPS e fala com o
`leilao-web` na porta 80. O `leilao-web` (nginx) serve a SPA e repassa `/api`, `/socket.io` e
`/images` para a `leilao-api`. Os dois serviços entram na rede `dokploy-network` (a mesma do
Traefik e do banco), por isso têm nomes próprios, que não colidem com os de outros apps.

## 1. Banco

No Dokploy, crie (ou use) um serviço **Postgres** vazio. Na aba dele, copie a **Internal
Connection URL**, no formato:

```
postgresql://USUARIO:SENHA@NOME-INTERNO-DO-BANCO:5432/BANCO
```

Ela vai na variável `DATABASE_URL` (passo 3). A API cria as tabelas sozinha na subida.

## 2. Segredos

Gere um valor diferente para cada um (`openssl rand -hex 32`):
`JWT_SECRET`, `PSEUDONYM_SECRET`, `RECEIPT_SECRET`. Escolha também o `ADMIN_USERNAME`
(ex.: `admin_ednan`) e a `ADMIN_PASSWORD` (mín. 8 caracteres).

Chave de assinatura da auditoria (recomendado):

```bash
uv run --directory backend python -m scripts.keygen
```

Ele imprime a linha `AUDIT_PRIVATE_KEY_PEM="..."`; cole-a inteira. Se ficar vazia, a API gera
uma chave e a guarda no volume `storage`. Funciona, mas a chave passa a morar ao lado da
testemunha da trilha.

**Troque os segredos só antes do primeiro uso.** `PSEUDONYM_SECRET` e `RECEIPT_SECRET` mudam
os pseudônimos dos licitantes e os links de comprovante já emitidos. Trocar a chave de
auditoria invalida a verificação de lotes antigos.

## 3. Criar o serviço no Dokploy

1. Projeto `animusdev` → ambiente `production` → **Create Service** → **Compose**.
2. **Provider:** Git, repositório
   `https://github.com/Ednaniajundiai/ednan-verzel.git`, branch `main`.
3. **Compose Path:** `./docker-compose.prod.yml`. **Compose Type:** Docker Compose.
4. Aba **Environment**: cole as variáveis do `.env.example` com os valores reais
   (`DATABASE_URL`, `JWT_SECRET`, `PSEUDONYM_SECRET`, `RECEIPT_SECRET`, `ADMIN_USERNAME`,
   `ADMIN_PASSWORD` e, se gerou, `AUDIT_PRIVATE_KEY_PEM`).
5. Aba **Domains** → adicione o domínio:
   - Service Name: `leilao-web`
   - Port: `80`
   - HTTPS ligado, Certificate: Let's Encrypt
   - O DNS do domínio (registro A) precisa apontar para o IP da VPS.
6. **Deploy.**

O WebSocket (`/socket.io`) passa pelo Traefik sem configuração extra.

## 4. Conferir

Nos logs da `leilao-api`:

```
[migrate] ok
[admin] conta criada: <ADMIN_USERNAME> (leiloeiro)
[api] ouvindo em http://localhost:3000
```

```bash
curl -s https://SEU_DOMINIO/api/lots | head -c 200      # {"server_now":...,"lots":[]}
curl -s https://SEU_DOMINIO/api/audit/public-key        # chave pública da auditoria
```

Abra `https://SEU_DOMINIO` e entre com o `ADMIN_USERNAME` e a `ADMIN_PASSWORD`. O banco nasce
**sem contas e sem lotes de demonstração**: a API só migra o schema e cria a conta do admin,
que é leiloeira. O login é por usuário (não por e-mail) e não diferencia maiúsculas. Os
licitantes se cadastram em `/cadastro`; o admin cria os lotes no painel, buscando as camisas na
TheSportsDB (sem camisas locais de reserva).

## 5. Se algo falhar

| Sintoma | Causa provável |
|---|---|
| Deploy falha com "defina X" | Variável faltando na aba Environment |
| `leilao-api` reinicia; log com erro de conexão | `DATABASE_URL` com host, usuário, senha ou banco errados; ou a API fora da `dokploy-network` |
| 404 / Bad Gateway no domínio | Service Name diferente de `leilao-web` ou porta diferente de `80` |
| Certificado não emitido | DNS ainda não propagou, ou portas 80 e 443 fechadas na VPS |
| Busca de camisas vazia | A TheSportsDB pode estar limitando as consultas; tente de novo em alguns minutos |

## 6. Operação

- **Atualizar:** `git push` na `main` e **Deploy** no Dokploy (ou ligue o auto deploy por
  webhook). A API migra o banco sozinha na subida.
- **Dados:** o banco fica no Postgres do Dokploy (use os backups dele); o volume `storage`
  guarda imagens, a testemunha da trilha e, se não houver `AUDIT_PRIVATE_KEY_PEM`, a chave.
  Faça backup dos dois.
- **Logs:** aba Logs do Dokploy, por serviço.
