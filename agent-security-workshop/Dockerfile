FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.163.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir 'psycopg[binary]==3.2.10' \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && groupadd --gid 1001 agent \
    && useradd --uid 1001 --gid 1001 --create-home agent \
    && mkdir -p /workspace /home/agent/.codex \
    && chown -R 1001:1001 /workspace /home/agent
ENV PATH="/opt/venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/agent CODEX_HOME=/home/agent/.codex
WORKDIR /workspace
COPY --chown=1001:1001 workspace/ ./
USER 1001:1001
CMD ["python", "-c", "import time; time.sleep(2147483647)"]
