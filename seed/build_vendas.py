# -*- coding: utf-8 -*-
"""Etapa 3 — DW_VENDAS: fato re-datado (grão = item de nota) + devoluções."""
from datetime import date, timedelta

from seed.config import connect

# fração determinística 0..1 a partir de md5 (reproduzível em qualquer sessão)
FRAC = "((('x' || substr(md5({key}), 1, 6))::bit(24)::int) / 16777215.0)"

BASE_JOIN = """
    FROM stg_order_items i
    JOIN stg_orders o        ON o.order_id = i.order_id
    JOIN stg_customers sc    ON sc.customer_id = o.customer_id
    JOIN tb_clientes cl      ON cl.customer_unique_id = sc.customer_unique_id
    JOIN tb_cidades ci       ON ci.cidade = cl.cidade
    JOIN tb_representantes r ON r.representante = ci.representante
    JOIN tb_departamentos d  ON d.departamento = ci.departamento
    JOIN tb_funcionarios f   ON f.representante = r.representante AND f.tipo = 3
    JOIN tb_produtos p       ON p.product_id = i.product_id
    LEFT JOIN tb_grupos_clientes g ON g.codigo_grupo = cl.codigo_grupo
"""

COMMON_COLS = """
    '001', {data_expr},
    lpad((((('x' || substr(md5(o.order_id), 1, 8))::bit(32)::bigint & 8388607) % 900000) + 100000)::text, 6, '0'),
    upper(substr(md5(o.order_id), 1, 8)),
    cl.cad_cgc, cl.razao_social, ci.cidade, ci.nome_cidade, ci.uf,
    f.funcionario, f.nome_funcionario, ci.departamento, d.nome_departamento,
    r.representante, r.nome_representante,
    p.codigo_pro, p.nome_produto, p.marca, cl.codigo_grupo, g.nome_grupo
"""

INSERT_COLS = """(empresa_id, data_nota, numero_nota, pedido, cad_cgc, razao_social,
    cidade, nome_cidade, uf, vendedor, nome_vendedor, departamento, nome_departamento,
    representante, nome_representante, codigo_pro, nome_produto, marca, codigo_grupo, nome_grupo,
    total_liquido, total_bruto, desconto, total_custo, total_vendas, total_devolucao, total_tela)"""


