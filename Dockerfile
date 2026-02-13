FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG PIP_EXTRA_ARGS=""

WORKDIR /app

COPY requirements.txt ./
RUN sh -c "pip install --no-cache-dir ${PIP_EXTRA_ARGS} -r requirements.txt"

COPY app ./app
COPY docs ./docs

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
