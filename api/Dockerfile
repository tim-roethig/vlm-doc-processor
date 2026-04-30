FROM python:3.14.3-slim-bookworm

WORKDIR /app
COPY . /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-impress \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && pip install \
        --no-cache-dir \
        -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
