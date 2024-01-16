FROM python:3.11-slim-bookworm as final

RUN apt-get update --fix-missing && apt-get install -y --fix-missing \
    build-essential \
    gcc \
    g++ && \
    rm -rf /var/lib/apt/lists/*

COPY ./ /app

WORKDIR /app

# install poetry
RUN pip install poetry && \
    poetry install --no-dev --no-interaction --no-ansi

EXPOSE 8080
ENTRYPOINT ["poetry", "run", "uvicorn", "app.app:app", "--workers", "1", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--timeout-keep-alive", "30"]
