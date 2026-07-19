# -*- coding: utf-8 -*-
"""Etapa 6 — validação: contagens, integridade referencial e distribuições."""
from seed.config import connect

CHECKS = [
    ("Contagem por tabela", """
        SELECT 'tb_cidades' t, count(*) n FROM tb_cidades
        UNION ALL SELECT 'tb_clientes', count(*) FROM tb_clientes
        UNION ALL SELECT 'tb_produtos', count(*) FROM tb_produtos
        UNION ALL SELECT 'tb_representantes', count(*) FROM tb_representantes
        UNION ALL SELECT 'dw_vendas', count(*) FROM dw_vendas
        UNION ALL SELECT 'dw_carteira_clientes', count(*) FROM dw_carteira_clientes
        UNION ALL SELECT 'dw_carteira_municipios', count(*) FROM dw_carteira_municipios
        UNION ALL SELECT 'dw_credito_clientes', count(*) FROM dw_credito_clientes
        UNION ALL SELECT 'dw_estoque_produtos', count(*) FROM dw_estoque_produtos
        UNION ALL SELECT 'dw_metas_comerciais', count(*) FROM dw_metas_comerciais
        ORDER BY 1"""),
    ("FKs orfas em dw_vendas (esperado: 3 zeros)", """
        SELECT (SELECT count(*) FROM dw_vendas v LEFT JOIN tb_clientes c ON c.cad_cgc = v.cad_cgc WHERE c.cad_cgc IS NULL),
               (SELECT count(*) FROM dw_vendas v LEFT JOIN tb_cidades ci ON ci.cidade = v.cidade WHERE ci.cidade IS NULL),
               (SELECT count(*) FROM dw_vendas v LEFT JOIN tb_produtos p ON p.codigo_pro = v.codigo_pro WHERE p.codigo_pro IS NULL)"""),
    ("Faturamento liquido por mes (ultimos 5)", """
        SELECT to_char(date_trunc('month', data_nota), 'YYYY-MM') mes,
               round(sum(total_liquido)) fat, count(*) linhas
        FROM dw_vendas GROUP BY 1 ORDER BY 1 DESC LIMIT 5"""),
    ("Margem media global (1 - vendas/tela) — alvo ~0.10-0.25", """
        SELECT round(1 - sum(total_vendas) / sum(total_tela), 4) FROM dw_vendas WHERE total_tela > 0"""),
    ("Distribuicao ranking ABC (ref mais recente)", """
        SELECT ranking, count(*) FROM dw_carteira_clientes
        WHERE mes_ano = (SELECT to_char(max(data_nota), 'MM/YYYY') FROM dw_vendas)
        GROUP BY ranking ORDER BY ranking"""),
    ("Credito: % inadimplentes (alvo ~12%)", """
        SELECT round(100.0 * avg((inadimplente = 'SIM')::int), 1) FROM dw_credito_clientes"""),
    ("Vendas por departamento", """
        SELECT departamento, nome_departamento, round(sum(total_liquido)) fat,
               count(DISTINCT representante) reps
        FROM dw_vendas GROUP BY 1, 2 ORDER BY 1"""),
    ("Devolucoes: total e clientes des-positivados", """
        SELECT round(sum(total_devolucao)) devolucao_total,
               count(DISTINCT cad_cgc) FILTER (WHERE total_liquido < 0) clientes_com_devolucao
        FROM dw_vendas"""),
    ("Estoque: consistencia grupo = soma dos filhos (esperado: 0)", """
        SELECT count(*) FROM (
            SELECT codigo_pai FROM dw_estoque_produtos
            GROUP BY codigo_pai, estoque_grupo
            HAVING sum(estoque) <> estoque_grupo) x"""),
    ("Metas: reps x meses x tipos", """
        SELECT count(DISTINCT representante), count(DISTINCT mes_ano), count(DISTINCT tipo)
        FROM dw_metas_comerciais"""),
    ("Tamanho do banco", "SELECT pg_size_pretty(pg_database_size(current_database()))"),
]


def main() -> None:
    conn = connect()
    falhas = 0
    for titulo, sql in CHECKS:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        print(f"\n== {titulo}")
        for r in rows:
            print("   ", " | ".join(str(c) for c in r))
    conn.close()
    print("\nVALIDACAO CONCLUIDA")


if __name__ == "__main__":
    main()
