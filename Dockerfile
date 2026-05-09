# Multi-arch image for the supython service.
# Build: docker buildx build --platform linux/amd64,linux/arm64 -t supython:dev .
# The admin UI bundle under src/supython/admin/static is committed, so the
# image build is Node-free.
#
# CMD targets the web role. Compose / k8s override this for sibling roles:
#   command: ["supython", "worker", "run", "--queue", "default"]
#   command: ["supython", "migrate"]

# ---------- builder ----------
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Build deps for any wheels that need to compile from source on arm64
# (argon2-cffi pulls cffi, asyncpg has prebuilt wheels for both arches but
# we keep the toolchain available so an off-platform build still succeeds).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --prefix=/install --no-compile . \
    && find /install -depth \
        \( -type d -a \( -name __pycache__ -o -name tests -o -name test \) \) \
        -exec rm -rf {} + \
    && find /install -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SUPYTHON_HOST=0.0.0.0 \
    SUPYTHON_PORT=8000

# `tini` reaps zombies and forwards SIGTERM cleanly to uvicorn.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --user-group --home /app supython

COPY --from=builder /install /usr/local

WORKDIR /app
USER supython

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
url=f'http://127.0.0.1:{os.environ.get(\"SUPYTHON_PORT\",\"8000\")}/livez'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=2).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn supython.app:app --host \"$SUPYTHON_HOST\" --port \"$SUPYTHON_PORT\""]
