FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TLDEXTRACT_CACHE=/opt/presidio/tld-cache

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Cache the stock email recognizer's suffix list before the workshop starts.
RUN python -c "import tldextract; assert tldextract.extract('example.com').suffix == 'com'"

COPY . ./

CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
