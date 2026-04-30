FROM python:3.14.3-slim-bookworm

WORKDIR /app
COPY . /app

RUN apt-get update \
    && pip install \
        --no-cache-dir \
        -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
