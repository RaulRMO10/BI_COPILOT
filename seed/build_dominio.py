# -*- coding: utf-8 -*-
"""Etapa 2 — domínio: TB_* (cidades+IBGE, reps/territórios, clientes, produtos+CMED)."""
import numpy as np
import pandas as pd
from faker import Faker

from seed.config import SEED, connect, copy_df, cnpj_from_uid, det_hash

UF_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}
# rep público por região (SP tem rep dedicado — volume)
PUB_REP = {"Norte": "025", "Nordeste": "026", "Centro-Oeste": "027", "Sudeste": "028", "Sul": "030"}


def main() -> None:
    rng = np.random.RandomState(SEED)
    Faker.seed(SEED)
    fk = Faker("pt_BR")
    conn = connect()
    conn.execute("""TRUNCATE tb_departamentos, tb_representantes, tb_funcionarios,
                    tb_cidades, tb_grupos_clientes, tb_clientes, tb_produtos""")
    conn.commit()

    # ── departamentos ────────────────────────────────────────────────────────
    deptos = pd.DataFrame([
        ("001", "VENDAS PRIVADO"), ("002", "VENDAS PUBLICO"),
        ("003", "KEY ACCOUNTS"), ("004", "USO INTERNO"),
    ], columns=["departamento", "nome_departamento"])
    copy_df(conn, "tb_departamentos", deptos)

    # ── representantes (001–024 privado · 025–030 público) ───────────────────
    reps = []
    regioes_priv = (["Sudeste"] * 10 + ["Sul"] * 5 + ["Nordeste"] * 4 +
                    ["Centro-Oeste"] * 3 + ["Norte"] * 2)  # 24 reps ~ proporção de volume
    for i in range(1, 31):
        rid = f"{i:03d}"
        depto = "001" if i <= 24 else "002"
        regiao = regioes_priv[i - 1] if i <= 24 else \
            {25: "Norte", 26: "Nordeste", 27: "Centro-Oeste", 28: "Sudeste", 29: "Sudeste", 30: "Sul"}[i]
        reps.append((rid, fk.name().upper(), depto, regiao))
    reps = pd.DataFrame(reps, columns=["representante", "nome_representante", "departamento", "regiao"])
    copy_df(conn, "tb_representantes", reps)

    # ── funcionários (1 diretor, 2 supervisores, 1 consultor por rep) ────────
    funcs = [("001", fk.name().upper(), 1, None),
             ("002", fk.name().upper(), 2, None),
             ("003", fk.name().upper(), 2, None)]
    funcs += [(f"1{r}", n, 3, r) for r, n in zip(reps.representante, reps.nome_representante)]
    funcs = pd.DataFrame(funcs, columns=["funcionario", "nome_funcionario", "tipo", "representante"])
    copy_df(conn, "tb_funcionarios", funcs)

    # ── cidades: distintas do Olist + código IBGE + canal + território ───────
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT customer_city, customer_state FROM stg_customers")
        cid = pd.DataFrame(cur.fetchall(), columns=["nome_cidade", "uf"])
        cur.execute("SELECT nome, uf, codigo_ibge, regiao FROM stg_ibge")
        ibge = pd.DataFrame(cur.fetchall(), columns=["nome_cidade", "uf", "codigo_ibge", "regiao"])
    cid = cid.merge(ibge, on=["nome_cidade", "uf"], how="left")
    cid["codigo_ibge"] = cid["codigo_ibge"].astype("Int64")
    cid["regiao"] = cid["regiao"].fillna(cid["uf"].map(UF_REGIAO))
    cid = cid.sort_values(["uf", "nome_cidade"]).reset_index(drop=True)
    cid["cidade"] = [f"{i + 10001:05d}" for i in range(len(cid))]
    # canal: ~22% das cidades são território público (hash determinístico)
    cid["departamento"] = [
        "002" if det_hash("canal", n, u) % 100 < 22 else "001"
        for n, u in zip(cid.nome_cidade, cid.uf)
    ]
    # território público: rep da região (SP → rep 029 dedicado)
    pub_rep = [
        "029" if (d == "002" and u == "SP") else PUB_REP.get(r, "028") if d == "002" else None
        for d, u, r in zip(cid.departamento, cid.uf, cid.regiao)
    ]
    # território privado: blocos contíguos (uf, nome) rateados entre reps da região
    priv = cid[cid.departamento == "001"]
    rep_by_reg = {reg: reps[(reps.departamento == "001") & (reps.regiao == reg)].representante.tolist()
                  for reg in set(regioes_priv)}
    priv_rep = {}
    for reg, grupo in priv.groupby("regiao"):
        rr = rep_by_reg.get(reg) or reps[reps.departamento == "001"].representante.tolist()
        blocos = np.array_split(np.arange(len(grupo)), len(rr))
        for rep_id, bloco in zip(rr, blocos):
            for pos in bloco:
                priv_rep[grupo.index[pos]] = rep_id
    cid["representante"] = [priv_rep.get(ix) or pr for ix, pr in zip(cid.index, pub_rep)]
    copy_df(conn, "tb_cidades",
            cid[["cidade", "nome_cidade", "uf", "codigo_ibge", "regiao", "representante", "departamento"]])
    print(f"[tb] cidades: {len(cid):,} ({(cid.departamento == '002').sum():,} publicas) | "
          f"IBGE match: {cid.codigo_ibge.notna().mean():.0%}")

    # ── grupos (redes/associações) ───────────────────────────────────────────
    grupos = pd.DataFrame(
        [(f"{i + 50001:05d}", f"REDE {fk.last_name().upper()} FARMACIAS") for i in range(15)],
        columns=["codigo_grupo", "nome_grupo"])
    copy_df(conn, "tb_grupos_clientes", grupos)

    # ── clientes: 1 por customer_unique_id, com cidade + receita ─────────────
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sc.customer_unique_id,
                   (ARRAY_AGG(sc.customer_city  ORDER BY o.order_purchase_timestamp DESC))[1],
                   (ARRAY_AGG(sc.customer_state ORDER BY o.order_purchase_timestamp DESC))[1],
                   COALESCE(SUM(i.price), 0)
            FROM stg_customers sc
            LEFT JOIN stg_orders o      ON o.customer_id = sc.customer_id
            LEFT JOIN stg_order_items i ON i.order_id    = o.order_id
            GROUP BY sc.customer_unique_id
        """)
        cli = pd.DataFrame(cur.fetchall(), columns=["uid", "nome_cidade", "uf", "receita"])
    cli["receita"] = cli["receita"].astype(float)
    cli = cli.merge(cid[["cidade", "nome_cidade", "uf", "departamento"]],
                    on=["nome_cidade", "uf"], how="left").dropna(subset=["cidade"])
    cli = cli.sort_values("uid").reset_index(drop=True)

    # CNPJ determinístico + resolução de colisões
    cli["cad_cgc"] = cli["uid"].map(cnpj_from_uid)
    while cli["cad_cgc"].duplicated().any():
        dup = cli["cad_cgc"].duplicated(keep="first")
        cli.loc[dup, "cad_cgc"] = [cnpj_from_uid(u + "#salt") for u in cli.loc[dup, "uid"]]

    # razão social sintética (vetorizado e seedado)
    sobrenomes = np.array([fk.last_name().upper() for _ in range(600)])
    formatos = np.array(["FARMACIA {} LTDA", "DROGARIA {} LTDA", "FARMACIA E DROGARIA {} LTDA",
                         "DISTRIBUIDORA {} DE MEDICAMENTOS LTDA", "CLINICA {} LTDA", "HOSPITAL {}"])
    fidx = rng.choice(len(formatos), len(cli), p=[.34, .30, .16, .08, .07, .05])
    n1 = sobrenomes[rng.randint(0, 600, len(cli))]
    n2 = sobrenomes[rng.randint(0, 600, len(cli))]
    nomes = np.where(rng.rand(len(cli)) < 0.35, n1 + " " + n2, n1)
    cli["razao_social"] = [f.format(n) for f, n in zip(formatos[fidx], nomes)]
    cli["nome_fantasia"] = ["FARMA " + n.split()[0] for n in nomes]
    # nas cidades públicas, o maior cliente vira a prefeitura
    top_pub = (cli[cli.departamento == "002"].sort_values("receita", ascending=False)
               .drop_duplicates(subset=["cidade"]))
    cli.loc[top_pub.index, "razao_social"] = "PREFEITURA MUNICIPAL DE " + top_pub["nome_cidade"]
    cli.loc[top_pub.index, "nome_fantasia"] = "PREF " + top_pub["nome_cidade"].str.slice(0, 18)
    # grupos: top-450 privados por receita
    top_priv = cli[cli.departamento == "001"].nlargest(450, "receita").index
    cli["codigo_grupo"] = None
    cli.loc[top_priv, "codigo_grupo"] = [
        grupos.codigo_grupo.iloc[det_hash("grp", u) % len(grupos)] for u in cli.loc[top_priv, "uid"]]
    cli["cad_cgc_id"] = (cli.index + 1).astype(str)
    cli["codigo_exp"] = [f"{i + 1:06d}" for i in cli.index]
    copy_df(conn, "tb_clientes",
            cli.rename(columns={"uid": "customer_unique_id"})[
                ["cad_cgc", "cad_cgc_id", "codigo_exp", "razao_social", "nome_fantasia",
                 "cidade", "codigo_grupo", "customer_unique_id"]])
    print(f"[tb] clientes: {len(cli):,} | prefeituras: {len(top_pub):,} | com grupo: {cli.codigo_grupo.notna().sum():,}")

    # ── produtos: catálogo CMED mapeado deterministicamente ao Olist ─────────
    with conn.cursor() as cur:
        cur.execute("SELECT product_id, COALESCE(product_category_name,'outros') FROM stg_products ORDER BY product_id")
        prods = pd.DataFrame(cur.fetchall(), columns=["product_id", "categoria_olist"])
        cur.execute("SELECT produto, apresentacao, laboratorio, cnpj_lab FROM stg_cmed ORDER BY cmed_id")
        cmed = pd.DataFrame(cur.fetchall(), columns=["produto", "apresentacao", "laboratorio", "cnpj_lab"])
    pai_ids = {p: f"P{i + 1:05d}" for i, p in enumerate(cmed["produto"].unique())}
    idx = [det_hash("med", pid) % len(cmed) for pid in prods.product_id]
    sel = cmed.iloc[idx].reset_index(drop=True)
    prods["codigo_pro"] = [f"{i + 1000001:07d}" for i in range(len(prods))]
    prods["nome_produto"] = (sel["produto"] + " " + sel["apresentacao"]).str.slice(0, 120)
    prods["marca"] = sel["produto"]
    prods["codigo_pai"] = sel["produto"].map(pai_ids)
    prods["produto_pai"] = sel["produto"]
    prods["razao_social_lab"] = sel["laboratorio"]
    prods["cad_cgc_industria"] = sel["cnpj_lab"]
    copy_df(conn, "tb_produtos",
            prods[["codigo_pro", "nome_produto", "marca", "codigo_pai", "produto_pai",
                   "razao_social_lab", "cad_cgc_industria", "categoria_olist", "product_id"]])
    print(f"[tb] produtos: {len(prods):,} | produtos-pai: {prods.codigo_pai.nunique():,} | "
          f"laboratorios: {prods.razao_social_lab.nunique():,}")

    conn.close()
    print("ETAPA 2 (dominio) OK")


if __name__ == "__main__":
    main()
