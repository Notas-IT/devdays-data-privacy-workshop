FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN pip install --no-cache-dir 'psycopg[binary]==3.2.10'
COPY gateway.py ./
USER 10002:10002
CMD ["python", "gateway.py"]
