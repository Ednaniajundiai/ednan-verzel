#!/bin/sh
# Entrypoint do container: migra, popula (opcional), cria o admin (se ADMIN_USERNAME/ADMIN_PASSWORD) e sobe a API.
set -e
python -m scripts.migrate
if [ "$SEED_ON_START" = "true" ]; then
  python -m scripts.seed
fi
if [ -n "$ADMIN_USERNAME" ] || [ -n "$ADMIN_PASSWORD" ]; then
  python -m scripts.create_admin
fi
exec python -m leilao.server
