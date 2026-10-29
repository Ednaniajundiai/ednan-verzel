# Casa de Leilões — camisas de futebol ao vivo

Para o desafio do Elite Dev, escolhi fazer um leilão ao vivo de camisas de futebol. As camisas
vêm da API pública [TheSportsDB](https://www.thesportsdb.com/). O foco do projeto é a
correção quando muitos lances chegam ao mesmo tempo, a integridade do dinheiro e uma auditoria
que qualquer pessoa pode verificar.

O que cada papel faz:

- **Leiloeiro:** busca camisas na TheSportsDB, cria lotes, cancela lotes sem lances e vê o
  resultado de cada lote encerrado e o total recebido.
- **Licitante:** deposita saldo simulado, dá lances numa sala ao vivo, acompanha os seus
  arremates e recebe um comprovante com link público.
- **Qualquer pessoa, sem login:** audita um lote e vê o histórico completo, se ele está
  íntegro ou foi adulterado, e pode refazer a verificação no próprio navegador.

O uso de IA no projeto está descrito em [USO_DE_IA.md](USO_DE_IA.md).
Deploy realizei na minha propria VPS usando o [Docker Compose](https://docs.docker.com/compose/) e utilizando o [Nginx](https://www.nginx.com/) para servir a aplicação. O domínio utilizado foi https://ednan-verzel.animusdev.com.br/.

---

## Sumário

1. [Acesso rápido](#acesso-rápido)
2. [Stack](#stack)
3. [Rodar com Docker Compose](#rodar-com-docker-compose)
4. [Rodar sem Docker](#rodar-sem-docker)
5. [Variáveis de ambiente](#variáveis-de-ambiente)
6. [Roteiro de avaliação](#roteiro-de-avaliação)
7. [Regras de lance e saldo](#regras-de-lance-e-saldo)
8. [Resiliência à API externa](#resiliência-à-api-externa)
9. [Auditoria à prova de adulteração](#auditoria-à-prova-de-adulteração)
10. [Privacidade](#privacidade)
11. [Opcionais entregues](#opcionais-entregues)
12. [Testes](#testes)
13. [API](#api)
14. [Comportamentos inesperados e limitações](#comportamentos-inesperados-e-limitações)

---

## Acesso rápido

O login é por **nome de usuário** (não por e-mail) e não diferencia maiúsculas.

| Papel | Usuário | Senha | Observação |
|---|---|---|---|
| Leiloeiro | `daniel_castello` | `demo-verzel` | dono dos lotes semeados |
| Leiloeiro | `filipe_carvalho` | `demo-verzel` | sem lotes, para criar um do zero |
| Licitante | `heloisa_barcala` | `demo-verzel` | R$ 5.000,00 de saldo inicial |
| Licitante | `luiz_spinelli` | `demo-verzel` | R$ 5.000,00 de saldo inicial |
| Licitante | `alan_franzin` | `demo-verzel` | R$ 5.000,00 de saldo inicial, sem lances |

### Lotes semeados (todos do Daniel)

| Lote | Estado na subida |
|---|---|
| Ao vivo com 3 lances (Heloisa R$ 150 → Luiz R$ 170 → Heloisa R$ 190) | encerra em 30 min |
| Ao vivo sem lances | encerra em 5 min: um lance nos últimos 2 min mostra a prorrogação |
| Agendado | começa em 10 min e passa a "ao vivo" sozinho |
| Encerrado e arrematado pelo Luiz (R$ 250) | tem comprovante |
| Encerrado sem vencedor | — |

Os horários são **relativos ao momento do seed**. Se os lotes ao vivo já tiverem encerrado
quando você abrir a aplicação, entre como `filipe_carvalho` (ou `daniel_castello`), clique em
**Novo lote** e publique um lote que comece agora. Leva menos de um minuto.

Se a TheSportsDB não responder durante o seed (fora do ar, limite de consultas ou rede
bloqueada), o seed usa **camisas locais de reserva** e a demonstração sobe completa do mesmo
jeito.

## Stack

| Camada | Tecnologia | Por quê |
|---|---|---|
| Front-End | React 18 + Vite + React Router | SPA leve, build rápido, sem servidor de front |
| Back-End | Python 3.12 + FastAPI (uv) | validação forte com Pydantic, código assíncrono simples |
| Tempo real | python-socketio / socket.io-client | lances, prorrogação e saldo chegam sem recarregar |
| Banco | PostgreSQL 16 (psycopg 3) | transações e `SELECT ... FOR UPDATE` para lances concorrentes |
| Infra | Docker Compose + nginx | sobe tudo com um comando; nginx serve a SPA e repassa a API |

## Rodar com Docker Compose

Pré-requisito: Docker Desktop (ou Docker Engine + Compose v2).

```bash
git clone https://github.com/Ednaniajundiai/ednan-verzel.git
cd ednan-verzel
docker compose up --build
```

Abra **http://localhost:8080**. O nginx serve a SPA e repassa `/api` (sem o prefixo),
`/socket.io` e `/images` para a API, que também responde direto em http://localhost:3000.

O compose sobe três serviços: `db` (PostgreSQL 16), `api` e `nginx`. O banco já é criado
pelo próprio container; não há nada para configurar. Na subida, a API:

1. aplica as migrações (`backend/migrations/*.sql`);
2. roda o seed (`SEED_ON_START=true` no compose). Na primeira vez ele cria as contas e os
   lotes; nas seguintes, só garante as contas;
3. sobe a API na porta 3000.

Para recomeçar do zero (banco, imagens e testemunha da auditoria):

```bash
docker compose down -v
```

## Rodar sem Docker

### Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 se precisar)
- Node 22 e npm (só para o front)
- PostgreSQL 16 rodando e acessível

### 1. Banco de dados (PostgreSQL)

Crie dois bancos: um para a aplicação e outro para os testes.

```bash
createdb -U postgres leilao
createdb -U postgres leilao_test
```

Ou pelo `psql`:

```sql
CREATE DATABASE leilao;
CREATE DATABASE leilao_test;
```

A API lê a conexão da variável `DATABASE_URL`, no formato
`postgres://USUARIO:SENHA@HOST:PORTA/BANCO`. O padrão, se ela não for definida, é
`postgres://postgres@localhost:5432/leilao`. As tabelas são criadas pelas migrações, que rodam
no seed e na subida do container; não há SQL para executar à mão.

### 2. Back-End

```bash
cd backend
uv sync                                                    # cria .venv com as dependências
export DATABASE_URL=postgres://postgres:postgres@localhost:5432/leilao
uv run python -m scripts.seed                              # migra e popula
uv run python -m leilao.server                             # API em http://localhost:3000
```

No PowerShell, troque o `export` por `$env:DATABASE_URL = "postgres://..."`.

Outros scripts:

| Comando | Faz |
|---|---|
| `uv run python -m scripts.migrate` | só aplica as migrações |
| `uv run python -m scripts.keygen` | gera a chave Ed25519 da auditoria |
| `uv run python -m scripts.verify_audit <lotId> [url]` | verifica a trilha de um lote fora do site |
| `uv run python -m scripts.create_admin` | cria uma conta de leiloeiro a partir de `ADMIN_USERNAME`/`ADMIN_PASSWORD` |
| `uv run python -m scripts.gen_tamper_fixtures` | regenera os casos de adulteração usados nos testes |

### 3. Front-End

Em outro terminal:

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173
```

O Vite repassa `/api`, `/socket.io` e `/images` para a porta 3000.

Fora de produção (`NODE_ENV` diferente de `production`), os segredos têm valores de
desenvolvimento e a chave da auditoria é gerada uma vez em `backend/storage/`.

## Variáveis de ambiente

Modelo em [.env.example](.env.example). O `docker-compose.yml` já traz valores próprios para
avaliação local.

| Variável | Padrão | Uso |
|---|---|---|
| `NODE_ENV` | — | `production` torna obrigatórios os três segredos abaixo (nome herdado do backend Node) |
| `DATABASE_URL` | `postgres://postgres@localhost:5432/leilao` | conexão com o PostgreSQL |
| `JWT_SECRET` | obrigatório em produção | assina o token de login |
| `PSEUDONYM_SECRET` | obrigatório em produção | gera o pseudônimo do licitante na auditoria e no comprovante |
| `RECEIPT_SECRET` | obrigatório em produção | gera o token do link público do comprovante |
| `AUDIT_PRIVATE_KEY_PEM` | gerada em `storage/` | chave Ed25519 que assina a trilha de auditoria |
| `WITNESS_FILE` | `storage/audit-witness.jsonl` | testemunha da trilha, fora do banco |
| `STORAGE_DIR` | `backend/storage` | imagens das camisas, testemunha e, sem a variável acima, a chave |
| `THESPORTSDB_BASE_URL` | `https://www.thesportsdb.com/api/v1/json/123` | fonte das camisas |
| `CATALOG_TTL_HOURS` | `24` | idade máxima da cópia local antes de consultar a fonte de novo |
| `SETTLEMENT_INTERVAL_MS` | `1000` | intervalo do job que encerra e liquida os lotes |
| `SEED_ON_START` | `true` no compose | roda o seed na subida do container |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | — | opcional: cria uma conta de leiloeiro na subida (senha com 8+ caracteres) |

Defina `PSEUDONYM_SECRET`, `RECEIPT_SECRET` e `AUDIT_PRIVATE_KEY_PEM` **antes do primeiro
uso** e não os troque depois: os pseudônimos mudam, os links de comprovante já enviados param
de abrir e as trilhas antigas deixam de passar na verificação.

## Roteiro de avaliação

Cerca de 10 minutos. Use duas janelas: uma normal e uma anônima.

1. **Vitrine** (`/`): seções Ao vivo, Agendados e Encerrados, com busca (ignora acentos) e
   filtro por estado. Lotes cancelados não aparecem.
2. **Sala ao vivo com dois licitantes:** `heloisa_barcala` numa janela e `luiz_spinelli` na
   outra, as duas no lote "ao vivo com 3 lances". O Luiz dá um lance: em menos de 1 s a outra
   janela vê o lance, troca "Você está ganhando" por "Você foi superado" e mostra a posição
   ("2º de 2 licitantes"). A contagem regressiva e o histórico atualizam sozinhos.
3. **Lances recusados:** tente cada caso e veja a mensagem junto ao campo, sem apagar o valor:
   abaixo do mínimo, saldo insuficiente, você já está ganhando, lote ainda não iniciado (no
   lote agendado) e lote encerrado.
4. **Anti-sniping:** no lote que encerra em 5 min, dê um lance com menos de 2 min no relógio.
   A contagem salta nas duas janelas e aparece "Lote prorrogado".
5. **Carteira** (`/carteira`): saldo total, comprometido (com os lotes que o compõem) e
   disponível, atualizados ao vivo; depósito simulado de R$ 1,00 a R$ 100.000,00.
6. **Meus arremates** (`/arremates`, como `luiz_spinelli`): lotes em que deu lance e o lote
   vencido, com "Ver comprovante" e "Copiar link". Abra o link numa janela anônima: comprovante
   completo, sem dado pessoal, e "Auditar este lote" a um clique.
7. **Painel do leiloeiro** (`/painel`, como `daniel_castello`): resultado de cada lote
   encerrado (arrematado ou não, e por quanto) e total recebido. Cancele um lote sem lances:
   ele some da vitrine na hora. Em **Novo lote**, busque um time ("Flamengo"), escolha a
   camisa, defina lance inicial, incremento, início e fim, e publique.
8. **Auditoria** (`/auditoria/<lote>`, sem login): siga o
   [roteiro de adulteração](#reproduza-a-detecção-cerca-de-5-min) e veja cada caso detectado
   na página e no botão "Verificar no meu navegador".
9. **Tema:** botão no topo alterna claro e escuro; a primeira visita segue o tema do sistema.

## Regras de lance e saldo

| Regra | Como funciona |
|---|---|
| Janela do lance | só é aceito entre o início e o fim do lote, pelo **relógio do banco**, lido depois do lock |
| Valor mínimo | o 1º lance deve ser ≥ lance inicial; os seguintes, ≥ lance atual + incremento mínimo |
| Líder não cobre o próprio lance | recusado com "Você já está ganhando este lote" |
| Papéis | leiloeiro não dá lance nem deposita; licitante não cria nem cancela lote |
| Saldo comprometido | não é armazenado: é a soma do preço atual dos lotes abertos que o licitante lidera. Ser superado libera o valor na hora |
| Saldo disponível | total − comprometido. O lance só é aceito se couber no disponível |
| Anti-sniping | lance aceito nos últimos 2 min estende o fim para 2 min depois do lance |
| Liquidação | ao encerrar, debita o vencedor e credita o leiloeiro na mesma transação e gera o comprovante. Lote sem lances fecha sem vencedor |
| Cancelamento | só para lote que ainda não recebeu lances e não encerrou |

**Concorrência.** Cada lance é uma transação: papel do usuário → `lots FOR UPDATE` → relógio
do banco → recusas na ordem acima → `wallets FOR UPDATE` → grava o lance → prorroga se
faltam ≤ 2 min. A ordem fixa dos locks (lote → carteira) elimina deadlocks. Lances repetidos
com o mesmo `Idempotency-Key` devolvem o lance original.

**Encerramento.** Um job a cada 1 s usa `FOR UPDATE SKIP LOCKED`, e qualquer leitura do lote
já o liquida se o fim passou. A idempotência vem do lock, da transição de status e de um
`UNIQUE(lot_id, kind)` no livro-razão: o vencedor nunca é debitado duas vezes.

## Resiliência à API externa

A TheSportsDB é consultada **só pelo painel do leiloeiro**, na hora de buscar camisas. Todo o
resto funciona sem ela.

- **Catálogo local primeiro.** Times e camisas buscados são gravados no banco e as imagens são
  copiadas para `storage/images`. A fonte só é consultada de novo quando a cópia tem mais de
  24 h (`CATALOG_TTL_HOURS`).
- **O lote é uma cópia.** Ao criar um lote, título, atributos e imagem são copiados para ele.
  Vitrine, sala, auditoria e comprovante leem só o banco local e as imagens locais.
- **Disjuntor.** Se a fonte cai, demora ou responde 429, a busca devolve o que já está salvo
  com um aviso ("tente de novo em N s") e respeita o `Retry-After`. Respostas malformadas são
  tratadas como indisponibilidade, nunca derrubam a página.
- **Seed independente.** Sem a fonte, o seed usa camisas locais de reserva.

Para testar: rode com `THESPORTSDB_BASE_URL=http://localhost:9` (porta fechada). Vitrine,
salas, auditoria e comprovantes continuam iguais; a busca do painel mostra o aviso e as camisas
já salvas.

## Auditoria à prova de adulteração

### Técnica

1. **Cadeia de hashes por lote.** Cada evento (abertura, lance, prorrogação, encerramento ou
   cancelamento) vira um elo:
   `hash = SHA-256(prev_hash | lot_id | seq | tipo | payload_canônico)`. O primeiro elo aponta
   para 64 zeros. O payload é guardado em JSON canônico (chaves ordenadas), então o que foi
   assinado é exatamente o que é servido.
2. **Assinatura Ed25519.** Cada `hash` é assinado com a chave privada da casa, que fica fora do
   banco. A chave pública está em `GET /api/audit/public-key`. Recalcular hashes é fácil;
   produzir assinaturas sem a chave, não.
3. **Banco só de acréscimo.** Um gatilho recusa `UPDATE` e `DELETE` em `audit_log`.
4. **Testemunha fora do banco.** Depois de cada COMMIT, o servidor grava em
   `storage/audit-witness.jsonl` uma linha assinada com o último elo do lote. O navegador
   também guarda o último elo que viu de cada lote.
5. **Checagem cruzada.** O estado do lote tem de bater com a trilha: preço atual, líder,
   contagem de lances, fim vigente e evento final.

### O que ela detecta

| Adulteração (direto no banco) | Detectada por | Veredito |
|---|---|---|
| Alterar o valor de um lance | o hash do elo não confere com o conteúdo | `altered` |
| Remover um lance do meio | salto na sequência / `prev_hash` órfão | `missing` |
| Remover o último evento e reescrever a cabeça | a testemunha fora do banco viu um elo a mais | `truncated` |
| Inserir um lance falso, mesmo com hash correto | assinatura inválida (sem a chave da casa) | `inserted` |
| Mexer em preço, líder, contagem ou fim do lote | checagem cruzada | `state_mismatch` |

### Onde verificar

- **Página pública** `/auditoria/<lote>`: veredito do servidor, histórico legível e o botão
  **"Verificar no meu navegador"**, que refaz tudo com Web Crypto a partir do histórico e da
  chave pública, sem usar o veredito do servidor.
- **Fora do site:**
  `uv run --directory backend python -m scripts.verify_audit <lotId> http://localhost:8080/api`.
- **API:** `GET /api/audit/lots/<lote>` e `GET /api/audit/lots/<lote>/verify`.

### Reproduza a detecção (cerca de 5 min)

Pré-requisito: `docker compose up --build` e http://localhost:8080 aberto.

**1. Ache o lote com 3 lances e abra a auditoria.**

```bash
docker compose exec db psql -U postgres -d leilao -c "SELECT id, title FROM lots WHERE bid_count = 3"
```

Abra `http://localhost:8080/auditoria/<id>`: veredito **Íntegro**.

**2. Abra o `psql`, guarde uma cópia e desligue a proteção (só para o teste).**

```bash
docker compose exec db psql -U postgres -d leilao
```

```sql
\set lote <id>
CREATE TABLE copia_trilha AS SELECT * FROM audit_log WHERE lot_id = :'lote';
CREATE TABLE copia_lote AS SELECT id, audit_seq, audit_head_hash FROM lots WHERE id = :'lote';
ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update;
```

Para **restaurar** entre um experimento e outro:

```sql
DELETE FROM audit_log WHERE lot_id = :'lote';
INSERT INTO audit_log SELECT * FROM copia_trilha;
UPDATE lots l SET audit_seq = c.audit_seq, audit_head_hash = c.audit_head_hash FROM copia_lote c WHERE l.id = c.id;
```

**3. Alterar o valor de um lance.** Recarregue a página: **Adulterado**, "conteúdo alterado"
no evento 3. Restaure.

```sql
UPDATE audit_log SET payload_canonical = replace(payload_canonical, '"amount_cents":17000', '"amount_cents":1700')
 WHERE lot_id = :'lote' AND seq = 3;
```

**4. Remover um lance do meio.** **Adulterado**, "evento ausente". Restaure.

```sql
DELETE FROM audit_log WHERE lot_id = :'lote' AND seq = 3;
```

**5. Remover o último evento e "arrumar" a cabeça no banco.** **Adulterado**, "fim do
histórico removido": a cadeia que sobrou é válida, mas a testemunha viu o evento 4. Restaure.

```sql
DELETE FROM audit_log WHERE lot_id = :'lote' AND seq = 4;
UPDATE lots SET audit_seq = 3, audit_head_hash = (SELECT hash FROM audit_log WHERE lot_id = :'lote' AND seq = 3) WHERE id = :'lote';
```

**6. Inserir um lance falso** com hash correto, mas sem a assinatura da casa. **Adulterado**,
"evento intruso" no evento 5.

```sql
INSERT INTO audit_log (lot_id, seq, event_type, payload_canonical, prev_hash, hash, signature)
SELECT lot_id, 5, 'bid_placed', '{"amount_cents":99999,"at":"2026-10-28T20:00:00.000Z","bid_id":999,"bidder":"ffffffffffffffff"}',
       hash, encode(sha256(convert_to(hash || '|' || lot_id || '|5|bid_placed|' ||
         '{"amount_cents":99999,"at":"2026-10-28T20:00:00.000Z","bid_id":999,"bidder":"ffffffffffffffff"}', 'UTF8')), 'hex'),
       'assinatura-falsa'
  FROM audit_log WHERE lot_id = :'lote' AND seq = 4;
```

Em cada passo, o botão **"Verificar no meu navegador"** chega ao mesmo veredito.

**7. Feche o experimento.**

```sql
DELETE FROM audit_log WHERE lot_id = :'lote';
INSERT INTO audit_log SELECT * FROM copia_trilha;
UPDATE lots l SET audit_seq = c.audit_seq, audit_head_hash = c.audit_head_hash FROM copia_lote c WHERE l.id = c.id;
ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_update;
DROP TABLE copia_trilha, copia_lote;
```

## Privacidade

- **Pseudônimo na auditoria e no comprovante.** O licitante aparece como
  `HMAC(PSEUDONYM_SECRET, usuário:lote)`, 16 caracteres hexadecimais. O código é estável dentro
  do lote (dá para acompanhar a disputa) e diferente entre lotes (não dá para seguir alguém de
  lote em lote). Sem o segredo, ninguém descobre de quem é.
- **Link do comprovante.** O formato é `/comprovante/<lote>.<token>`, com
  `token = HMAC(RECEIPT_SECRET, lote)`. Não é sequencial nem adivinhável, e não é possível
  forjar o comprovante de outro lote.
- **Nada pessoal em público.** Respostas públicas e eventos do socket não trazem usuário, nome
  nem id interno, e há testes que garantem isso.
- Senhas são guardadas com scrypt e sal aleatório.

## Opcionais entregues

| Opcional | Status | Observação |
|---|---|---|
| Busca e filtro de lotes | ✅ | busca por texto (ignora acentos) e filtro por estado na vitrine |
| Cancelamento com estorno automático | ✅ | o cancelamento só vale para lote sem lances, como pede o desafio. Como o saldo comprometido é derivado dos lotes que o licitante lidera, nenhum valor fica preso |
| Docker Compose | ✅ | `docker compose up --build` sobe banco, API, front e seed |
| Testes automatizados | ✅ | back e front, contra PostgreSQL real, incluindo concorrência e adulteração |
| Dark Mode | ✅ | botão no topo; segue o tema do sistema na primeira visita; contraste AA testado |

## Testes

Os testes do backend rodam contra um **PostgreSQL real**, no banco `leilao_test` por padrão
(`TEST_DATABASE_URL` para trocar).

```bash
cd backend && uv run ruff check && uv run mypy && uv run pytest
cd frontend && npm run typecheck && npm test && npm run build
```

| Teste | Garante |
|---|---|
| 50 lances paralelos, valores embaralhados | preço final = maior aceito; histórico crescente; sem deadlock |
| 20 lances paralelos com o mesmo valor | exatamente 1 aceito |
| mesmo usuário, 10 lotes em paralelo | nunca compromete mais que o saldo |
| liquidação 20× + job em paralelo | um débito do vencedor e um crédito do leiloeiro |
| lances martelando enquanto o lote fecha | nenhum lance aceito após o fim |
| 50 lances paralelos na janela de prorrogação | o fim só aumenta, nunca diminui |
| lance × cancelamento em paralelo | nunca os dois aceitos |
| motivos de recusa | um código e uma mensagem para cada motivo |
| fonte de camisas fora do ar, limitada (429) ou malformada | busca responde com o que está salvo e um aviso |
| adulteração direta no banco | veredito "adulterado" com o tipo e o ponto da quebra |
| verificador do navegador × do servidor | mesmo veredito nos mesmos casos |
| depósito repetido com a mesma chave | um único lançamento |
| respostas públicas e eventos do socket | nenhum nome, usuário ou id interno |
| contraste dos dois temas | todos os pares de cor ≥ 4,5:1 (AA) |

## API

O front chama as rotas abaixo sob `/api` (o nginx e o Vite removem o prefixo).

| Método | Rota | Acesso |
|---|---|---|
| POST | `/auth/register` (`username`, `password`, `role`: `auctioneer` ou `bidder`) · `/auth/login` | — |
| GET | `/me` (papel e saldos) | login |
| GET | `/wallet` (saldos e lotes do comprometido) | licitante |
| POST | `/wallet/deposit` `{amount_cents}` + `Idempotency-Key` | licitante |
| GET | `/me/participations` (meus arremates) | licitante |
| GET | `/lots` (vitrine) · `/lots/:id` (sala, com posição se logado) | — |
| POST | `/lots/:id/bids` `{amount_cents}` + `Idempotency-Key` | licitante |
| GET | `/auctioneer/catalog/teams?q=` · `/auctioneer/catalog/teams/:teamId/jerseys` · `/auctioneer/catalog/jerseys` | leiloeiro |
| GET/POST | `/auctioneer/lots` · POST `/auctioneer/lots/:id/cancel` | leiloeiro |
| GET | `/receipts/:receiptId` (comprovante) | — |
| GET | `/audit/public-key` · `/audit/lots/:id` · `/audit/lots/:id/verify` | — |

Socket.IO: emita `lot:join <lotId>`; receba `bid:placed`, `lot:extended`, `lot:settled` e
`lot:cancelled`; com login, também `bid:outbid`, `lot:won` e `wallet:changed`.

## Comportamentos inesperados e limitações

- **Login por usuário, não por e-mail.** O usuário aceita de 3 a 32 caracteres (letras,
  números, `_` e `-`) e não diferencia maiúsculas.
- **Lotes semeados vencem.** O seed cria os lotes uma vez, com horários relativos à subida.
  Depois, crie um lote novo pelo painel ou, local, rode `docker compose down -v && docker
  compose up --build`.
- **TheSportsDB limitada.** A chave gratuita aceita cerca de 10 consultas por minuto e devolve
  poucas camisas por time (≈ 2). Ao bater no limite, a busca mostra "tente de novo em N s".
  Camisas sem imagem na fonte não podem virar lote.
- **A fase exibida é do navegador; quem decide é o banco.** Ao zerar a contagem, o lote fica
  "a confirmar" por um instante. Um lance enviado no último segundo pode ser recusado como
  "encerrado" se chegar depois do fim.
- **Prorrogação sem limite.** Enquanto houver lances nos últimos 2 min, o lote não fecha.
- **Liquidação até ~1 s depois do fim** pelo job; qualquer leitura do lote já o liquida.
- **Testemunha da auditoria depende de disco persistente.** Sem o volume `storage/`, ela se
  perde a cada reinício: a página mostra "sem testemunha" (nunca um falso "adulterado") e a
  remoção do último evento deixa de ser detectável pelo servidor.
- **Limite da técnica.** A testemunha protege contra quem controla o banco. Quem controla o
  servidor **e** o volume `storage/` pode reescrever tudo; contra isso seria preciso publicar a
  cabeça da cadeia num lugar externo, o que ficou fora do escopo.
- **Chave de auditoria gerada.** Sem `AUDIT_PRIVATE_KEY_PEM`, a chave é gerada em `storage/`.
  Apagar só esse volume e manter o banco faz as trilhas antigas falharem na assinatura.
- **Navegadores sem Ed25519 no Web Crypto** não fazem a verificação local; a página avisa e
  indica o script offline.
- **Papel fixo.** Uma conta é leiloeiro ou licitante para sempre.
- **Datas do formulário de lote** usam o fuso do navegador; o servidor grava em UTC e valida
  "início no passado" pelo relógio do banco, com 1 min de tolerância.
- **Instância única.** Socket.IO e o disjuntor do catálogo vivem em memória. Para escalar
  horizontalmente, seria preciso o `AsyncRedisManager` do python-socketio e estado no Redis.
- **Depósito simulado.** Não há pagamento real, saque nem extrato.
- **`NODE_ENV` num backend Python.** O nome foi mantido da versão Node do backend para não
  mudar o `.env` de quem já rodava o projeto.
