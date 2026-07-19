# -*- coding: utf-8 -*-
"""Etapa 4 — snapshots mensais de carteira (clientes e municípios) com ranking ABC."""
from seed.config import connect

N_REFS = 4  # mês corrente + 3 anteriores

SQL_CLIENTES = """
INSERT INTO dw_carteira_clientes
SELECT s.cad_cgc, cl.cad_cgc_id, cl.codigo_exp, cl.razao_social, cl.nome_fantasia,
       f.funcionario, r.representante, r.nome_representante, ci.departamento, d.nome_departamento,
       to_char(%(ref)s::date, 'MM/YYYY'),
       s.mesatual, s.mes01, s.mes02, s.mes03, s.frequencia,
       s.mesatual_margem, s.mes01_margem, s.mes02_margem, s.mes03_margem,
       round((s.mes01_margem + s.mes02_margem + s.mes03_margem) / 3.0, 2),
       s.mes01 + s.mes02 + s.mes03,
       round((s.mes01 + s.mes02 + s.mes03) / NULLIF(s.frequencia, 0), 2),
       CASE WHEN s.frequencia = 3 THEN '1-OURO'
            WHEN s.frequencia = 2 THEN '2-PRATA'
            WHEN s.frequencia = 1 THEN '3-BRONZE'
            WHEN s.mesatual > 0   THEN '3-BRONZE'
            WHEN s.ultima_compra IS NOT NULL THEN '4-RED'
            ELSE '5-NENHUMA VENDA' END,
       s.ultima_compra
FROM (
    SELECT v.cad_cgc,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date), 0) AS mesatual,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '1 month'), 0) AS mes01,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '2 month'), 0) AS mes02,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '3 month'), 0) AS mes03,
           (COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '1 month'), 0) > 0)::int
         + (COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '2 month'), 0) > 0)::int
         + (COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '3 month'), 0) > 0)::int AS frequencia,
           {margem_atual} AS mesatual_margem,
           {margem_m1} AS mes01_margem,
           {margem_m2} AS mes02_margem,
           {margem_m3} AS mes03_margem,
           MAX(v.data_nota) FILTER (WHERE v.total_liquido > 0) AS ultima_compra
    FROM dw_vendas v
    WHERE v.data_nota >= %(ref)s::date - interval '11 month'
      AND v.data_nota <  %(ref)s::date + interval '1 month'
    GROUP BY v.cad_cgc
) s
JOIN tb_clientes cl      ON cl.cad_cgc = s.cad_cgc
JOIN tb_cidades ci       ON ci.cidade = cl.cidade
JOIN tb_representantes r ON r.representante = ci.representante
JOIN tb_departamentos d  ON d.departamento = ci.departamento
JOIN tb_funcionarios f   ON f.representante = r.representante AND f.tipo = 3
"""

SQL_MUNICIPIOS = """
INSERT INTO dw_carteira_municipios
SELECT s.cidade, ci.nome_cidade, ci.uf,
       f.funcionario, r.representante, r.nome_representante, ci.departamento, d.nome_departamento,
       to_char(%(ref)s::date, 'MM/YYYY'),
       s.mesatual, s.mes01, s.mes02, s.mes03, s.frequencia,
       s.mesatual_margem, s.mes01_margem, s.mes02_margem, s.mes03_margem,
       round((s.mes01_margem + s.mes02_margem + s.mes03_margem) / 3.0, 2),
       s.mes01 + s.mes02 + s.mes03,
       round((s.mes01 + s.mes02 + s.mes03) / NULLIF(s.frequencia, 0), 2),
       CASE WHEN s.frequencia = 3 THEN '1-OURO'
            WHEN s.frequencia = 2 THEN '2-PRATA'
            WHEN s.frequencia = 1 THEN '3-BRONZE'
            WHEN s.mesatual > 0   THEN '3-BRONZE'
            WHEN s.ultima_compra IS NOT NULL THEN '4-RED'
            ELSE '5-NENHUMA VENDA' END,
       s.ultima_compra
FROM (
    SELECT v.cidade,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date), 0) AS mesatual,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '1 month'), 0) AS mes01,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '2 month'), 0) AS mes02,
           COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '3 month'), 0) AS mes03,
           (COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '1 month'), 0) > 0)::int
         + (COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '2 month'), 0) > 0)::int
         + (COALESCE(SUM(v.total_liquido) FILTER (WHERE date_trunc('month', v.data_nota) = %(ref)s::date - interval '3 month'), 0) > 0)::int AS frequencia,
           {margem_atual} AS mesatual_margem,
           {margem_m1} AS mes01_margem,
           {margem_m2} AS mes02_margem,
           {margem_m3} AS mes03_margem,
           MAX(v.data_nota) FILTER (WHERE v.total_liquido > 0) AS ultima_compra
    FROM dw_vendas v
    JOIN tb_cidades tc ON tc.cidade = v.cidade AND tc.departamento = '002'
    WHERE v.data_nota >= %(ref)s::date - interval '11 month'
      AND v.data_nota <  %(ref)s::date + interval '1 month'
    GROUP BY v.cidade
) s
JOIN tb_cidades ci       ON ci.cidade = s.cidade
JOIN tb_representantes r ON r.representante = ci.representante
JOIN tb_departamentos d  ON d.departamento = ci.departamento
JOIN tb_funcionarios f   ON f.representante = r.representante AND f.tipo = 3
"""


def margem(offset_expr: str) -> str:
    """% de margem do bucket: 100*(1 - vendas/tela), 0 quando não há base."""
    cond = f"date_trunc('month', v.data_nota) = %(ref)s::date{offset_expr}"
    tela = f"SUM(v.total_tela) FILTER (WHERE {cond})"
    vendas = f"SUM(v.total_vendas) FILTER (WHERE {cond})"
    return (f"CASE WHEN COALESCE({tela}, 0) > 0 "
            f"THEN round(100.0 * (1 - COALESCE({vendas}, 0) / {tela}), 2) ELSE 0 END")


def main() -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT date_trunc('month', max(data_nota))::date FROM dw_vendas")
        ref_max = cur.fetchone()[0]
        cur.execute("TRUNCATE dw_carteira_clientes, dw_carteira_municipios")
        fmt = dict(margem_atual=margem(""), margem_m1=margem(" - interval '1 month'"),
                   margem_m2=margem(" - interval '2 month'"), margem_m3=margem(" - interval '3 month'"))
        for k in range(N_REFS):
            cur.execute("SELECT (%s::date - make_interval(months => %s))::date", (ref_max, k))
            ref = cur.fetchone()[0]
            cur.execute(SQL_CLIENTES.format(**fmt), {"ref": ref})
            ncli = cur.rowcount
            cur.execute(SQL_MUNICIPIOS.format(**fmt), {"ref": ref})
            nmun = cur.rowcount
            print(f"[carteira] ref {ref:%m/%Y}: {ncli:,} clientes | {nmun:,} municipios")
    conn.commit()
    conn.close()
    print("ETAPA 4 (snapshots) OK")


if __name__ == "__main__":
    main()
