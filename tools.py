import os
import re
import json
import psycopg
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

DATABASE_URL = os.getenv("DATABASE_URL")

DEPT_PUBLICO  = os.getenv("DEPT_PUBLICO", "002")
DEPT_EXCLUIDO = os.getenv("DEPT_EXCLUIDO", "004")

# ---------------------------------------------------------------------------
# FIX 1 — Connection Pool (substitui nova conexão TCP por request)
# Conexões pooladas são devolvidas ao pool via conn.close() — o proxy abaixo
# preserva o padrão conn.close() usado por todas as tools/checkpointer.
# ---------------------------------------------------------------------------
_pool: ConnectionPool | None = None


class _PooledConnection:
    """Proxy: repassa tudo à conexão real, mas close() devolve ao pool."""

    def __init__(self, pool: ConnectionPool, conn: psycopg.Connection):
        self._pool = pool
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        try:
            self._conn.rollback()  # encerra transação de leitura antes de devolver
        except Exception:
            pass
        self._pool.putconn(self._conn)


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=8,     # free tier do Supabase: manter folga no session pooler
            timeout=30,
            open=True,
        )
        print("[Pool DB] Pool Postgres criado: min=1, max=8")
    return _pool


def get_connection():
    """Adquire uma conexão do pool (retorna None em caso de falha)."""
    try:
        pool = _get_pool()
        return _PooledConnection(pool, pool.getconn())
    except Exception as e:
        print(f"Erro ao adquirir conexão do pool: {e}")
        return None

# ---------------------------------------------------------------------------
# FIX 2 — Blocklist de padrões perigosos para executar_consulta_sql_livre
# Bloqueia DML/DDL, metadados e funções de sistema do Postgres.
# ---------------------------------------------------------------------------
_SQL_BLOCKED_PATTERNS = re.compile(
    r"\b("
    # funções e catálogos de sistema do Postgres (pg_sleep, pg_read_file, pg_catalog,
    # pg_stat_activity, pg_class...) — prefixo inteiro bloqueado
    r"pg_[a-z0-9_]+"
    r"|information_schema"
    r"|current_setting|set_config|dblink|lo_import|lo_export"
    # tabelas fora do escopo analítico: modo demo (e-mails de visitantes),
    # infraestrutura do agente (checkpoints/auditoria) e staging do seed
    r"|demo_[a-z0-9_]+"
    r"|ai_[a-z0-9_]+"
    r"|stg_[a-z0-9_]+"
    # DML/DDL
    r"|grant|revoke|drop|truncate|delete|update|insert|merge|create|alter|vacuum|copy"
    r")\b",
    re.IGNORECASE,
)

# Tradução acento-insensível (mesma semântica do TRANSLATE usado no Oracle)
_TR = "TRANSLATE(UPPER({col}), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC')"
_TR_PARAM = "TRANSLATE(UPPER(%s), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC')"

# ---------------------------------------------------------------------------
# Fuzzy match helper — fallback quando LIKE não encontra nada.
# ---------------------------------------------------------------------------
def _fuzzy_match(termo: str, rows: list, name_idx: int = 1, threshold: float = 0.72) -> list:
    from difflib import SequenceMatcher
    import unicodedata

    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFD", str(s))
        return "".join(c for c in s if unicodedata.category(c) != "Mn").upper().strip()

    termo_n = _norm(termo)
    scored = []
    for row in rows:
        nome_full = _norm(row[name_idx])
        words = nome_full.split() or [nome_full]
        best = max(
            SequenceMatcher(None, termo_n, s).ratio()
            for s in [nome_full] + words
        )
        if best >= threshold:
            scored.append((best, row))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:10]]


