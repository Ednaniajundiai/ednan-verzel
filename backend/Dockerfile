FROM python:3.12-slim
WORKDIR /app
ENV NODE_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
# Dependências antes do código: a camada só refaz quando o uv.lock muda.
RUN pip install --no-cache-dir uv==0.11.32
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
# Mesmo uid do usuário `node` da imagem anterior: volumes `storage` antigos continuam graváveis.
RUN useradd --uid 1000 --create-home app && mkdir -p storage/images && chown -R app:app storage
USER app
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health', timeout=2)" || exit 1
CMD ["sh", "scripts/start.sh"]
