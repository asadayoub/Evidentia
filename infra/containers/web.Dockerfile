# syntax=docker/dockerfile:1.19
# @skyhook-implements REQ-012
# @skyhook-implements NFR-004
# @skyhook-story STORY-009

ARG NODE_IMAGE=node:24.21.0-alpine3.24
ARG NGINX_IMAGE=nginx:1.29.8-alpine3.23

FROM ${NODE_IMAGE} AS builder
ENV PNPM_HOME=/pnpm
ENV PATH=${PNPM_HOME}:${PATH}
WORKDIR /workspace

RUN corepack enable && corepack prepare pnpm@12.8.1 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY frontend/package.json frontend/
COPY sdks/typescript/package.json sdks/typescript/
RUN pnpm install --frozen-lockfile

COPY frontend frontend
COPY sdks/typescript sdks/typescript
RUN pnpm --filter @evidentia/typescript-sdk build \
    && pnpm --filter @evidentia/web build

FROM ${NGINX_IMAGE} AS runtime
COPY infra/containers/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder --chown=nginx:nginx /workspace/frontend/dist /usr/share/nginx/html
RUN mkdir -p /tmp/nginx/client_temp /tmp/nginx/proxy_temp /tmp/nginx/fastcgi_temp \
    /tmp/nginx/uwsgi_temp /tmp/nginx/scgi_temp \
    && chown -R nginx:nginx /tmp/nginx
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/health/live"]
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
