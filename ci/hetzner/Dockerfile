FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
ENV PNPM_STORE_DIR=/opt/pnpm-store

# 1. OS + base tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg \
    build-essential libffi-dev libssl-dev tini \
    && rm -rf /var/lib/apt/lists/*

# 2. uv (pinned — bump when needed, not on a schedule)
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /usr/local/bin/uv

# 3. Python 3.11-3.14 via uv (no deadsnakes PPA needed)
RUN uv python install 3.11 3.12 3.13 3.14

# 4. Node 22 LTS + pnpm 9.10.0 (pinned)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && corepack prepare pnpm@9.10.0 --activate

# 5. JS deps — populate pnpm content-addressable store
#    Reproduces the packages/ workspace structure so pnpm install works.
#    At runtime, pnpm install is ~50ms (just creates hard links from the store).
WORKDIR /build-js
COPY packages/pnpm-lock.yaml packages/pnpm-workspace.yaml packages/package.json ./
COPY packages/buckaroo-js-core/package.json ./buckaroo-js-core/
COPY packages/js/package.json ./js/
RUN pnpm install --frozen-lockfile --store-dir /opt/pnpm-store

# 6. Python deps — one venv per Python version, all extras, no project install
#    At runtime, `uv sync` installs only buckaroo itself (editable), which is instant.
WORKDIR /build-py
COPY pyproject.toml uv.lock ./
RUN for v in 3.11 3.12 3.13 3.14; do \
    uv venv /opt/venvs/$v --python $v && \
    UV_PROJECT_ENVIRONMENT=/opt/venvs/$v \
        uv sync --locked --dev --all-extras --no-install-project; \
done

# 7. Playwright chromium — install system deps + browser for Python playwright.
#    JS playwright (pnpm exec playwright) uses the same PLAYWRIGHT_BROWSERS_PATH,
#    so it will find the same browser or install its version alongside it.
RUN /opt/venvs/3.13/bin/playwright install --with-deps chromium
RUN cd /build-js/buckaroo-js-core && pnpm exec playwright install chromium

# 8. Bake CI runner scripts into the image at a stable path so they survive
#    `git checkout` of arbitrary SHAs inside /repo at runtime.
COPY ci/hetzner/run-ci.sh ci/hetzner/lib/ /opt/ci-runner/
COPY scripts/test_playwright_jupyter_parallel.sh /opt/ci-runner/
ARG GIT_SHA=unknown
RUN echo "$GIT_SHA" > /opt/ci-runner/VERSION && \
    chmod +x /opt/ci-runner/run-ci.sh /opt/ci-runner/test_playwright_jupyter_parallel.sh

# Allow JupyterLab to start as root (container runs as root).
# This avoids needing --allow-root in every script that starts Jupyter.
RUN mkdir -p /root/.jupyter && \
    echo "c.ServerApp.allow_root = True" >> /root/.jupyter/jupyter_lab_config.py

# Source code is bind-mounted at /repo at runtime — not baked in.
# Allow git to operate on the bind-mounted repo (owned by ci on host, root in container).
RUN git config --system --add safe.directory /repo
WORKDIR /repo
# tini as PID 1 reaps zombie processes from docker exec'd CI runs.
# Without it, sleep-infinity PID 1 doesn't call wait(), zombies accumulate,
# and back-to-back CI runs fail.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sleep", "infinity"]
