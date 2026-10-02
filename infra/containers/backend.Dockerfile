# syntax=docker/dockerfile:1.19
# @skyhook-implements NFR-004
# @skyhook-implements NFR-006
# @skyhook-story STORY-009

ARG PYTHON_IMAGE=python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.21

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /workspace

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
COPY sdks/python/pyproject.toml sdks/python/
RUN uv sync --frozen --no-dev --package evidentia-backend --no-install-project

COPY backend/src backend/src
RUN uv sync --frozen --no-dev --no-editable --package evidentia-backend

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/workspace/.venv/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /workspace

RUN groupadd --gid 10001 evidentia \
    && useradd --uid 10001 --gid evidentia --no-create-home --shell /usr/sbin/nologin evidentia \
    && mkdir -p /var/lib/evidentia/artifacts \
    && chown -R evidentia:evidentia /var/lib/evidentia
COPY --from=builder --chown=evidentia:evidentia /workspace/.venv /workspace/.venv
USER 10001:10001

FROM runtime AS api
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]
CMD ["evidentia-api"]

FROM runtime AS worker
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["python", "-c", "from evidentia.entrypoints.worker import worker_probe; assert worker_probe()['status'] == 'ok'"]
CMD ["evidentia-worker"]
