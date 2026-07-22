# BI Copilot — Assistente Comercial com IA Generativa

Sistema de Business Intelligence conversacional que permite consultar indicadores comerciais em **linguagem natural** (português). O usuário faz perguntas como _"Quais meus 5 melhores clientes deste mês?"_ e o agente decide qual ferramenta usar, executa a query na camada semântica e devolve uma resposta executiva — **respeitando o perfil de acesso de quem pergunta**.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-1C3C3C)
![LLM](https://img.shields.io/badge/LLM-GPT--5.1_%7C_Claude_Sonnet_5-412991)
![PostgreSQL](https://img.shields.io/badge/Supabase-PostgreSQL_17-3FCF8E?logo=supabase&logoColor=white)
![Cube.js](https://img.shields.io/badge/Cube.js-Semantic_Layer-FF6492)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangSmith](https://img.shields.io/badge/LangSmith-Tracing-1C3C3C)

🔗 **Demo ao vivo:** [bicopilot-raulrmo.streamlit.app](https://bicopilot-raulrmo.streamlit.app) — login com Google, 10 perguntas de cortesia.

![Demonstração do BI Copilot](docs/demo.gif)

> ℹ️ **Sobre este projeto:** desenvolvido originalmente em ambiente profissional e disponibilizado aqui **com autorização**, para fins de estudo e portfólio (pós-graduação em **Agentes de IA — FIAP**). Esta versão roda em **modo demonstração**: banco próprio no Supabase com dados públicos e sintéticos — **nenhum dado real de empresa**.

---

## Demonstração

```
[login: brenda — Consultora, carteira privada 001]

Usuária: Quais são meus 5 melhores clientes deste mês?

Assistente: Analisando este mês (01/07 a 19/07)...
1. DROGARIA CARDOSO VASCONCELOS LTDA — R$ 1.838,72
2. CLINICA DAS NEVES LTDA — R$ 1.837,92
...
(o filtro do representante 001 foi injetado pelo código — a consultora
só enxerga a própria carteira, mesmo que o LLM tente o contrário)
```

A interface traz um expander **"Bastidores"** em cada resposta: o JSON gerado para o Cube.js (já com os filtros de segurança), o SQL real executado no banco e o passo a passo de decisão do agente.

---

## Arquitetura

```
┌────────────────────────────────────────────────────────────────┐
│  Streamlit (app.py)                FastAPI (fastapi_server.py) │
│  chat com login de perfis          bridge REST p/ frontends    │
│            │                                  │                │
│            └──────────────┬───────────────────┘                │
│                LangGraph Agentic Workflow                      │
│                (langgraph_app.py: prompt + RLS fail-closed)    │
│                           │                                    │
│              ┌────────────┴─────────────┐                      │
│              ▼                          ▼                      │
│        Tools de banco             Cube.js Semantic Layer       │
│        (tools.py)                 (cube_tools.py → :4000)      │
│              │                          │                      │
│              └────────────┬─────────────┘                      │
│                           ▼                                    │
│              PostgreSQL 17 (Supabase)                          │
│                                                                │
│  Observabilidade: LangSmith (tracing) + Studio (langgraph.json)│
└────────────────────────────────────────────────────────────────┘
```

### Fluxo de uma pergunta

1. O usuário loga na UI (perfil simulado: diretor ou consultor) e pergunta em português
2. O agente recebe o `user_context` e monta o prompt com as regras do perfil
3. O LLM (configurável: GPT-5.1 ou Claude Sonnet 5) escolhe a ferramenta e gera a query
4. O `secure_tool_node` intercepta a chamada e **injeta os filtros de segurança no código** (fail closed)
5. Cube.js traduz a query semântica em SQL e consulta o Postgres
6. O agente interpreta o resultado e responde em linguagem executiva
7. Checkpoints e traces ficam persistidos (Supabase + LangSmith)

---

## Modo demonstração — os dados

O banco demo é construído por um pipeline reproduzível (`seed/`, seed fixo = 42) a partir de fontes públicas:

| Fonte | Uso |
|---|---|
| **[Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)** (Kaggle) | ~100 mil pedidos reais (2016–2018) viram as transações de `dw_vendas`, **re-datados** em múltiplos de 7 dias para uma janela móvel recente (o "mês atual" sempre tem dados) |
| **CMED/ANVISA** (lista pública de preços) | Catálogo de produtos: 25 mil apresentações de medicamentos reais, com laboratório e hierarquia produto-pai |
| **IBGE** (API de localidades) | Códigos oficiais de municípios, UF e região |
| **Camadas sintéticas** | O que não existe em dado público: 30 representantes territoriais, carteiras com ranking ABC, metas, crédito/inadimplência, estoque e a recorrência de compra da base fiel |

Resultado: ~196 mil linhas de vendas, 96 mil clientes com CNPJ fake (dígitos verificadores válidos), faturamento mensal estável de ~R$ 3 mi e distribuição ABC realista — dentro do free tier do Supabase.

> **Atribuição:** o dataset Olist é licenciado sob [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — uso não comercial com atribuição, como neste projeto. Dados da CMED/ANVISA e IBGE são públicos. Nomes de empresas, pessoas e CNPJs exibidos são **sintéticos**.

### Usuários de demonstração (tela de login)

Senha única: `demo123`

| Login | Perfil | O que a segurança faz |
|---|---|---|
| `joao` | 👔 Diretor | Acesso total: quadrante completo, qualquer carteira |
| `brenda` | 💼 Consultora — carteira privada (rep 001) | Filtro do representante injetado no código; dados de outros reps bloqueados |
| `hellena` | 🏛️ Consultora — canal público (rep 029) | "Cliente" vira município; carteira por cidade |

---

## Componentes

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Interface Streamlit: login de perfis, chat e bastidores (JSON Cube/SQL/regras/fluxo) |
| `fastapi_server.py` | API REST (streaming SSE + gestão de chats) para integração com frontends |
| `langgraph_app.py` | Orquestrador LangGraph: state machine, system prompt, RLS fail-closed |
| `tools.py` | Ferramentas de banco (psycopg + pool): busca fuzzy de reps/clientes/produtos, SQL livre com blocklist |
| `cube_tools.py` | Ferramenta Cube.js: executa queries JSON na camada semântica (JWT de curta duração) |
| `db_checkpointer.py` | Persiste checkpoints do LangGraph no Postgres (upsert `ON CONFLICT`) |
| `sync_cube_to_db.py` | Sincroniza metadados dos cubos para o dicionário de métricas |
| `regras/politica_comercial.md` | Caderno de regras de negócio (RAG): política comercial completa, injetada inteira no contexto do agente |
| `seed/` | Pipeline do banco demo: DDL + carga Olist/CMED/IBGE + camadas sintéticas + validação |
| `langgraph.json` | Registro do grafo para o LangSmith Studio (`langgraph dev`) |

### Camada Semântica — Cube.js (`cube_project/model/`)

| Cubo | Dados |
|---|---|
| `dw_vendas` | Faturamento, margem, positivação (privada e pública) e ticket médio |
| `dw_ranking_clientes` | Carteira de clientes com ranking ABC e histórico trimestral |
| `dw_ranking_municipios` | Carteira por município (canal público) |
| `dw_analise_credito` | Limite de crédito, inadimplência e potencial de compra |
| `premiacoes_metas` | Metas mensais por representante (faturamento, margem, ticket, positivação) |
| `dw_estoque_produto_pai` | Estoque consolidado por produto-pai (catálogo CMED) |

### Tabelas do banco (criadas pelo pipeline `seed/`)

- **Domínio (`tb_*`)** — cidades (com código IBGE), clientes, produtos, representantes, departamentos, funcionários, grupos
- **Analíticas (`dw_*`)** — fato de vendas + snapshots mensais de carteira + crédito + estoque + metas
- **Infraestrutura (`ai_*`)** — `ai_chats` (sessões), `ai_conversas` (auditoria pergunta/resposta/SQL), `ai_sessao_chat` (checkpoints LangGraph), `ai_controle_metricas` (dicionário de métricas)

---

## Funcionalidades

- **Linguagem natural em português** — sem necessidade de SQL
- **Multi-ferramenta** — o agente escolhe autonomamente entre buscas de cadastro, Cube.js e SQL direto
- **Row-Level Security em código (fail closed)** — filtros de representante/departamento injetados pelo `secure_tool_node` antes de qualquer execução; se o filtro falhar, a consulta é bloqueada. Não depende do LLM obedecer
- **Regras de negócio em contexto (RAG)** — a política comercial (alçadas de desconto, bloqueio por inadimplência, teto PMVG no canal público, RDC 471/Portaria 344, cadeia fria...) entra **inteira** no contexto do agente, que cita a regra aplicável ao limitar uma resposta. Fórmulas ficam no SQL da camada semântica; regras descritivas ficam no caderno versionado `regras/`
- **LLM configurável** — OpenAI GPT-5.1 ou Claude Sonnet 5, trocável por variável de ambiente
- **Recuperação de sessão** — histórico persiste via checkpointer no Postgres
- **Streaming SSE** — respostas em tempo real para frontends via FastAPI
- **Auditoria completa** — pares pergunta/resposta + SQL executado gravados no banco
- **Proteção de SQL** — apenas SELECT + blocklist de padrões perigosos do Postgres (`pg_sleep`, `pg_catalog`, `information_schema`, DML/DDL...)
- **Observabilidade** — tracing completo no LangSmith e visualização do grafo no Studio
- **Cache de contexto** — data do banco e allowlist de métricas cacheadas entre re-entradas do agente

---

## Decisões de arquitetura (o "porquê")

Mais importante que as ferramentas usadas são as decisões por trás delas:

- **Camada semântica (Cube.js) em vez de text-to-SQL cru.** Deixar o LLM escrever SQL livre contra o schema é frágil: ele erra join, inventa coluna, e não há garantia de que a métrica de "faturamento" é sempre a mesma. Com o Cube, as métricas (faturamento, margem, positivação, ticket médio) são **definidas uma vez** em YAML e o agente só escolhe *quais* pedir — a fórmula é sempre a mesma, versionada e testável. O agente fica mais simples e as respostas, consistentes.

- **Segurança (RLS) forçada em código, não confiando no prompt.** A regra "consultor só vê a própria carteira" **não** pode depender do LLM obedecer a uma instrução — um prompt bem construído contorna qualquer instrução. Por isso o `secure_tool_node` intercepta toda chamada de ferramenta e **injeta o filtro do representante antes de executar**, com política *fail closed*: se o filtro não puder ser aplicado, a consulta é bloqueada. O prompt reforça, mas o código garante.

- **Regras de negócio no contexto, fórmulas na camada semântica.** Duas naturezas diferentes: regra descritiva ("desconto acima de 20% exige diretoria") vive em texto no caderno `regras/` e entra **inteira** no contexto do agente; cálculo ("margem = 1 − vendas/tabela") vive no SQL do Cube, onde é determinístico. Tentar fazer o LLM calcular, ou vetorizar e "buscar a regra mais próxima", foi descartado — ambos introduzem erro onde não deveria haver.

- **Dados reais re-datados em vez de 100% sintéticos.** Usar transações verdadeiras do Olist (com re-datação para uma janela recente) dá volumetria, sazonalidade e distribuição realistas que dados inventados não teriam — e o catálogo CMED ancora o cenário no tema farmacêutico. O sintético fica só para o que não existe em fonte pública (representantes, metas, crédito), derivado do próprio histórico para manter coerência.

- **LLM plugável (OpenAI ou Anthropic).** O provedor é uma variável de ambiente, não uma dependência cravada — troca-se de GPT-5.1 para Claude Sonnet 5 sem tocar no código do agente. Facilita comparar custo/qualidade e não amarra o projeto a um fornecedor.

---

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| LLM | OpenAI GPT-5.1 **ou** Anthropic Claude Sonnet 5 (via LangChain, configurável) |
| Orquestração | LangGraph (agentic workflow com state machine) |
| Banco de dados | PostgreSQL 17 no Supabase (`psycopg` + connection pool) |
| Camada semântica | Cube.js (Docker) |
| Backend API | FastAPI + Uvicorn (SSE streaming) |
| Interface | Streamlit (com login de perfis) |
| Observabilidade | LangSmith (tracing) + LangSmith Studio (`langgraph dev`) |

---

## Como rodar localmente

### Pré-requisitos

- Python 3.12+ · Docker Desktop · conta gratuita no [Supabase](https://supabase.com)
- Chave de API da OpenAI **ou** da Anthropic
- CSVs do Olist ([Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)) em `data/olist/`, planilha PMC da [CMED](https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos) em `data/cmed/` e municípios do IBGE (`https://servicodados.ibge.gov.br/api/v1/localidades/municipios`) em `data/ibge/municipios.json`

### 1. Clonar e instalar

```bash
git clone https://github.com/RaulRMO10/BI_COPILOT.git
cd BI_COPILOT
python -m venv .venv
.venv\Scripts\activate        # Windows | source .venv/bin/activate no Linux/macOS
pip install -r requirements.txt
```

### 2. Configurar o `.env`

```bash
cp .env.example .env
```

Principais variáveis (ver [.env.example](.env.example)):

```
DATABASE_URL=      # URI do session pooler do Supabase (porta 5432, sslmode=require)
LLM_PROVIDER=      # openai | anthropic
LLM_MODEL=         # ex.: gpt-5.1 | claude-sonnet-5
OPENAI_API_KEY=    # e/ou ANTHROPIC_API_KEY, conforme o provider
CUBEJS_API_SECRET= # mesma secret do cube_project/.env
LANGSMITH_API_KEY= # opcional — tracing
```

### 3. Construir o banco demo (uma vez)

```bash
python -m seed.load_olist        # DDL + staging (Olist + CMED + IBGE)
python -m seed.build_dominio     # cidades, clientes, produtos, reps...
python -m seed.build_vendas      # fato de vendas re-datado + recorrência
python -m seed.build_snapshots   # carteiras mensais com ranking ABC
python -m seed.build_sinteticos  # metas, crédito, estoque
python -m seed.validate          # checks de sanidade
python sync_cube_to_db.py        # dicionário de métricas (ai_controle_metricas)
```

### 4. Subir o Cube.js

```bash
cd cube_project
cp .env.example .env             # aponte para o mesmo Supabase (CUBEJS_DB_SSL=true)
docker compose up -d
```

### 5. Abrir a interface

```bash
streamlit run app.py             # http://localhost:8501 — login: joao/brenda/hellena, senha demo123
```

Opcionais:

```bash
uvicorn fastapi_server:app --host 127.0.0.1 --port 8000   # API REST p/ frontends
langgraph dev                                              # grafo visual no LangSmith Studio
```

### Demo pública (opcional)

Há um **modo demo** com login Google, limite de perguntas por pessoa e feedback,
pensado para hospedar no Hugging Face Spaces (`DEMO_MODE=true`). Passo a passo em
[DEPLOY.md](DEPLOY.md).

---

## Segurança implementada

- **RLS forçada em código, fail closed** — o `secure_tool_node` injeta o filtro do representante/departamento em toda consulta de consultor; em erro de validação, a consulta é bloqueada (nunca "passa sem filtro")
- **Dimensões sensíveis bloqueadas** — consultores não conseguem listar outros representantes/vendedores, mesmo pedindo explicitamente
- **Somente SELECT + blocklist Postgres** na ferramenta de SQL livre (`pg_sleep`, `pg_read_file`, `information_schema`, DML/DDL, `dblink`...)
- **Autenticação Bearer Token** nos endpoints da API + **CORS restrito** + **headers de segurança HTTP**
- **JWT de curta duração** (1h) gerado a cada request para o Cube.js
- **Auditoria** — SQLs executados e pares pergunta/resposta gravados no banco
- **Teste de drift** — verificação automatizada de que os members citados nos mapas de segurança existem nos YAMLs do Cube

---

## Estrutura de pastas

```
bi-copilot/
├── app.py                    # Interface Streamlit (login + chat + bastidores)
├── fastapi_server.py         # API REST (bridge frontend ↔ LangGraph)
├── langgraph_app.py          # Orquestrador, system prompt e RLS do agente
├── tools.py                  # Ferramentas de banco (search fuzzy + SQL livre)
├── cube_tools.py             # Ferramenta Cube.js
├── db_checkpointer.py        # Persistência de estado LangGraph (Postgres)
├── sync_cube_to_db.py        # Pipeline: YAML Cube → dicionário de métricas
├── langgraph.json            # Registro do grafo p/ LangSmith Studio
├── regras/                   # Caderno de regras de negócio (RAG em contexto)
├── seed/                     # Pipeline do banco demo (DDL + cargas + validação)
├── data/                     # CSVs de origem (gitignorado)
├── requirements.txt
├── .env.example
└── cube_project/
    ├── docker-compose.yml
    ├── .env.example
    └── model/                # 6 cubos YAML da camada semântica
```

---

## Roadmap

- Golden questions automatizadas por perfil (pytest) + teste de drift no CI
- Prompt caching explícito para reduzir custo por pergunta
- Deploy do demo (Streamlit Community Cloud + Cube Cloud)

---

## Autor

**Raul Martins** · [GitHub @RaulRMO10](https://github.com/RaulRMO10) · [LinkedIn](https://www.linkedin.com/in/raulrmo/)

---

## Licença

MIT — o código. Os dados de demonstração seguem as licenças das fontes: Olist ([CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)), CMED/ANVISA e IBGE (dados públicos).
