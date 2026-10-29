-- 002_papeis_catalogo: papéis, dono e cópia da camisa no lote, catálogo TheSportsDB,
-- cancelamento e crédito ao leiloeiro (spec 002).

-- ---------------------------------------------------------------- papéis (D-06)
ALTER TABLE users ADD COLUMN IF NOT EXISTS role text;
UPDATE users SET role = 'bidder' WHERE role IS NULL; -- D-04: contas da 001 viram licitantes
ALTER TABLE users ALTER COLUMN role SET NOT NULL;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('auctioneer', 'bidder'));

-- Conta de sistema dona dos lotes antigos. password_hash '!' nunca confere (D-04).
INSERT INTO users (email, name, password_hash, role)
VALUES ('sistema@casa-de-leiloes.invalid', 'Leiloeiro do sistema', '!', 'auctioneer')
ON CONFLICT (email) DO NOTHING;
INSERT INTO wallets (user_id)
SELECT id FROM users WHERE email = 'sistema@casa-de-leiloes.invalid'
ON CONFLICT (user_id) DO NOTHING;

-- ---------------------------------------------------------------- catálogo (D-03)
ALTER TABLE items
  ADD COLUMN IF NOT EXISTS team_external_id text,
  ADD COLUMN IF NOT EXISTS season text,
  ADD COLUMN IF NOT EXISTS kind text,
  ADD COLUMN IF NOT EXISTS fetched_at timestamptz;
CREATE INDEX IF NOT EXISTS items_team_idx ON items (team_external_id);

CREATE TABLE IF NOT EXISTS catalog_teams (
  external_id        text PRIMARY KEY,
  name               text NOT NULL,
  league             text,
  country            text,
  badge_url          text,
  fetched_at         timestamptz NOT NULL DEFAULT now(),
  jerseys_fetched_at timestamptz
);

CREATE TABLE IF NOT EXISTS catalog_team_searches (
  term_normalized   text PRIMARY KEY,
  team_external_ids text[] NOT NULL,
  fetched_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- lote: dono e cópia (D-09, D-10)
ALTER TABLE lots
  ADD COLUMN IF NOT EXISTS auctioneer_id uuid REFERENCES users(id),
  ADD COLUMN IF NOT EXISTS title text,
  ADD COLUMN IF NOT EXISTS size text CHECK (size IN ('PP', 'P', 'M', 'G', 'GG', 'XGG')),
  ADD COLUMN IF NOT EXISTS condition text CHECK (condition IN ('nova_com_etiqueta', 'nova', 'usada')),
  ADD COLUMN IF NOT EXISTS attributes jsonb NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS image_path text,
  ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;

UPDATE lots l
   SET auctioneer_id = (SELECT id FROM users WHERE email = 'sistema@casa-de-leiloes.invalid'),
       title = i.title,
       image_path = i.image_path
  FROM items i
 WHERE i.id = l.item_id AND l.auctioneer_id IS NULL;

ALTER TABLE lots ALTER COLUMN auctioneer_id SET NOT NULL;
ALTER TABLE lots ALTER COLUMN title SET NOT NULL;

ALTER TABLE lots DROP CONSTRAINT IF EXISTS lots_status_check;
ALTER TABLE lots ADD CONSTRAINT lots_status_check CHECK (status IN ('open', 'settled', 'unsold', 'cancelled'));
-- Cancelado nunca tem líder (só se cancela sem lances) e sempre tem o instante do cancelamento.
ALTER TABLE lots ADD CONSTRAINT lots_cancelled_check
  CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL) AND (status <> 'cancelled' OR leader_user_id IS NULL));

CREATE INDEX IF NOT EXISTS lots_auctioneer_idx ON lots (auctioneer_id, created_at DESC);

-- ---------------------------------------------------------------- crédito ao leiloeiro (D-01)
-- O UNIQUE(lot_id, kind) da 001 já barra um segundo crédito do mesmo lote.
ALTER TABLE ledger_entries DROP CONSTRAINT IF EXISTS ledger_entries_kind_check;
ALTER TABLE ledger_entries ADD CONSTRAINT ledger_entries_kind_check
  CHECK (kind IN ('deposit', 'settlement_debit', 'settlement_credit'));
