import os
import json
import jwt
import requests
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

CUBE_BASE_URL = os.getenv("CUBE_API_BASE_URL", "http://localhost:4000")
CUBE_API_URL = f"{CUBE_BASE_URL}/cubejs-api/v1/load"
CUBE_API_SECRET = os.getenv("CUBEJS_API_SECRET")

def generate_cube_token() -> str:
    """Gera um JWT de curta duração para a API do Cube.dev (válido por 1 hora).
    FIX 4: tokens de vida curta — mesmo que a secret vaze, o token expira.
    """
    import time
    now = int(time.time())
    payload = {
        "iat": now,
        "exp": now + 3600,  # 1 hora — gerado a cada request, sem custo extra
    }
    return jwt.encode(payload, CUBE_API_SECRET, algorithm="HS256")

@tool
def executar_consulta_cube(query_json_str: str) -> str:
    """
    Executa uma consulta JSON estruturada na Semantic Layer do Cube.dev.
    O LLM DEVE usar esta ferramenta após mapear os IDs e intenções do usuário para extrair as medidas e dimensões.
    
    Args:
        query_json_str: String contendo o JSON válido da query para o Cube.
                       Exemplo: {"measures": ["DW_VENDAS.faturamento_liquido"], "dimensions": ["DW_VENDAS.nome_produto"]}
                     
    Returns:
        String com os dados retornados do banco pelo Cube (em formato JSON) ou a mensagem de erro.
    """
    try:
        # Analisar para garantir que é um JSON válido
        query_obj = json.loads(query_json_str)

        # FIX 6 — continueWait nativo: o Cube.dev bloqueia internamente até o
        # pre-aggregate estar pronto e responde em um único request.
        # Elimina o loop de polling com time.sleep(2) × 15 que travava a thread.
        query_obj["renewQuery"] = True

        token = generate_cube_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # continueWait via query param faz o servidor Cube aguardar server-side
        params = {
            "query":       json.dumps(query_obj),
            "continueWait": "true",
        }

        # 1. Obter a Query SQL gerada (para debug/exposição ao usuário)
        sql_gerado = "SQL não disponível"
        try:
            sql_response = requests.get(
                f"{CUBE_BASE_URL}/cubejs-api/v1/sql",
                headers=headers,
                params={"query": json.dumps(query_obj)},
                timeout=10,
            )
            if sql_response.status_code == 200:
                sql_data = sql_response.json()
                if "sql" in sql_data and "sql" in sql_data["sql"]:
                    query_text  = sql_data["sql"]["sql"][0]
                    bind_values = sql_data["sql"]["sql"][1] if len(sql_data["sql"]["sql"]) > 1 else []

                    import re
                    vals = list(bind_values)
                    def replacer(match):
                        if not vals: return match.group(0)
                        val = vals.pop(0)
                        if isinstance(val, str): return f"'{val}'"
                        if val is None: return "NULL"
                        return str(val)

                    sql_gerado = re.sub(r':"\?"|:\?|\?', replacer, query_text)
        except Exception:
            pass  # falha na captura de SQL não bloqueia a consulta principal

        # 2. Executar a consulta — um único request, sem loop, sem sleep
        # timeout=35s: cobre o worst-case de build de pre-aggregate do Cube.dev
        response = requests.get(CUBE_API_URL, headers=headers, params=params, timeout=35)

        if response.status_code != 200:
            return f"Erro Cube.dev (Status {response.status_code}): {response.text}"

        data       = response.json()
        dados_cube = data.get("data", data)

        if isinstance(dados_cube, list) and len(dados_cube) > 100:
            dados_cube = dados_cube[:100]
            dados_cube.append({
                "AVISO_SISTEMA_CRITICO": (
                    "LIMITE DE TOKENS ATINGIDO! Os resultados do Cube.js foram limitados a 100 linhas. "
                    "Filtre mais sua busca ou remova granularidades."
                )
            })

        return json.dumps(
            {"dados_cube": dados_cube, "sql_executado_no_banco": sql_gerado},
            ensure_ascii=False,
        )

    except requests.Timeout:
        return "Erro Cube.dev: Timeout — o servidor não respondeu em 35 segundos. Tente uma query mais filtrada."
    except json.JSONDecodeError:
        return "Erro: O parâmetro fornecido não é um JSON válido. Por favor, corrija a sintaxe."
    except Exception as e:
        return f"Erro na execução da consulta ao Cube.dev: {str(e)}"

CUBE_META_URL = f"{CUBE_BASE_URL}/cubejs-api/v1/meta"

@tool
def consultar_esquema_cube() -> str:
    """
    Lista todos os Cubos (Tabelas), Medidas (Measures) e Dimensões (Dimensions) disponíveis na Camada Semântica (Cube.dev).
    O LLM DEVE usar esta ferramenta ANTES de gerar qualquer JSON para ter certeza dos nomes exatos de medidas e dimensões.
    
    Returns:
        String contendo o dicionário/JSON com a lista de modelos disponíveis no Cube ou mensagem de erro.
    """
    try:
        token = generate_cube_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(CUBE_META_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # Retorna simplificado: Apenas nomes de cubos, medidas e dimensoes
            schema_summary = {}
            for cube in data.get("cubes", []):
                cube_name = cube.get("name")
                schema_summary[cube_name] = {
                    "measures": [m.get("name") for m in cube.get("measures", [])],
                    "dimensions": [d.get("name") for d in cube.get("dimensions", [])]
                }
            return json.dumps(schema_summary, ensure_ascii=False, indent=2)
        else:
            return f"Erro Cube.dev Meta (Status {response.status_code}): {response.text}"
            
    except Exception as e:
        return f"Erro na listagem do esquema do Cube.dev: {str(e)}"
