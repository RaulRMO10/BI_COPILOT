-- ═══════════════════════════════════════════════════════════════════════════
-- BI COPILOT — Tabelas de infraestrutura do agente (AI_*) · PostgreSQL
-- AI_SESSAO_CHAT: checkpoints do LangGraph (DBCheckpointSaver)
-- AI_CHATS/AI_CONVERSAS: metadados e auditoria (fastapi_server)
-- AI_CONTROLE_METRICAS: allowlist de métricas do prompt (sync_cube_to_db)
-- Idempotente: CREATE IF NOT EXISTS (não derruba histórico de conversas).
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS ai_sessao_chat (
    session_id      TEXT NOT NULL,
    checkpoint_id   TEXT NOT NULL,
    checkpoint_data TEXT,
    metadata        TEXT,
    created_at      TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo'),
    PRIMARY KEY (session_id, checkpoint_id)
);
CREATE INDEX IF NOT EXISTS idx_ai_sessao_created ON ai_sessao_chat (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_chats (
    session_id  TEXT PRIMARY KEY,
    funcionario TEXT,
    titulo      TEXT,
    created_at  TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo')
);
CREATE INDEX IF NOT EXISTS idx_ai_chats_func ON ai_chats (funcionario, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_conversas (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id    TEXT,
    funcionario   TEXT,
    pergunta      TEXT,
    resposta      TEXT,
    sql_executado TEXT,
    created_at    TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo')
);

CREATE TABLE IF NOT EXISTS ai_controle_metricas (
    nome_metrica TEXT PRIMARY KEY,
    tipo         TEXT,
    cube_fonte   TEXT,
    status       TEXT DEFAULT 'INATIVA'
);