def main() -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE dw_vendas RESTART IDENTITY")
        # âncora = última compra que gera linha de venda de fato (com item e status válido);
        # o rabo do Olist (set-out/2018) é esparso/cancelado e não pode ancorar o "mês atual"
        cur.execute("""
            SELECT max(o.order_purchase_timestamp)::date
            FROM stg_orders o
            JOIN stg_order_items i ON i.order_id = o.order_id
            WHERE o.order_status IN ('delivered','shipped','invoiced','processing','approved')
        """)
        max_d = cur.fetchone()[0]
    yesterday = date.today() - timedelta(days=1)
    offset = ((yesterday - max_d).days // 7) * 7
    print(f"[vendas] re-datacao: +{offset} dias (multiplo de 7) | "
          f"{max_d} -> {max_d + timedelta(days=offset)}")

    tela_key = "'t' || p.codigo_pro"
    custo_key = "'c' || p.codigo_pro"
    tela_f = f"(1.05 + {FRAC.format(key=tela_key)} * 0.30)"
    custo_f = f"(0.60 + {FRAC.format(key=custo_key)} * 0.25)"
    data_venda = f"(o.order_purchase_timestamp + make_interval(days => {offset}))::date"
    # devolução ~7 dias depois da compra (preserva dia da semana), sem passar de ontem
    data_devol = (f"LEAST((o.order_purchase_timestamp + make_interval(days => {offset + 7}))::date, "
                  f"DATE '{yesterday}')")

    with conn.cursor() as cur:
        # vendas normais (inclui as que depois serão devolvidas — narrativa completa)
        cur.execute(f"""
            INSERT INTO dw_vendas {INSERT_COLS}
            SELECT {COMMON_COLS.format(data_expr=data_venda)},
                   i.price,
                   i.price + COALESCE(i.freight_value, 0),
                   round(i.price * {tela_f}, 2) - i.price,
                   round(i.price * {custo_f}, 2),
                   i.price,
                   0,
                   round(i.price * {tela_f}, 2)
            {BASE_JOIN}
            WHERE o.order_status IN ('delivered','shipped','invoiced','processing','approved','canceled')
        """)
        n_vendas = cur.rowcount
        # devoluções: pedidos cancelados geram linha espelho negativa
        cur.execute(f"""
            INSERT INTO dw_vendas {INSERT_COLS}
            SELECT {COMMON_COLS.format(data_expr=data_devol)},
                   -i.price,
                   -(i.price + COALESCE(i.freight_value, 0)),
                   0,
                   -round(i.price * {custo_f}, 2),
                   0,
                   i.price,
                   0
            {BASE_JOIN}
            WHERE o.order_status = 'canceled'
        """)
        n_dev = cur.rowcount
    conn.commit()
    print(f"[vendas] linhas de venda: {n_vendas:,} | devolucoes: {n_dev:,}")

    # ── recorrência sintética ────────────────────────────────────────────────
    # Olist é e-commerce (compra única); uma distribuidora B2B tem base fiel
    # mensal. Os maiores clientes + prefeituras ganham pedidos recorrentes:
    # clone da "cesta padrão" (melhor pedido) com dia e valor variados de forma
    # determinística. Sem isso não existem clientes OURO/PRATA na carteira.
    def fr(key: str) -> str:
        return f"((('x' || substr(md5({key}), 1, 6))::bit(24)::int) / 16777215.0)"

    with conn.cursor() as cur:
        cur.execute("SELECT max(data_nota), min(data_nota) FROM dw_vendas")
        max_data, min_data = cur.fetchone()
        k_dia = "'d' || c.cad_cgc || m.mes::text"
        k_hit = "'r' || c.cad_cgc || m.mes::text"
        k_fat = "'f' || c.cad_cgc || m.mes::text"
        k_id = "c.cad_cgc || m.mes::text"
        cur.execute(f"""
            INSERT INTO dw_vendas {INSERT_COLS}
            WITH alvo AS (
                SELECT cad_cgc FROM (
                    SELECT cad_cgc, SUM(total_liquido) s FROM dw_vendas
                    GROUP BY cad_cgc ORDER BY s DESC LIMIT 3000) t
                UNION
                SELECT cad_cgc FROM tb_clientes WHERE razao_social LIKE 'PREFEITURA%%'
            ),
            melhor_pedido AS (
                SELECT cad_cgc, pedido FROM (
                    SELECT v.cad_cgc, v.pedido, SUM(v.total_liquido) s,
                           ROW_NUMBER() OVER (PARTITION BY v.cad_cgc ORDER BY SUM(v.total_liquido) DESC, v.pedido) rn
                    FROM dw_vendas v JOIN alvo a USING (cad_cgc)
                    WHERE v.total_liquido > 0
                    GROUP BY v.cad_cgc, v.pedido) x
                WHERE rn = 1
            ),
            cesta AS (
                SELECT v.* FROM dw_vendas v
                JOIN melhor_pedido mp ON mp.cad_cgc = v.cad_cgc AND mp.pedido = v.pedido
                WHERE v.total_liquido > 0
            ),
            meses AS (
                SELECT generate_series(date_trunc('month', %s::date + interval '1 month'),
                                       date_trunc('month', %s::date),
                                       interval '1 month')::date AS mes
            )
            SELECT c.empresa_id,
                   m.mes + (floor({fr(k_dia)} * 27))::int,
                   lpad((((('x' || substr(md5('n' || {k_id}), 1, 8))::bit(32)::bigint & 8388607) %% 900000) + 100000)::text, 6, '0'),
                   upper(substr(md5({k_id}), 1, 8)),
                   c.cad_cgc, c.razao_social, c.cidade, c.nome_cidade, c.uf,
                   c.vendedor, c.nome_vendedor, c.departamento, c.nome_departamento,
                   c.representante, c.nome_representante,
                   c.codigo_pro, c.nome_produto, c.marca, c.codigo_grupo, c.nome_grupo,
                   round(c.total_liquido * (0.70 + 0.60 * {fr(k_fat)}), 2),
                   round(c.total_bruto   * (0.70 + 0.60 * {fr(k_fat)}), 2),
                   round(c.total_tela * (0.70 + 0.60 * {fr(k_fat)}), 2)
                     - round(c.total_vendas * (0.70 + 0.60 * {fr(k_fat)}), 2),
                   round(c.total_custo   * (0.70 + 0.60 * {fr(k_fat)}), 2),
                   round(c.total_vendas  * (0.70 + 0.60 * {fr(k_fat)}), 2),
                   0,
                   round(c.total_tela    * (0.70 + 0.60 * {fr(k_fat)}), 2)
            FROM cesta c
            CROSS JOIN meses m
            WHERE {fr(k_hit)} < 0.72
              AND m.mes <> date_trunc('month', c.data_nota)::date
              AND m.mes + (floor({fr(k_dia)} * 27))::int <= %s::date
        """, (min_data, max_data, max_data))
        n_rec = cur.rowcount
    conn.commit()
    print(f"[vendas] recorrencia sintetica (base fiel): {n_rec:,} linhas")

    with conn.cursor() as cur:
        cur.execute("""SELECT min(data_nota), max(data_nota),
                              round(sum(total_liquido)), count(DISTINCT cad_cgc) FROM dw_vendas""")
        mn, mx, fat, ncli = cur.fetchone()
    print(f"[vendas] janela: {mn} a {mx} | fat. liquido total: R$ {fat:,.0f} | clientes: {ncli:,}")
    conn.close()
    print("ETAPA 3 (dw_vendas) OK")


if __name__ == "__main__":
    main()