@tool
def buscar_representante(nome_busca: str) -> str:
    """Busca o ID (REPRESENTANTE) pelo nome do representante ou ID numérico."""
    conn = get_connection()
    if not conn:
        return "Erro de conexão."

    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()

        base_query = """
            SELECT DISTINCT
                fr.representante,
                fr.nome_representante,
                fr.departamento
            FROM tb_representantes fr
            WHERE fr.departamento NOT IN (%(dept_excluido)s)
        """
        base_params = {"dept_excluido": DEPT_EXCLUIDO}

        if nome_busca_limpo.isdigit():
            query = base_query + " AND fr.representante = LPAD(%(busca)s, 3, '0') LIMIT 20"
            cursor.execute(query, {**base_params, "busca": nome_busca_limpo})
            rows = cursor.fetchall()
        else:
            query = base_query + f"""
                AND {_TR.format(col='fr.nome_representante')}
                 LIKE {_TR_PARAM.replace('%s', '%(busca)s')}
                LIMIT 20
            """
            cursor.execute(query, {**base_params, "busca": f"%{nome_busca_limpo}%"})
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(base_query, base_params)
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)

        resultados = []
        for r in rows:
            departamento = r[2]
            tipo_venda = "Público (Vendas Diretas)" if departamento == DEPT_PUBLICO else "Privado"
            resultados.append({
                "ID": r[0],
                "NOME": r[1],
                "DEPARTAMENTO": departamento,
                "TIPO_VENDA": tipo_venda,
            })
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        conn.close()


@tool
def buscar_grupo_cliente(nome_busca: str) -> str:
    """Busca o ID (CODIGO_GRUPO) pelo nome do grupo de clientes."""
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        if nome_busca_limpo.isdigit():
            query = """
                SELECT DISTINCT codigo_grupo, UPPER(nome_grupo) AS nome
                FROM tb_grupos_clientes
                WHERE codigo_grupo = LPAD(%s, 5, '0') LIMIT 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = f"""
                SELECT codigo_grupo, UPPER(nome_grupo) AS nome
                FROM tb_grupos_clientes
                WHERE {_TR.format(col='nome_grupo')} LIKE {_TR_PARAM}
                LIMIT 20
            """
            cursor.execute(query, (f"%{nome_busca_limpo}%",))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT codigo_grupo, UPPER(nome_grupo) FROM tb_grupos_clientes")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        conn.close()


@tool
def buscar_departamento(nome_busca: str) -> str:
    """Busca o ID (DEPARTAMENTO) pelo nome do departamento."""
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        if nome_busca_limpo.isdigit():
            query = """
                SELECT DISTINCT departamento, UPPER(nome_departamento) AS nome
                FROM tb_departamentos
                WHERE departamento = LPAD(%s, 3, '0') LIMIT 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = f"""
                SELECT departamento, UPPER(nome_departamento) AS nome
                FROM tb_departamentos
                WHERE {_TR.format(col='nome_departamento')} LIKE {_TR_PARAM}
                LIMIT 20
            """
            cursor.execute(query, (f"%{nome_busca_limpo}%",))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT departamento, UPPER(nome_departamento) FROM tb_departamentos")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        conn.close()


@tool
def buscar_cidade(nome_busca: str) -> str:
    """Busca o ID (CIDADE) pelo nome da cidade."""
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()

        if nome_busca_limpo.isdigit():
            query = """
                SELECT DISTINCT cidade, UPPER(nome_cidade) AS nome
                FROM tb_cidades
                WHERE cidade = LPAD(%s, 5, '0') LIMIT 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = f"""
                SELECT cidade, UPPER(nome_cidade) AS nome
                FROM tb_cidades
                WHERE {_TR.format(col='nome_cidade')} LIKE {_TR_PARAM}
                LIMIT 20
            """
            cursor.execute(query, (f"%{nome_busca_limpo}%",))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT cidade, UPPER(nome_cidade) FROM tb_cidades LIMIT 1000")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)

        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        conn.close()


@tool
def buscar_produto(nome_busca: str) -> str:
    """Busca o ID (CODIGO_PRO) pelo nome ou descrição do produto."""
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        if nome_busca_limpo.isdigit():
            query = """
                SELECT codigo_pro, UPPER(nome_produto) AS nome
                FROM tb_produtos
                WHERE codigo_pro = LPAD(%s, 7, '0') LIMIT 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = f"""
                SELECT DISTINCT codigo_pro, UPPER(nome_produto) AS nome
                FROM tb_produtos
                WHERE {_TR.format(col='nome_produto')} LIKE {_TR_PARAM}
                LIMIT 20
            """
            cursor.execute(query, (f"%{nome_busca_limpo}%",))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT codigo_pro, UPPER(nome_produto) FROM tb_produtos LIMIT 500")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        conn.close()


