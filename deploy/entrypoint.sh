#!/usr/bin/env bash
# Entrypoint do container demo (HF Spaces).
# Materializa .streamlit/secrets.toml com o bloco [auth] do login Google a partir
# das secrets do Space (env vars), depois sobe o Streamlit na porta 7860.
set -e

mkdir -p .streamlit

if [ -n "${GOOGLE_CLIENT_ID:-}" ]; then
  cat > .streamlit/secrets.toml <<EOF
[auth]
redirect_uri = "${AUTH_REDIRECT_URI}"
cookie_secret = "${AUTH_COOKIE_SECRET}"
client_id = "${GOOGLE_CLIENT_ID}"
client_secret = "${GOOGLE_CLIENT_SECRET}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
EOF
  echo "[entrypoint] login Google configurado."
else
  echo "[entrypoint] GOOGLE_CLIENT_ID ausente — subindo com fallback de e-mail."
fi

exec streamlit run app.py \
  --server.port 7860 \
  --server.address 0.0.0.0 \
  --server.headless true
