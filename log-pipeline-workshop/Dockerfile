FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends lua5.1 lua-cjson \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir pytest==8.4.2

COPY log-pipeline-workshop/ ./
CMD ["python", "app.py"]
