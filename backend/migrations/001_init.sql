-- 001_init: esquema inicial (spec 001). Valores monetários em centavos (Const. 1.1).

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  name          text NOT NULL,
  password_hash text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wallets (
  user_id       uuid PRIMARY KEY REFERENCES users(id),
  balance_cents bigint NOT NULL DEFAULT 0 CHECK (balance_cents >= 0), -- Const. 1.2
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS items (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id      text NOT NULL UNIQUE,
  source           text NOT NULL,
  title            text NOT NULL,
  description      text NOT NULL DEFAULT '',
  image_path       text,
  image_source_url text,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lots (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id              uuid NOT NULL REFERENCES items(id),
  starting_price_cents bigint NOT NULL CHECK (starting_price_cents > 0),
  min_increment_cents  bigint NOT NULL CHECK (min_increment_cents > 0),
  starts_at            timestamptz NOT NULL,
  ends_at              timestamptz NOT NULL,
  status               text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'settled', 'unsold')),
  current_price_cents  bigint,
  leader_user_id       uuid REFERENCES users(id),
  bid_count            integer NOT NULL DEFAULT 0,
  audit_seq            integer NOT NULL DEFAULT 0,
  audit_head_hash      text NOT NULL DEFAULT repeat('0', 64),
  settled_at           timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (ends_at > starts_at),
  CHECK ((leader_user_id IS NULL) = (current_price_cents IS NULL))
);

-- Job de liquidação: só lotes abertos, ordenados por vencimento.
CREATE INDEX IF NOT EXISTS lots_open_ends_at_idx ON lots (ends_at) WHERE status = 'open';
-- Cálculo do saldo comprometido (P2).
CREATE INDEX IF NOT EXISTS lots_open_leader_idx ON lots (leader_user_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS bids (
  id              bigserial PRIMARY KEY,
  lot_id          uuid NOT NULL REFERENCES lots(id),
  user_id         uuid NOT NULL REFERENCES users(id),
  amount_cents    bigint NOT NULL CHECK (amount_cents > 0),
  idempotency_key text,
  created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS bids_lot_idx ON bids (lot_id, id);

CREATE TABLE IF NOT EXISTS ledger_entries (
  id           bigserial PRIMARY KEY,
  user_id      uuid NOT NULL REFERENCES users(id),
  kind         text NOT NULL CHECK (kind IN ('deposit', 'settlement_debit')),
  amount_cents bigint NOT NULL,
  lot_id       uuid REFERENCES lots(id),
  created_at   timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- Segunda barreira de idempotência da liquidação (Const. 3.2).
CREATE UNIQUE INDEX IF NOT EXISTS ledger_lot_kind_uq ON ledger_entries (lot_id, kind) WHERE lot_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS audit_log (
  lot_id            uuid NOT NULL REFERENCES lots(id),
  seq               integer NOT NULL,
  event_type        text NOT NULL,
  payload_canonical text NOT NULL,
  prev_hash         text NOT NULL,
  hash              text NOT NULL,
  signature         text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (lot_id, seq)
);

-- Append-only (Const. 4.3): bloqueia UPDATE/DELETE no próprio banco.
CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log é append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
