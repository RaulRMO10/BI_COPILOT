# -*- coding: utf-8 -*-
"""Etapa 5 — camadas sintéticas derivadas do histórico: metas, crédito e estoque."""
from seed.config import connect


def frac(key_sql: str) -> str:
    """Fração determinística 0..1 derivada de md5 (reproduzível)."""
    return f"((('x' || substr(md5({key_sql}), 1, 6))::bit(24)::int) / 16777215.0)"


SQL_METAS = f"""
INSERT INTO dw_metas_comerciais (representante, mes_ano, tipo, valor)
WITH mensal AS (
    SELECT representante, date_trunc('month', data_nota)::date AS mes,
           SUM(total_liquido) AS fat,
           CASE WHEN SUM(total_tela) > 0
                THEN 100.0 * (1 - SUM(total_vendas) / SUM(total_tela)) ELSE 0 END AS margem,
           COUNT(DISTINCT cad_cgc) FILTER (WHERE total_liquido > 0) AS positivados
    FROM dw_vendas
    GROUP BY representante, date_trunc('month', data_nota)
),
base AS (
    SELECT m.representante, m.mes,
           AVG(h.fat)         AS fat_3m,
           AVG(h.margem)      AS margem_3m,
           AVG(h.positivados) AS pos_3m
    FROM mensal m
    JOIN mensal h ON h.representante = m.representante
               AND h.mes >= m.mes - interval '3 month' AND h.mes < m.mes
    WHERE m.mes > (SELECT max(mes) - interval '6 month' FROM mensal)
    GROUP BY m.representante, m.mes
)
SELECT representante, mes, t.tipo,
       CASE t.tipo
            WHEN 1 THEN round(fat_3m    * (1.05 + {frac("'m1' || representante || mes::text")} * 0.10), 2)
            WHEN 2 THEN round(margem_3m * (1.00 + {frac("'m2' || representante || mes::text")} * 0.10), 2)
            WHEN 3 THEN round(CASE WHEN pos_3m > 0 THEN fat_3m / pos_3m ELSE 0 END
                              * (1.03 + {frac("'m3' || representante || mes::text")} * 0.10), 2)
            WHEN 4 THEN ceil(pos_3m * (1.05 + {frac("'m4' || representante || mes::text")} * 0.12))
       END
FROM base CROSS JOIN (VALUES (1), (2), (3), (4)) AS t(tipo)
"""

