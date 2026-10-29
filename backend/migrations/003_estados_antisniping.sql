-- 003_estados_antisniping: fim original do lote (spec 003). O `ends_at` passa a ser o
-- fim vigente, que só cresce com as prorrogações. `cancelled` já vem da 002.
ALTER TABLE lots ADD COLUMN IF NOT EXISTS original_ends_at timestamptz;
UPDATE lots SET original_ends_at = ends_at WHERE original_ends_at IS NULL;
ALTER TABLE lots ALTER COLUMN original_ends_at SET NOT NULL;
