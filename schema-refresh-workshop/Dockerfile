FROM postgres:16-bookworm
# Match the database server's dump/restore version and keep Python dependencies isolated.
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/runner
ENV PATH="/opt/runner/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY schema-refresh-workshop/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY schema-refresh-workshop/ ./
ENTRYPOINT []
CMD ["python", "starter.py"]
