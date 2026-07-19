# -*- coding: utf-8 -*-
"""Configuração compartilhada do seed do modo demo (Olist + CMED + IBGE → Supabase)."""
import hashlib
import io
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
SEED = 42  # seed global — banco 100% reproduzível

load_dotenv(REPO / ".env")
DATABASE_URL = os.environ["DATABASE_URL"]


def connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Executa um .sql statement a statement (split ingênuo por ';' — sem $$)."""
    for stmt in path.read_text(encoding="utf-8").split(";"):
        if stmt.strip():
            conn.execute(stmt)
    conn.commit()


def copy_df(conn: psycopg.Connection, table: str, df) -> int:
    """COPY de um DataFrame (colunas do df = colunas da tabela, na ordem)."""
    cols = ", ".join(df.columns)
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)") as cp:
            cp.write(buf.getvalue())
    conn.commit()
    return len(df)


def det_hash(*parts: str) -> int:
    """Hash determinístico (independente de plataforma/sessão) para regras seedadas."""
    h = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def cnpj_from_uid(uid: str) -> str:
    """CNPJ sintético determinístico com dígitos verificadores válidos."""
    base8 = det_hash("cnpj", uid) % 100_000_000
    corpo = f"{base8:08d}0001"
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = 11 - (sum(int(c) * p for c, p in zip(corpo, pesos1)) % 11)
    d1 = 0 if d1 >= 10 else d1
    d2 = 11 - (sum(int(c) * p for c, p in zip(corpo + str(d1), pesos2)) % 11)
    d2 = 0 if d2 >= 10 else d2
    return f"{corpo}{d1}{d2}"
