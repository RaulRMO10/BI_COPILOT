-- ═══════════════════════════════════════════════════════════════════════════
-- BI COPILOT — Tabelas do MODO DEMO PÚBLICO (controle de crédito + feedback)
-- Usadas apenas quando DEMO_MODE=true (demo hospedada na internet).
-- Idempotente: CREATE IF NOT EXISTS.
-- ═══════════════════════════════════════════════════════════════════════════

-- Cada visitante identificado (por e-mail do Google). Limite de perguntas por pessoa.
CREATE TABLE IF NOT EXISTS demo_usuarios (
    email          TEXT PRIMARY KEY,
    nome           TEXT,
    limite         INT DEFAULT 10,
    criado_em      TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo'),
    ultimo_acesso  TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo')
);

-- Uma linha por pergunta feita, com a resposta do agente e o SQL gerado.
-- Dá o consumo por pessoa, o disjuntor diário global E o histórico completo de Q&A.
CREATE TABLE IF NOT EXISTS demo_uso (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT,
    persona       TEXT,
    pergunta      TEXT,
    resposta      TEXT,
    sql_executado TEXT,
    criado_em     TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo')
);
CREATE INDEX IF NOT EXISTS idx_demo_uso_email ON demo_uso (email);
CREATE INDEX IF NOT EXISTS idx_demo_uso_dia ON demo_uso ((criado_em::date));

-- Feedback opcional (👍/👎 + comentário) — prova social e captação de contato.
CREATE TABLE IF NOT EXISTS demo_feedback (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email      TEXT,
    nome       TEXT,
    rating     TEXT,           -- 'positivo' | 'negativo'
    comentario TEXT,
    criado_em  TIMESTAMP DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo')
);
