-- ═══════════════════════════════════════════════════════════════════════════
-- BI COPILOT — MODO DEMO · DDL do banco Supabase (PostgreSQL 17)
-- Camadas: stg_* (staging descartável) · tb_* (domínio) · dw_* (analítica)
-- Nomes de colunas espelham exatamente os `sql:` dos cubos YAML.
-- Idempotente: DROP + CREATE.
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── STAGING ────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS stg_orders CASCADE;
CREATE TABLE stg_orders (
    order_id                 TEXT PRIMARY KEY,
    customer_id              TEXT,
    order_status             TEXT,
    order_purchase_timestamp TIMESTAMP
);

DROP TABLE IF EXISTS stg_order_items CASCADE;
CREATE TABLE stg_order_items (
    order_id      TEXT,
    order_item_id INT,
    product_id    TEXT,
    price         NUMERIC(12,2),
    freight_value NUMERIC(12,2)
);

DROP TABLE IF EXISTS stg_customers CASCADE;
CREATE TABLE stg_customers (
    customer_id        TEXT PRIMARY KEY,
    customer_unique_id TEXT,
    customer_city      TEXT,
    customer_state     TEXT
);

DROP TABLE IF EXISTS stg_products CASCADE;
CREATE TABLE stg_products (
    product_id            TEXT PRIMARY KEY,
    product_category_name TEXT
);

DROP TABLE IF EXISTS stg_payments_agg CASCADE;
CREATE TABLE stg_payments_agg (
    order_id     TEXT PRIMARY KEY,
    payment_type TEXT
);

DROP TABLE IF EXISTS stg_cmed CASCADE;
CREATE TABLE stg_cmed (
    cmed_id     SERIAL PRIMARY KEY,
    substancia  TEXT,
    cnpj_lab    TEXT,
    laboratorio TEXT,
    produto     TEXT,
    apresentacao TEXT
);

DROP TABLE IF EXISTS stg_ibge CASCADE;
CREATE TABLE stg_ibge (
    codigo_ibge BIGINT PRIMARY KEY,
    nome        TEXT,
    uf          TEXT,
    regiao      TEXT
);

-- ─── DOMÍNIO (TB_*) ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS tb_departamentos CASCADE;
CREATE TABLE tb_departamentos (
    departamento      TEXT PRIMARY KEY,
    nome_departamento TEXT
);

DROP TABLE IF EXISTS tb_representantes CASCADE;
CREATE TABLE tb_representantes (
    representante      TEXT PRIMARY KEY,
    nome_representante TEXT,
    departamento       TEXT,
    regiao             TEXT
);

DROP TABLE IF EXISTS tb_funcionarios CASCADE;
CREATE TABLE tb_funcionarios (
    funcionario      TEXT PRIMARY KEY,
    nome_funcionario TEXT,
    tipo             INT,      -- 1 diretor · 2 supervisor · 3 consultor
    representante    TEXT      -- rep vinculado (consultores)
);

DROP TABLE IF EXISTS tb_cidades CASCADE;
CREATE TABLE tb_cidades (
    cidade        TEXT PRIMARY KEY,   -- ID 5 dígitos
    nome_cidade   TEXT,
    uf            TEXT,
    codigo_ibge   BIGINT,
    regiao        TEXT,
    representante TEXT,               -- rep dono do território
    departamento  TEXT                -- 001 privado · 002 público
);

DROP TABLE IF EXISTS tb_grupos_clientes CASCADE;
CREATE TABLE tb_grupos_clientes (
    codigo_grupo TEXT PRIMARY KEY,    -- 5 dígitos
    nome_grupo   TEXT
);

DROP TABLE IF EXISTS tb_clientes CASCADE;
CREATE TABLE tb_clientes (
    cad_cgc            TEXT PRIMARY KEY,  -- CNPJ (14 dígitos, DV válido)
    cad_cgc_id         TEXT,              -- ID interno
    codigo_exp         TEXT,              -- código externo sequencial
    razao_social       TEXT,
    nome_fantasia      TEXT,
    cidade             TEXT,
    codigo_grupo       TEXT,
    customer_unique_id TEXT               -- rastreabilidade Olist (não exposto)
);
CREATE INDEX idx_tb_clientes_uid ON tb_clientes (customer_unique_id);

DROP TABLE IF EXISTS tb_produtos CASCADE;
CREATE TABLE tb_produtos (
    codigo_pro         TEXT PRIMARY KEY,  -- 7 dígitos
    nome_produto       TEXT,
    marca              TEXT,
    codigo_pai         TEXT,
    produto_pai        TEXT,
    razao_social_lab   TEXT,
    cad_cgc_industria  TEXT,
    categoria_olist    TEXT,
    product_id         TEXT               -- rastreabilidade Olist
);
CREATE INDEX idx_tb_produtos_pid ON tb_produtos (product_id);

