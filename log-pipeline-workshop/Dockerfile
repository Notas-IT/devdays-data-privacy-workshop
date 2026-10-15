FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TLDEXTRACT_CACHE=/opt/presidio/tld-cache

WORKDIR /app
COPY presidio-workshop/requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN python -c "import tldextract; assert tldextract.extract('example.com').suffix == 'com'"

COPY presidio-workshop/detector.py ./shared_detector.py
COPY log-pipeline-workshop/ ./
CMD ["python", "processor.py"]
