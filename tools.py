import os
import re
import json
import oracledb
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DSN      = os.getenv("DB_DSN")

DEPT_PUBLICO  = os.getenv("DEPT_PUBLICO", "002")
DEPT_EXCLUIDO = os.getenv("DEPT_EXCLUIDO", "004")

# ---------------------------------------------------------------------------
# FIX 1 — Connection Pool (substitui nova conexão TCP por request)
# Conexões pooladas são retornadas ao pool via conn.close() — sem alteração
# nas tools existentes.
# ---------------------------------------------------------------------------
_pool: oracledb.ConnectionPool | None = None

def _get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(
            user=DB_USER,
            password=DB_PASSWORD,
            dsn=DB_DSN,
            min=2,
            max=20,        # suporta até ~20 queries simultâneas
            increment=2,
            timeout=30,
            wait_timeout=5000,
        )
        print("[Pool DB] Pool criado: min=2, max=20")
    return _pool

def get_connection():
    """Adquire uma conexão do pool (retorna None em caso de falha)."""
    try:
        return _get_pool().acquire()
    except Exception as e:
        print(f"Erro ao adquirir conexão do pool: {e}")
        return None

# ---------------------------------------------------------------------------
# FIX 2 — Blocklist de padrões perigosos para executar_consulta_sql_livre
# Bloqueia acesso a metadados, pacotes internos e contexto de sessão do banco.
# ---------------------------------------------------------------------------
_SQL_BLOCKED_PATTERNS = re.compile(
    r"\b("
    r"SYS_CONTEXT|UTL_FILE|UTL_HTTP|UTL_TCP|UTL_SMTP"
    r"|DBMS_[A-Z_]+|EXECUTE\s+IMMEDIATE"
    r"|ALL_SOURCE|USER_SOURCE|DBA_SOURCE"
    r"|ALL_TABLES|DBA_TABLES|DBA_[A-Z_]+"
    r"|V\$[A-Z_]+|GV\$[A-Z_]+"
    r"|SYS\.[A-Z_]+|SYSTEM\.[A-Z_]+"
    r"|GRANT|REVOKE|DROP|TRUNCATE|DELETE|UPDATE|INSERT|MERGE|CREATE|ALTER"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Fuzzy match helper — fallback quando LIKE não encontra nada.
# Usa difflib.SequenceMatcher (stdlib, sem dependências extras).
# Pontua cada row pelo campo name_idx contra o termo buscado,
# comparando também palavra a palavra (cobre "Rafaela" → "RAFAELLA SANTOS").
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
    import json
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        
        base_query = f"""
            SELECT DISTINCT 
                FR.REPRESENTANTE, 
                FR.NOME, 
                FD.DEPARTAMENTO
            FROM TB_FUNCIONARIOS FF
            JOIN TB_REPRESENTANTES FR ON FR.REPRESENTANTE = FF.REPRESENTANTE
            JOIN TB_DEPARTAMENTOS FD  ON FD.DEPARTAMENTO  = FF.DEPARTAMENTO
            WHERE FF.TIPO = 4 AND FD.DEPARTAMENTO NOT IN ('{DEPT_EXCLUIDO}')
        """
        
        if nome_busca_limpo.isdigit():
            # Busca direta pelo ID de 3 dígitos (varchar/char com zero à esquerda)
            query = base_query + " AND FR.REPRESENTANTE = LPAD(:1, 3, '0') AND ROWNUM <= 20"
            cursor.execute(query, (nome_busca_limpo,))
        else:
            # Busca textual: ignora acentos via TRANSLATE e normaliza para UPPER
            query = base_query + """ 
                AND TRANSLATE(UPPER(FR.NOME), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                 LIKE TRANSLATE(UPPER(:1), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                AND ROWNUM <= 20
            """
            cursor.execute(query, (f'%{nome_busca_limpo}%',))

            # Fallback fuzzy: se LIKE não achou nada, tenta similaridade por string
            rows_like = cursor.fetchall()
            if not rows_like:
                cursor.execute(base_query)
                rows_like = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
            # reatribui para o fetchall abaixo não ser chamado novamente
            # (usamos variável temporária e pulamos o fetchall padrão)
            resultados = []
            for r in rows_like:
                departamento = r[2]
                tipo_venda = "Público" if departamento == DEPT_PUBLICO else "Privado"
                resultados.append({"ID": r[0], "NOME": r[1], "DEPARTAMENTO": departamento, "TIPO_VENDA": tipo_venda})
            return json.dumps(resultados, ensure_ascii=False)
            
        resultados = []
        for r in cursor.fetchall():
            rep_id = r[0]
            nome = r[1]
            departamento = r[2]
            
            tipo_venda = "Privado"
            if departamento == DEPT_PUBLICO:
                tipo_venda = "Público (Vendas Diretas)"
                
            resultados.append({
                "ID": rep_id, 
                "NOME": nome, 
                "DEPARTAMENTO": departamento,
                "TIPO_VENDA": tipo_venda
            })
            
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor: cursor.close()
        conn.close()

@tool
def buscar_grupo_cliente(nome_busca: str) -> str:
    """Busca o ID (CODIGO_GRUPO) pelo nome do grupo de clientes."""
    import json
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        if nome_busca_limpo.isdigit():
            query = """
                SELECT DISTINCT codigo_grupo, UPPER(nome) AS nome 
                FROM tb_grupos_clientes 
                WHERE codigo_grupo = LPAD(:1, 5, '0') AND ROWNUM <= 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = """
                SELECT
		        codigo_grupo, UPPER(nome) AS nome
                FROM
			tb_grupos_clientes
                WHERE TRANSLATE(UPPER(nome), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                 LIKE TRANSLATE(UPPER(:1), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                AND ROWNUM <= 20
            """
            cursor.execute(query, (f'%{nome_busca_limpo}%',))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT codigo_grupo, UPPER(nome) FROM tb_grupos_clientes")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor: cursor.close()
        conn.close()

@tool
def buscar_departamento(nome_busca: str) -> str:
    """Busca o ID (DEPARTAMENTO) pelo nome do departamento."""
    import json
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        if nome_busca_limpo.isdigit():
            query = """
                SELECT DISTINCT departamento, UPPER(nome) AS nome 
                FROM tb_departamentos 
                WHERE departamento = LPAD(:1, 3, '0') AND ROWNUM <= 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = """
                SELECT
		departamento, UPPER(nome) AS nome
                FROM
		TB_DEPARTAMENTOS fd
                WHERE TRANSLATE(UPPER(fd.nome), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                 LIKE TRANSLATE(UPPER(:1), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                AND ROWNUM <= 20
            """
            cursor.execute(query, (f'%{nome_busca_limpo}%',))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT departamento, UPPER(nome) FROM tb_departamentos")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor: cursor.close()
        conn.close()

@tool
def buscar_cidade(nome_busca: str) -> str:
    """Busca o ID (CIDADE) pelo nome da cidade."""
    import json
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Heurística: se for número (ex: "00265" ou "265") pesquisa direto no ID (cidade) formatando com LPAD para 5 dígitos
        if nome_busca_limpo.isdigit():
            # Completa com zeros à esquerda no código ou joga direto (assumindo que seja formatado)
            query = """
                SELECT DISTINCT CIDADE, UPPER(nome) AS NOME 
                FROM tb_cidades 
                WHERE CIDADE = LPAD(:1, 5, '0') AND ROWNUM <= 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            # Busca textual: ignora acentos via TRANSLATE e normaliza para UPPER
            query = """
                SELECT
	            cidade, UPPER(nome) AS NOME 
                FROM tb_cidades
                WHERE TRANSLATE(UPPER(nome), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                 LIKE TRANSLATE(UPPER(:1), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                AND ROWNUM <= 20
            """
            cursor.execute(query, (f'%{nome_busca_limpo}%',))
            rows = cursor.fetchall()
            if not rows:
                # Fallback fuzzy: limita a 1000 cidades para performance
                cursor.execute("SELECT cidade, UPPER(nome) FROM tb_cidades WHERE ROWNUM <= 1000")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)

        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor: cursor.close()
        conn.close()

@tool
def buscar_produto(nome_busca: str) -> str:
    """Busca o ID (CODIGO_PRO) pelo nome ou descrição do produto."""
    import json
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    nome_busca_limpo = nome_busca.strip()
    cursor = None
    try:
        cursor = conn.cursor()
        if nome_busca_limpo.isdigit():
            query = """
                SELECT
		codigo_pro, UPPER(nome_produto) AS nome 
                FROM
		tb_produtos 
                WHERE CODIGO_PRO = LPAD(:1, 7, '0') AND ROWNUM <= 20
            """
            cursor.execute(query, (nome_busca_limpo,))
            rows = cursor.fetchall()
        else:
            query = """
                SELECT DISTINCT CODIGO_PRO, UPPER(NOME_PRODUTO) AS NOME 
                FROM tb_produtos 
                WHERE TRANSLATE(UPPER(NOME_PRODUTO), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                 LIKE TRANSLATE(UPPER(:1), 'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') 
                AND ROWNUM <= 20
            """
            cursor.execute(query, (f'%{nome_busca_limpo}%',))
            rows = cursor.fetchall()
            if not rows:
                # Fallback fuzzy: limita a 500 produtos para performance
                cursor.execute("SELECT CODIGO_PRO, UPPER(NOME_PRODUTO) FROM tb_produtos WHERE ROWNUM <= 500")
                rows = _fuzzy_match(nome_busca_limpo, cursor.fetchall(), name_idx=1)
        res = [{"ID": r[0], "NOME": r[1]} for r in rows]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor: cursor.close()
        conn.close()

@tool
def buscar_cadastro_cliente(termo_busca: str) -> str:
    """
    Busca o Cadastro do Cliente (CODIGO_EXP, CAD_CGC, RAZAO_SOCIAL) no banco de dados.
    Forneça o CNPJ (CAD_CGC), o Código ID (CODIGO_EXP) ou uma parte do nome (Razão Social).
    """
    import json
    import re
    conn = get_connection()
    if not conn:
        return "Erro de conexão."
    
    termo_busca_limpo = termo_busca.strip()
    termo_numerico = re.sub(r'\D', '', termo_busca_limpo)
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Heurística baseada no input do usuário
        if termo_busca_limpo.isdigit():
            if len(termo_numerico) <= 7:
                # É puramente um número pequeno. Definitivamente o Código Expresso (ID).
                query = """
                    SELECT DISTINCT codigo_exp, cad_cgc, razao_social 
                    FROM tb_clientes 
                    WHERE codigo_exp = :busca_numerica_exata AND ROWNUM <= 20
                """
                cursor.execute(query, busca_numerica_exata=int(termo_numerico))
            else:
                # É puramente número mas muito grande para ser um ID. É um CNPJ limpo.
                query = """
                    SELECT DISTINCT codigo_exp, cad_cgc, razao_social 
                    FROM tb_clientes 
                    WHERE REGEXP_REPLACE(cad_cgc, '[^0-9]', '') LIKE :busca_numerica AND ROWNUM <= 20
                """
                cursor.execute(query, busca_numerica=f"%{termo_numerico}%")
                
        elif termo_numerico and len(termo_numerico) > 7:
            # Tem letras/simbolos mas a parte numérica indica que o usuário colou um CNPJ com máscara.
            query = """
                SELECT DISTINCT codigo_exp, cad_cgc, razao_social 
                FROM tb_clientes 
                WHERE REGEXP_REPLACE(cad_cgc, '[^0-9]', '') LIKE :busca_numerica AND ROWNUM <= 20
            """
            cursor.execute(query, busca_numerica=f"%{termo_numerico}%")
            
        else:
            # Sem formato óbvio de ID numérico cravado ou CNPJ longo. Busca genérica (Ex: "Loja 10", "Loja ABC")
            query = """
                SELECT DISTINCT codigo_exp, cad_cgc, razao_social 
                FROM tb_clientes 
                WHERE UPPER(razao_social) LIKE UPPER(:busca) AND ROWNUM <= 20
            """
            cursor.execute(query, busca=f"%{termo_busca_limpo}%")
            
        res = [{"CAD_CGC": r[1], "RAZAO_SOCIAL": r[2]} for r in cursor.fetchall()]
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Erro: {str(e)}"
    finally:
        if cursor: cursor.close()
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

    # Proteção 2: blocklist de padrões perigosos (metadados, pacotes internos, DML)
    match = _SQL_BLOCKED_PATTERNS.search(query_stripped)
    if match:
        return json.dumps(
            {"erro": f"Query bloqueada por segurança: uso de '{match.group(0)}' não é permitido."},
            ensure_ascii=False,
        )
        
    conn = get_connection()
    if not conn: return "Erro de conexão."
    
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        colunas = [col[0] for col in cursor.description]
        registros = [dict(zip(colunas, row)) for row in cursor.fetchall()]
        
        if len(registros) > 100:
            registros = registros[:100]
            registros.append({"AVISO_SISTEMA_CRITICO": "LIMITE DE TOKENS ATINGIDO! Os resultados foram cortados nas primeiras 100 linhas. Você deve reescrever sua query SQL usando GROUP BY, SUM(), ou ROWNUM para agregar esses dados *dentro do banco de dados*!"})
        
        resultado_json = {
            "sql_executado_no_banco": query,
            "dados": registros
        }
        return json.dumps(resultado_json, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"erro": f"Erro ao executar SQL Mágico: {str(e)}"}, ensure_ascii=False)
    finally:
        if cursor: cursor.close()
        conn.close()