SQL_CREDITO = f"""
INSERT INTO dw_credito_clientes
WITH s AS (
    SELECT v.cad_cgc,
           MAX(v.razao_social)  AS razao_social,
           MAX(v.representante) AS representante,
           MAX(v.departamento)  AS departamento,
           SUM(v.total_liquido) AS fat12,
           MAX(v.data_nota)     AS ultima
    FROM dw_vendas v
    WHERE v.data_nota >= (SELECT max(data_nota) - interval '12 month' FROM dw_vendas)
    GROUP BY v.cad_cgc
    HAVING SUM(v.total_liquido) > 0
),
p AS (
    SELECT cl.cad_cgc,
           AVG(CASE WHEN pay.payment_type = 'boleto' THEN 1.0 ELSE 0.0 END) AS pboleto
    FROM stg_orders o
    JOIN stg_customers sc    ON sc.customer_id = o.customer_id
    JOIN tb_clientes cl      ON cl.customer_unique_id = sc.customer_unique_id
    JOIN stg_payments_agg pay ON pay.order_id = o.order_id
    GROUP BY cl.cad_cgc
)
SELECT s.cad_cgc, s.razao_social, s.representante, s.departamento,
       GREATEST(1000, round(s.fat12 * 0.35, -2))                                        AS limite_credito,
       CASE WHEN {frac("'i' || s.cad_cgc")} < 0.12
            THEN round(GREATEST(1000, round(s.fat12 * 0.35, -2)) * (0.05 + 0.45 * {frac("'a' || s.cad_cgc")}), 2)
            ELSE 0 END                                                                  AS total_atrasado,
       round(s.fat12 / 12.0 * (0.30 + 0.90 * {frac("'v' || s.cad_cgc")}), 2)            AS total_a_vencer,
       round(s.fat12 / 12.0 * (0.30 + 0.90 * {frac("'v' || s.cad_cgc")})
             * (0.40 + 0.60 * {frac("'w' || s.cad_cgc")}), 2)                           AS total_a_vencer_30_dias,
       GREATEST(1000, round(s.fat12 * 0.35, -2))
         - CASE WHEN {frac("'i' || s.cad_cgc")} < 0.12
                THEN round(GREATEST(1000, round(s.fat12 * 0.35, -2)) * (0.05 + 0.45 * {frac("'a' || s.cad_cgc")}), 2)
                ELSE 0 END
         - round(s.fat12 / 12.0 * (0.30 + 0.90 * {frac("'v' || s.cad_cgc")}), 2)        AS total_disponivel_limite,
       CASE WHEN {frac("'i' || s.cad_cgc")} < 0.12
            THEN (5 + floor(115 * {frac("'d' || s.cad_cgc")}))::int ELSE 0 END          AS dias_atrasado,
       round(s.fat12 / 12.0 * (1.10 + 0.70 * {frac("'p' || s.cad_cgc")}), 2)            AS potencial_compra,
       CASE WHEN {frac("'i' || s.cad_cgc")} < 0.12 THEN 'SIM' ELSE 'NAO' END            AS inadimplente,
       CASE WHEN {frac("'i' || s.cad_cgc")} < 0.12 OR {frac("'s' || s.cad_cgc")} < 0.08
                 OR s.ultima < (SELECT max(data_nota) - interval '6 month' FROM dw_vendas)
            THEN 'SIM' ELSE 'NAO' END                                                   AS sujeito_analise_credito,
       CASE WHEN COALESCE(p.pboleto, 0) >= 0.5 THEN 'A PRAZO' ELSE 'A VISTA' END        AS condicao_pagamento,
       (SELECT max(data_nota) FROM dw_vendas)
         - (floor({frac("'l' || s.cad_cgc")} * 365))::int                               AS data_limite_credito
FROM s LEFT JOIN p ON p.cad_cgc = s.cad_cgc
"""

SQL_ESTOQUE = f"""
INSERT INTO dw_estoque_produtos
WITH giro AS (
    SELECT codigo_pro, COUNT(*) AS qtd
    FROM dw_vendas
    WHERE total_liquido > 0
    GROUP BY codigo_pro
),
base AS (
    SELECT p.codigo_pro, p.nome_produto, p.razao_social_lab, p.cad_cgc_industria, p.marca,
           GREATEST(3, ceil(COALESCE(g.qtd, 1) * (0.5 + 2.5 * {frac("'e' || p.codigo_pro")})))::int AS estoque,
           p.codigo_pai, p.produto_pai
    FROM tb_produtos p
    LEFT JOIN giro g ON g.codigo_pro = p.codigo_pro
)
SELECT codigo_pro, nome_produto, razao_social_lab, cad_cgc_industria, marca,
       estoque, codigo_pai, produto_pai,
       SUM(estoque) OVER (PARTITION BY codigo_pai)::int AS estoque_grupo
FROM base
"""


def main() -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE dw_metas_comerciais, dw_credito_clientes, dw_estoque_produtos")
        cur.execute(SQL_METAS)
        print(f"[metas] linhas: {cur.rowcount:,} (4 tipos x reps x 6 meses)")
        cur.execute(SQL_CREDITO)
        print(f"[credito] clientes: {cur.rowcount:,}")
        cur.execute(SQL_ESTOQUE)
        print(f"[estoque] produtos: {cur.rowcount:,}")
    conn.commit()
    conn.close()
    print("ETAPA 5 (sinteticos) OK")


if __name__ == "__main__":
    main()
