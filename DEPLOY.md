# Deploy da Demo Pública (Streamlit Community Cloud)

Topologia usada em produção: **Streamlit Community Cloud roda o app** (lê direto deste
repositório no GitHub) → conversa com **Supabase** (dados), **Cube Cloud** (camada
semântica) e **OpenAI** (LLM). Login via **Google**, com limite de perguntas por pessoa.

> A primeira subida costuma pedir 1-2 ajustes (URL de callback, propagação do Google). É normal.

## 1. Cube Cloud (camada semântica)

1. Crie conta em https://cubecloud.dev (free tier) e um novo deployment.
2. **Importar de um repositório GitHub** → repositório `BI_COPILOT` → em *Diretório do Projeto*
   informe **`cube_project`** (é onde está a pasta `model/` com os 6 cubos).
3. Conexão de banco: **PostgreSQL** com as credenciais do Supabase (host do session pooler,
   porta 5432, `postgres`, user `postgres.<ref>`, SSL ativado).
4. Nas env vars do deployment, defina `CUBEJS_API_SECRET` com o **mesmo valor** usado no app
   (o do `.env`) — o app assina o JWT com ele e o Cube valida com ele.
5. Anote a **URL da API REST** (ex.: `https://<nome>.aws-us-east-1.cubecloudapp.dev`) — sem o
   sufixo `/cubejs-api/v1`, que o app adiciona sozinho.

## 2. Google OAuth (login)

1. https://console.cloud.google.com → crie um projeto.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID → Web application**.
3. Em **Authorized redirect URIs**, adicione a URL do app + `/oauth2callback`
   (ex.: `https://<seu-app>.streamlit.app/oauth2callback`).
4. Anote **Client ID** e **Client secret**.

## 3. Streamlit Community Cloud

1. https://share.streamlit.io → entre com o GitHub.
2. **New app** → repositório `RaulRMO10/BI_COPILOT`, branch `main`, main file `app.py`.
3. Em **Settings → Secrets**, cole um TOML no formato abaixo (valores entre aspas). Os campos
   de topo viram variáveis de ambiente (via ponte no `app.py`); a seção `[auth]` é lida pelo
   `st.login`:

   ```toml
   DEMO_MODE = "true"
   LLM_PROVIDER = "openai"
   LLM_MODEL = "gpt-5.1"
   DEMO_LIMITE_PERGUNTAS = "10"
   DEMO_LIMITE_GLOBAL_DIA = "300"
   DEPT_PUBLICO = "002"
   DEPT_EXCLUIDO = "004"
   LINKEDIN_URL = "https://www.linkedin.com/in/seu-perfil/"
   GITHUB_URL = "https://github.com/RaulRMO10/BI_COPILOT"

   DATABASE_URL = "postgresql://postgres.<ref>:<senha>@<host-pooler>:5432/postgres?sslmode=require"
   OPENAI_API_KEY = "sk-proj-..."
   CUBE_API_BASE_URL = "https://<nome>.aws-us-east-1.cubecloudapp.dev"
   CUBEJS_API_SECRET = "<mesmo secret do Cube Cloud>"

   # opcional — tracing
   LANGSMITH_TRACING = "true"
   LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
   LANGSMITH_API_KEY = "lsv2_pt_..."
   LANGSMITH_PROJECT = "BI_COPILOT"

   [auth]
   redirect_uri = "https://<seu-app>.streamlit.app/oauth2callback"
   cookie_secret = "<string aleatoria longa>"
   client_id = "<google client id>"
   client_secret = "<google client secret>"
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
   ```

4. Deploy. O `requirements.txt` inclui `Authlib` (necessário para o `st.login`). A URL do app
   (`redirect_uri`) precisa bater **idêntica** com a cadastrada no Google (passo 2).

## 4. Discord (notificação — opcional)

Num canal do Discord: **Editar canal → Integrações → Webhooks → Novo webhook → Copiar URL** →
adicione como secret `DISCORD_WEBHOOK_URL`. Você recebe um aviso a cada nova visita e feedback.

## Antes de divulgar

- Faça uma pergunta de ponta a ponta logado com sua conta Google.
- Confirme o medidor de crédito descendo e a "parede" ao esgotar.
- Free tier do Supabase **pausa após ~1 semana** sem uso — com tráfego, fica acordado.

---

## Alternativa: Hugging Face Spaces (Docker)

O repo também traz um `Dockerfile` + `deploy/entrypoint.sh` para hospedar como Space Docker
(app na porta 7860; o entrypoint monta o `.streamlit/secrets.toml` a partir de env vars). Não
é o deploy usado (a conta esbarrou na cota de hardware do HF), mas fica como opção.
