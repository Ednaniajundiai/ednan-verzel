-- 005_usuario: login por nome de usuário no lugar do e-mail.
-- `username` guarda o que a pessoa digitou; a unicidade ignora maiúsculas. `email` vira legado
-- opcional (contas novas não têm). Contas antigas ganham um usuário derivado do e-mail.
ALTER TABLE users ADD COLUMN IF NOT EXISTS username text;

WITH cleaned AS (
  SELECT id, regexp_replace(split_part(email, '@', 1), '[^A-Za-z0-9_-]', '_', 'g') AS c
  FROM users
  WHERE username IS NULL
), base AS (
  SELECT id, CASE WHEN length(c) < 3 THEN rpad(c, 3, '_') ELSE left(c, 28) END AS b FROM cleaned
), numbered AS (
  SELECT id, b, row_number() OVER (PARTITION BY lower(b) ORDER BY id) AS n FROM base
)
UPDATE users u
   SET username = CASE WHEN numbered.n = 1 THEN numbered.b ELSE numbered.b || '_' || numbered.n END
  FROM numbered
 WHERE u.id = numbered.id;

ALTER TABLE users ALTER COLUMN username SET NOT NULL;
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uq ON users (lower(username));
