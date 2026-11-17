FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /broker
COPY broker.py write_config.py ./
RUN mkdir /state && chown 10003:10003 /state
USER 10003:10003
CMD ["python", "broker.py"]
