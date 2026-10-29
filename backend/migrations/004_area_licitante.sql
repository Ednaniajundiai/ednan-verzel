-- 004_area_licitante: idempotência do depósito (spec 004, S-09). Uma confirmação
-- repetida (duplo clique, reenvio) com a mesma chave vira um único lançamento.
ALTER TABLE ledger_entries ADD COLUMN IF NOT EXISTS idempotency_key text;
CREATE UNIQUE INDEX IF NOT EXISTS ledger_user_idempotency_uq
  ON ledger_entries (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
