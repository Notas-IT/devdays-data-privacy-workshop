FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.163.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir 'psycopg[binary]==3.2.10' \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && mkdir /workspace && chmod 0777 /workspace
ENV PATH="/opt/venv/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1
COPY layer_runtime/agent_client.py /opt/agent/client.py
WORKDIR /workspace
CMD ["python", "-c", "import time; time.sleep(2147483647)"]
