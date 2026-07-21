# Deploy da Demo Pública (Hugging Face Spaces)

Topologia: **HF Space (Docker) roda só o Streamlit** → conversa com **Supabase** (dados),
**Cube Cloud** (camada semântica) e **OpenAI** (LLM). Login via **Google**, com limite de
perguntas por pessoa. Este runbook cobre os 4 setups externos. Ordem sugerida abaixo.

> A primeira subida costuma pedir 1-2 ajustes (portas, URI de callback). É normal.

## 1. Cube Cloud (camada semântica)

1. Crie conta em https://cubecloud.dev (free tier).
2. **New Deployment** → conecte ao repositório GitHub `BI_COPILOT`, pasta `cube_project/`.
3. Configure a conexão com o banco (as mesmas credenciais do Supabase do `.env`):
   `CUBEJS_DB_TYPE=postgres`, host do session pooler, porta 5432, `CUBEJS_DB_SSL=true`.
4. Após o deploy, anote: **URL da API do Cube** (algo como `https://<seu>.cubecloud.dev`)
   e o **API Secret** (em Settings → Env vars, `CUBEJS_API_SECRET`).

## 2. Google OAuth (login)

1. https://console.cloud.google.com → crie um projeto.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID → Web application**.
3. Em **Authorized redirect URIs**, adicione: `https://<seu-space>.hf.space/oauth2callback`
   (o `<seu-space>` você define ao criar o Space no passo 3; pode voltar aqui e adicionar depois).
4. Anote **Client ID** e **Client secret**.

## 3. Hugging Face Space

1. https://huggingface.co → **New Space** → SDK **Docker** → nome (ex.: `bi-copilot`).
2. Faça push deste repositório para o Space (ou conecte o GitHub). O `Dockerfile` na raiz
   já sobe o app na porta 7860.
3. Em **Settings → Variables and secrets**, adicione as secrets (nunca no código):

   | Nome | Valor |
   |---|---|
   | `DATABASE_URL` | URI do session pooler do Supabase (`...sslmode=require`) |
   | `OPENAI_API_KEY` | sua chave OpenAI |
   | `LLM_PROVIDER` | `openai` |
   | `LLM_MODEL` | `gpt-5.1` |
   | `CUBE_API_BASE_URL` | URL da API do Cube Cloud (passo 1) |
   | `CUBEJS_API_SECRET` | secret do Cube Cloud (passo 1) |
   | `DEMO_MODE` | `true` |
   | `DEMO_LIMITE_PERGUNTAS` | `10` |
   | `DEMO_LIMITE_GLOBAL_DIA` | `300` |
   | `GOOGLE_CLIENT_ID` | client id do passo 2 |
   | `GOOGLE_CLIENT_SECRET` | client secret do passo 2 |
   | `AUTH_REDIRECT_URI` | `https://<seu-space>.hf.space/oauth2callback` |
   | `AUTH_COOKIE_SECRET` | string aleatória longa (assina o cookie de sessão) |
   | `LINKEDIN_URL` | seu LinkedIn |
   | `GITHUB_URL` | URL do repositório |
   | `DISCORD_WEBHOOK_URL` | (opcional) webhook do passo 4 |
   | `LANGSMITH_API_KEY` | (opcional) tracing |

4. O `deploy/entrypoint.sh` monta o `.streamlit/secrets.toml` a partir dessas variáveis
   e sobe o app. Volte ao passo 2 e confirme que o redirect URI casa com a URL final do Space.

## 4. Discord (notificação — opcional)

Num canal do seu Discord: **Editar canal → Integrações → Webhooks → Novo webhook →
Copiar URL** → cole em `DISCORD_WEBHOOK_URL`. Você recebe um aviso a cada nova visita e feedback.

## Antes de divulgar

- Rode uma pergunta de ponta a ponta logado com sua conta Google.
- Confirme o medidor de crédito descendo e a "parede" ao esgotar.
- Lembre: o free tier do Supabase **pausa após ~1 semana** sem uso — com tráfego, fica acordado.