-- ─── ANALÍTICA (DW_*) ───────────────────────────────────────────────────────
DROP TABLE IF EXISTS dw_vendas CASCADE;
CREATE TABLE dw_vendas (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id         TEXT,
    data_nota          DATE,
    numero_nota        TEXT,
    pedido             TEXT,
    cad_cgc            TEXT,
    razao_social       TEXT,
    cidade             TEXT,
    nome_cidade        TEXT,
    uf                 TEXT,
    vendedor           TEXT,
    nome_vendedor      TEXT,
    departamento       TEXT,
    nome_departamento  TEXT,
    representante      TEXT,
    nome_representante TEXT,
    codigo_pro         TEXT,
    nome_produto       TEXT,
    marca              TEXT,
    codigo_grupo       TEXT,
    nome_grupo         TEXT,
    total_liquido      NUMERIC(14,2),
    total_bruto        NUMERIC(14,2),
    desconto           NUMERIC(14,2),
    total_custo        NUMERIC(14,2),
    total_vendas       NUMERIC(14,2),
    total_devolucao    NUMERIC(14,2),
    total_tela         NUMERIC(14,2)
);
CREATE INDEX idx_dwv_data  ON dw_vendas (data_nota);
CREATE INDEX idx_dwv_cgc   ON dw_vendas (cad_cgc);
CREATE INDEX idx_dwv_rep   ON dw_vendas (representante);
CREATE INDEX idx_dwv_cid   ON dw_vendas (cidade);
CREATE INDEX idx_dwv_pro   ON dw_vendas (codigo_pro);

DROP TABLE IF EXISTS dw_carteira_clientes CASCADE;
CREATE TABLE dw_carteira_clientes (
    cad_cgc                   TEXT,
    cad_cgc_id                TEXT,
    codigo_exp                TEXT,
    razao_social              TEXT,
    nome_fantazia             TEXT,   -- grafia do YAML (NOME_FANTAZIA)
    funcionario               TEXT,
    representante             TEXT,
    nome_representante        TEXT,
    departamento              TEXT,
    nome_departamento         TEXT,
    mes_ano                   TEXT,   -- 'MM/YYYY'
    mesatual                  NUMERIC(14,2),
    mes01                     NUMERIC(14,2),
    mes02                     NUMERIC(14,2),
    mes03                     NUMERIC(14,2),
    frequencia                INT,
    mesatual_margem           NUMERIC(8,2),
    mes01_margem              NUMERIC(8,2),
    mes02_margem              NUMERIC(8,2),
    mes03_margem              NUMERIC(8,2),
    media_margem              NUMERIC(8,2),
    total_vendas_fechado      NUMERIC(14,2),
    media_total_vendas_fechado NUMERIC(14,2),
    ranking                   TEXT,
    ultima_compra             DATE,
    PRIMARY KEY (cad_cgc, mes_ano)
);
CREATE INDEX idx_cart_cli_ref ON dw_carteira_clientes (mes_ano, representante);

DROP TABLE IF EXISTS dw_carteira_municipios CASCADE;
CREATE TABLE dw_carteira_municipios (
    cidade                    TEXT,
    nome_cidade               TEXT,
    estado                    TEXT,
    funcionario               TEXT,
    representante             TEXT,
    nome_representante        TEXT,
    departamento              TEXT,
    nome_departamento         TEXT,
    mes_ano                   TEXT,
    mesatual                  NUMERIC(14,2),
    mes01                     NUMERIC(14,2),
    mes02                     NUMERIC(14,2),
    mes03                     NUMERIC(14,2),
    frequencia                INT,
    mesatual_margem           NUMERIC(8,2),
    mes01_margem              NUMERIC(8,2),
    mes02_margem              NUMERIC(8,2),
    mes03_margem              NUMERIC(8,2),
    media_margem              NUMERIC(8,2),
    total_vendas_fechado      NUMERIC(14,2),
    media_total_vendas_fechado NUMERIC(14,2),
    ranking                   TEXT,
    ultima_compra             DATE,
    PRIMARY KEY (cidade, mes_ano)
);
CREATE INDEX idx_cart_mun_ref ON dw_carteira_municipios (mes_ano, representante);

DROP TABLE IF EXISTS dw_credito_clientes CASCADE;
CREATE TABLE dw_credito_clientes (
    cad_cgc                 TEXT PRIMARY KEY,
    razao_social            TEXT,
    representante           TEXT,
    departamento            TEXT,
    limite_credito          NUMERIC(14,2),
    total_atrasado          NUMERIC(14,2),
    total_a_vencer          NUMERIC(14,2),
    total_a_vencer_30_dias  NUMERIC(14,2),
    total_disponivel_limite NUMERIC(14,2),
    dias_atrasado           INT,
    potencial_compra        NUMERIC(14,2),
    inadimplente            TEXT,   -- 'SIM'/'NAO'
    sujeito_analise_credito TEXT,   -- 'SIM'/'NAO'
    condicao_pagamento      TEXT,   -- 'A VISTA'/'A PRAZO'
    data_limite_credito     DATE
);

DROP TABLE IF EXISTS dw_estoque_produtos CASCADE;
CREATE TABLE dw_estoque_produtos (
    codigo_pro        TEXT PRIMARY KEY,
    nome_produto      TEXT,
    razao_social      TEXT,   -- laboratório
    cad_cgc_industria TEXT,
    marca             TEXT,
    estoque           INT,
    codigo_pai        TEXT,
    produto_pai       TEXT,
    estoque_grupo     INT
);
CREATE INDEX idx_estq_pai ON dw_estoque_produtos (codigo_pai);

DROP TABLE IF EXISTS dw_metas_comerciais CASCADE;
CREATE TABLE dw_metas_comerciais (
    representante TEXT,
    mes_ano       DATE,    -- 1º dia do mês
    tipo          INT,     -- 1 faturamento · 2 margem · 3 ticket · 4 positivação
    valor         NUMERIC(14,2),
    PRIMARY KEY (representante, mes_ano, tipo)
);
