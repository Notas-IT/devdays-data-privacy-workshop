FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir 'psycopg[binary]==3.2.10'
WORKDIR /workspace
COPY starter.py ./
CMD ["python", "-c", "import time; time.sleep(2147483647)"]
