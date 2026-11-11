FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY schema-refresh-workshop/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY schema-refresh-workshop/ ./
CMD ["python", "starter.py"]
