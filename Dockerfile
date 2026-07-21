# Imagem do MODO DEMO PÚBLICO (Hugging Face Spaces — só o app Streamlit).
# O Cube.js roda separado no Cube Cloud; o Postgres é o Supabase. Ver DEPLOY.md.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DEMO_MODE=true
# HF Spaces expõe a porta 7860
EXPOSE 7860

CMD ["bash", "deploy/entrypoint.sh"]
