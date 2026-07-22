"""Etapa manual — re-alinha a janela temporal do demo.

Os dados foram re-datados uma única vez no seed; com o passar das semanas o
"mês atual" seca e o "mês passado" envelhece. Este script desloca dw_vendas em
múltiplos de 7 dias (preserva o dia-da-semana) até a última venda ficar a menos
de 7 dias de ontem, e reconstrói snapshots e sintéticos — ambos derivam suas
referências de max(data_nota), então se re-alinham sozinhos.

Rodar ~1x por mês:  python -m seed.atualizar_janela

Obs.: os totais mensais mudam (cada venda muda de data), portanto números
anotados de meses anteriores deixam de bater — esperado num demo sintético.
"""
from datetime import date, timedelta

from seed.config import connect


def main() -> None:
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT max(data_nota) FROM dw_vendas")
        ultima = cur.fetchone()[0]
        ontem = date.today() - timedelta(days=1)
        dias = ((ontem - ultima).days // 7) * 7
        if dias <= 0:
            print(f"[janela] em dia (última venda {ultima}); nada a fazer.")
            conn.close()
            return
        cur.execute(
            "UPDATE dw_vendas SET data_nota = data_nota + make_interval(days => %s)",
            (dias,),
        )
        print(f"[janela] {cur.rowcount:,} vendas deslocadas +{dias} dias "
              f"(última agora {ultima + timedelta(days=dias)})")
    conn.commit()
    conn.close()

    from seed import build_snapshots, build_sinteticos
    build_snapshots.main()
    build_sinteticos.main()
    print("JANELA ATUALIZADA")


if __name__ == "__main__":
    main()
