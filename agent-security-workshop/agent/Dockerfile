FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.163.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_VERSION}"
ENV PYTHONDONTWRITEBYTECODE=1
COPY client.py run_codex.py /opt/agent/
COPY workspace/ /workspace/
WORKDIR /workspace
USER 10001:10001
CMD ["python3", "-c", "import time; time.sleep(2147483647)"]
