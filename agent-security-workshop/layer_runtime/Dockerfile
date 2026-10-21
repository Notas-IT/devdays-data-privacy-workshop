FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir 'psycopg[binary]==3.2.10'
WORKDIR /runtime
COPY tools/manage.py ./base_manage.py
COPY tools/schema.sql ./schema.sql
COPY layer_runtime/stage_setup.py layer_runtime/gateway.py layer_runtime/functions.sql ./
ENTRYPOINT ["python", "stage_setup.py"]
