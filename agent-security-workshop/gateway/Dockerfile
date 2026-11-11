FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir 'psycopg[binary]==3.2.10'
WORKDIR /app
COPY gateway.py write_config.py apply_security.py security.sql ./
USER 1002:1002
CMD ["python", "gateway.py"]
