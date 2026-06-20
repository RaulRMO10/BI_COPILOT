# BI Copilot — Assistente Comercial com IA Generativa

Sistema de Business Intelligence conversacional que permite consultar indicadores comerciais em **linguagem natural** (português). O usuário faz perguntas como _"Qual foi o faturamento da Ana em março?"_ e o agente decide automaticamente qual ferramenta usar, executa a query e devolve uma resposta formatada.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agentic-1C3C3C)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--5.4--mini-412991?logo=openai&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Cube.js](https://img.shields.io/badge/Cube.js-Semantic_Layer-FF6492)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-FAC51C)

> 🖼️ _Screenshot/GIF da interface conversacional aqui — mostre uma pergunta real e a resposta formatada._

> ℹ️ **Sobre este projeto:** desenvolvido originalmente em ambiente profissional e disponibilizado aqui **com autorização**, para fins de estudo e portfólio (pós-graduação em **Agentes de IA — FIAP**). Credenciais e dados reais foram removidos; nomes de tabelas e exemplos são ilustrativos.

---

## Demonstração

```
Usuário: Qual o ranking dos meus clientes inativos este mês?

Assistente: [consulta a camada semântica Cube.js]
Encontrei 12 clientes no ranking RED e 3 sem nenhuma venda em abril/2025.
Os 5 com maior histórico de compra são: ...
```

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  Interface Web                                              │
│  Streamlit (app.py) ──────► FastAPI (fastapi_server.py)     │
│                                      │                      │
│                          LangGraph Agentic Workflow          │
│                          (langgraph_app.py)                  │
│                                      │                      │
│              ┌───────────────────────┼──────────────────┐   │
│              ▼                       ▼                   ▼   │
│         Banco de Dados        Cube.js Semantic       ChromaDB │
│         (tools.py)           Layer (cube_tools.py)  (RAG)    │
└─────────────────────────────────────────────────────────────┘
```

### Fluxo de uma pergunta

1. Usuário digita a pergunta na UI (Streamlit ou via API REST)
2. FastAPI autentica o token e repassa ao LangGraph
3. O agente (GPT-5.4-mini) raciocina e escolhe qual ferramenta chamar
4. A ferramenta executa a query (Cube.js ou SQL direto) e retorna JSON
5. O agente interpreta o resultado e gera a resposta em português
6. O histórico é persistido no banco para retomada em sessões futuras

---

## Componentes

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Interface Streamlit com histórico e abas de debug |
| `fastapi_server.py` | API REST (streaming SSE + endpoints de gestão de chats) |
| `langgraph_app.py` | Orquestrador LangGraph: state machine, system prompt, RLS |
| `tools.py` | Ferramentas de banco: busca fuzzy de representantes, clientes, produtos |
| `cube_tools.py` | Ferramenta Cube.js: executa queries JSON na camada semântica |
| `db_checkpointer.py` | Persiste checkpoints do LangGraph no banco |
| `sync_cube_to_db.py` | Sincroniza metadados do Cube.js para o banco (dicionário de métricas) |
| `sync_regras_to_chroma.py` | Vetoriza regras de negócio do banco para ChromaDB (RAG) |

### Camada Semântica — Cube.js (`cube_project/model/`)

| Cubo | Dados |
|---|---|
| `dw_vendas` | Faturamento, margem, positivação e ticket médio por representante/dia |
| `dw_carteira_clientes` | Carteira de clientes com ranking ABC e histórico trimestral |
| `dw_carteira_municipios` | Carteira por município (setor público) |
| `dw_analise_credito` | Limite de crédito, inadimplência e potencial de compra |
| `premiacoes_metas` | Metas mensais por representante (faturamento, margem, positivação) |
| `dw_estoque_produto_pai` | Estoque consolidado por produto-pai |

### Tabelas de domínio consultadas pelo agente

| Tabela | Conteúdo |
|---|---|
| `TB_FUNCIONARIOS` | Cadastro de funcionários (tipo, departamento, representante) |
| `TB_REPRESENTANTES` | Dados dos representantes comerciais |
| `TB_DEPARTAMENTOS` | Cadastro de departamentos |
| `TB_GRUPOS_CLIENTES` | Grupos de clientes |
| `TB_CIDADES` | Cidades e municípios |
| `TB_PRODUTOS` | Catálogo de produtos |
| `TB_CLIENTES` | Cadastro de clientes (CNPJ, razão social) |

### Tabelas de infraestrutura criadas pelo sistema

| Tabela | Uso |
|---|---|
| `AI_CHATS` | Metadados de sessões de chat por usuário |
| `AI_CONVERSAS` | Auditoria completa: pergunta, resposta e SQL executado |
| `AI_SESSAO_CHAT` | Checkpoints LangGraph (retomada de conversa) |
| `AI_CONTROLE_METRICAS` | Dicionário de métricas/dimensões do Cube.js |
| `AI_REGRAS_NEGOCIO` | Regras de negócio para RAG (vetorizadas no ChromaDB) |

---

## Funcionalidades

- **Linguagem natural em português** — sem necessidade de SQL
- **Multi-ferramenta** — o agente escolhe autonomamente entre banco, Cube.js e RAG
- **Row-Level Security (RLS)** — representantes veem apenas seus próprios dados, aplicado no código (não depende do LLM obedecer)
- **Recuperação de sessão** — histórico persiste via checkpointer no banco
- **Streaming SSE** — respostas em tempo real para o frontend
- **Auditoria completa** — todo par pergunta/resposta + SQL executado é gravado
- **Proteção contra SQL injection** — blocklist de padrões perigosos + apenas SELECT
- **RAG com regras de negócio** — ChromaDB fornece contexto de domínio ao agente
- **Cache de contexto** — evita queries repetidas ao banco a cada re-entrada do agente

---

## Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| LLM | OpenAI GPT-5.4-mini via LangChain |
| Orquestração | LangGraph (agentic workflow com state machine) |
| Backend API | FastAPI + Uvicorn (SSE streaming) |
| Interface | Streamlit |
| Banco de dados | Relacional (via `oracledb` connection pool) |
| Camada semântica | Cube.js (Docker) |
| Vetores (RAG) | ChromaDB + OpenAI text-embedding-3-small |
| Monitoramento | LangSmith (tracing opcional) |

---

## Como rodar localmente

### Pré-requisitos

- Python 3.11+
- Banco de dados relacional acessível
- Cube.js rodando (ver `cube_project/`)
- Chave de API OpenAI

### 1. Clonar e instalar dependências

```bash
git clone https://github.com/RaulRMO10/BI_COPILOT.git
cd BI_COPILOT
python -m venv .venv
.venv\Scripts\activate        # Windows
# ou: source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

Variáveis necessárias (ver [.env.example](.env.example)):

```
DB_USER=          # usuário do banco
DB_PASSWORD=      # senha do banco
DB_DSN=           # host:porta/service_name
OPENAI_API_KEY=   # chave OpenAI
CUBEJS_API_SECRET=# secret compartilhada com Cube.js
CUBE_API_BASE_URL=# URL do Cube.js (ex: http://localhost:4000)
IA_FASTAPI_SECRET_TOKEN= # token de autenticação da API
```

### 3. Criar tabelas no banco

> **Nota:** O sistema usa dois conjuntos de tabelas:
> - **Tabelas de infraestrutura** (`AI_*`) — criadas pelos scripts abaixo, para persistência do agente.
> - **Tabelas de domínio** (`TB_*`, `DW_*`) — representam os dados do seu negócio. Adapte os nomes conforme seu modelo de dados.

Execute no banco (como o usuário configurado no `DB_USER`):

```sql
-- Sessões de chat
CREATE TABLE AI_CHATS (
    SESSION_ID  VARCHAR2(100) PRIMARY KEY,
    FUNCIONARIO VARCHAR2(100),
    TITULO      VARCHAR2(300),
    CREATED_AT  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

-- Auditoria de conversas
CREATE TABLE AI_CONVERSAS (
    ID           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    SESSION_ID   VARCHAR2(100),
    FUNCIONARIO  VARCHAR2(100),
    PERGUNTA     CLOB,
    RESPOSTA     CLOB,
    SQL_EXECUTADO CLOB,
    CREATED_AT   TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

-- Checkpoints LangGraph
CREATE TABLE AI_SESSAO_CHAT (
    SESSION_ID      VARCHAR2(100),
    CHECKPOINT_ID   VARCHAR2(100),
    CHECKPOINT_DATA CLOB,
    METADATA        CLOB,
    CREATED_AT      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
    PRIMARY KEY (SESSION_ID, CHECKPOINT_ID)
);

-- Dicionário de métricas
CREATE TABLE AI_CONTROLE_METRICAS (
    NOME_METRICA VARCHAR2(200) PRIMARY KEY,
    TIPO         VARCHAR2(20),
    CUBE_FONTE   VARCHAR2(100),
    STATUS       VARCHAR2(10) DEFAULT 'INATIVA'
);

-- Regras de negócio para RAG
CREATE TABLE AI_REGRAS_NEGOCIO (
    ID            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CONTEXTO      VARCHAR2(200),
    REGRA         CLOB,
    TABELA_ALVO   VARCHAR2(100),
    PALAVRAS_CHAVE VARCHAR2(500),
    STATUS        VARCHAR2(10) DEFAULT 'ATIVA'
);
```

### 4. Iniciar o Cube.js

```bash
cd cube_project
cp .env.example .env
# Edite o .env com as credenciais do banco
docker-compose up -d
```

### 5. Sincronizar metadados

```bash
# Sincroniza os cubos do Cube.js para o banco
python sync_cube_to_db.py

# Vetoriza regras de negócio para o ChromaDB
python sync_regras_to_chroma.py
```

### 6. Iniciar os servidores

```bash
# Terminal 1 — FastAPI (modo API REST + streaming)
uvicorn fastapi_server:app --host 127.0.0.1 --port 8501

# Terminal 2 — Streamlit (interface de demonstração direta)
streamlit run app.py
```

---

## Segurança implementada

- **Autenticação Bearer Token** em todos os endpoints da API
- **Row-Level Security forçada em código** — filtros de representante injetados pelo LangGraph antes de qualquer tool call, independente do que o LLM decidir
- **SQL injection blocklist** — padrões perigosos (`DBMS_*`, `EXECUTE IMMEDIATE`, DDL, `SYS_CONTEXT`, etc.) bloqueados antes de qualquer execução
- **Somente SELECT** na ferramenta de SQL livre
- **JWT de curta duração** (1h) gerado a cada request para o Cube.js
- **CORS restrito** a origens configuradas
- **Headers de segurança HTTP** (`X-Frame-Options`, `X-Content-Type-Options`, etc.)
- **Auditoria de queries** — todos os SQLs executados ficam gravados

---

## Estrutura de pastas

```
bi-copilot/
├── app.py                    # Interface Streamlit
├── fastapi_server.py         # API REST (bridge frontend ↔ LangGraph)
├── langgraph_app.py          # Orquestrador e system prompt do agente
├── tools.py                  # Ferramentas de banco (search + SQL livre)
├── cube_tools.py             # Ferramenta Cube.js
├── db_checkpointer.py        # Persistência de estado LangGraph
├── sync_cube_to_db.py        # Pipeline: YAML Cube → banco (metadados)
├── sync_regras_to_chroma.py  # Pipeline: banco → ChromaDB (RAG)
├── requirements.txt
├── .env.example              # Template de variáveis de ambiente
├── .gitignore
└── cube_project/
    ├── docker-compose.yml
    ├── .env.example
    └── model/
        ├── dw_vendas.yaml
        ├── dw_ranking_clientes.yaml
        ├── dw_ranking_municipios.yaml
        ├── dw_analise_credito.yaml
        ├── premiacoes_metas.yaml
        └── dw_estoque_produto_pai.yaml
```

---

## Autor

**Raul Martins** · [GitHub @RaulRMO10](https://github.com/RaulRMO10) · [LinkedIn](https://www.linkedin.com/in/raulrmo/)

---

## Licença

MIT