@tool
def buscar_cadastro_cliente(termo_busca: str) -> str:
    """
    Busca o Cadastro do Cliente (CODIGO_EXP, CAD_CGC, RAZAO_SOCIAL) no banco de dados.
    Forneça o CNPJ (CAD_CGC), o Código ID (CODIGO_EXP) ou uma parte do nome (Razão Social).
    """
    conn = get_connection()
    if not conn:
        return "Erro de conexão."

    termo_busca_limpo = termo_busca.strip()
    termo_numerico = re.sub(r'\D', '', termo_busca_limpo)
    cursor = None
    try:
        cursor = conn.cursor()

        if termo_busca_limpo.isdigit():
            if len(termo_numerico) <= 7:
                # Número pequeno → Código Expresso (ID), armazenado com zeros à esquerda
                query = """
                    SELECT DISTINCT codigo_exp, cad_cgc, razao_social
                    FROM tb_clientes
                    WHERE codigo_exp = LPAD(%s, 6, '0') LIMIT 20
                """
                cursor.execute(query, (termo_numerico,))
            else:
                # Número grande → CNPJ limpo
                query = """
                    SELECT DISTINCT codigo_exp, cad_cgc, razao_social
                    FROM tb_clientes
                    WHERE REGEXP_REPLACE(cad_cgc, '[^0-9]', '', 'g') LIKE %s LIMIT 20
                """
                cursor.execute(query, (f"%{termo_numerico}%",))

        elif termo_numerico and len(termo_numerico) > 7:
            # CNPJ com máscara
            query = """
                SELECT DISTINCT codigo_exp, cad_cgc, razao_social
                FROM tb_clientes
                WHERE REGEXP_REPLACE(cad_cgc, '[^0-9]', '', 'g') LIKE %s LIMIT 20
            """
            cursor.execute(query, (f"%{termo_numerico}%",))

        else:
            query = """
                SELECT DISTINCT codigo_exp, cad_cgc, razao_social
                FROM tb_clientes
                WHERE UPPER(razao_social) LIKE UPPER(%s) LIMIT 20
            """
            cursor.execute(query, (f"%{termo_busca_limpo}%",))

        res = [{"CAD_CGC": r[1], "RAZAO_SOCIAL": r[2]} for r in cursor.fetchall()]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        conn.close()


@tool
def executar_consulta_sql_livre(query: str) -> str:
    """
    Executa uma consulta SQL livre (RAW SQL) diretamente no banco de dados.
    Útil para cálculos matemáticos complexos como Ticket Médio ou uso de funções nativas SQL.
    Apenas SELECT é permitido.
    """
    query_stripped = query.strip()

    # Proteção 1: deve iniciar com SELECT
    if not query_stripped.upper().startswith("SELECT"):
        return json.dumps({"erro": "Apenas consultas SELECT são permitidas."}, ensure_ascii=False)

    # Proteção 2: blocklist de padrões perigosos (metadados, funções de sistema, DML)
    match = _SQL_BLOCKED_PATTERNS.search(query_stripped)
    if match:
        return json.dumps(
            {"erro": f"Query bloqueada por segurança: uso de '{match.group(0)}' não é permitido."},
            ensure_ascii=False,
        )

    conn = get_connection()
    if not conn:
        return "Erro de conexão."

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        colunas = [col[0] for col in cursor.description]
        registros = [dict(zip(colunas, row)) for row in cursor.fetchall()]

        if len(registros) > 100:
            registros = registros[:100]
            registros.append({"AVISO_SISTEMA_CRITICO": "LIMITE DE TOKENS ATINGIDO! Os resultados foram cortados nas primeiras 100 linhas. Você deve reescrever sua query SQL usando GROUP BY, SUM(), ou LIMIT para agregar esses dados *dentro do banco de dados*!"})

        resultado_json = {
            "sql_executado_no_banco": query,
            "dados": registros
        }
        return json.dumps(resultado_json, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"erro": f"Erro ao executar SQL Mágico: {str(e)}"}, ensure_ascii=False)
    finally:
        if cursor:
            cursor.close()
        conn.close()
