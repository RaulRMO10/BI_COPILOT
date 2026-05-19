"""
FastAPI Server — Bridge entre o Laravel e o Agente LangGraph.
Roda em: uvicorn fastapi_server:app --host 127.0.0.1 --port 8501
IMPORTANTE: usar --host 127.0.0.1 (não 0.0.0.0) para aceitar apenas conexões locais.
"""

import os
import sys
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, AsyncGenerator
from queue import Queue, Empty

# Garante que os imports locais do projeto funcionem
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Depends, Security, Request as FastAPIRequest
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.callbacks import BaseCallbackHandler

import oracledb
from tools import get_connection
from langgraph_app import get_compiled_graph


# ---------------------------------------------------------------------------
# Helpers de persistência de chats
# ---------------------------------------------------------------------------
def _registrar_chat(session_id: str, funcionario: str, titulo: str) -> None:
    """Insere ou ATUALIZA o registro do chat na tabela AI_CHATS."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            """MERGE INTO AI_CHATS T
               USING DUAL ON (T.SESSION_ID = :sid)
               WHEN MATCHED THEN UPDATE SET TITULO = :titulo
               WHEN NOT MATCHED THEN INSERT (SESSION_ID, FUNCIONARIO, TITULO, CREATED_AT)
               VALUES (:sid, :func, :titulo, SYSTIMESTAMP AT TIME ZONE 'America/Sao_Paulo')""",
            sid=session_id, func=funcionario, titulo=titulo[:300],
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[WARN] Falha ao registrar chat: {e}")


def _extrair_sqls(messages: list) -> str:
    """Extrai os SQLs realmente executados no banco a partir das mensagens."""
    sqls = []
    for msg in messages:
        # 1) SQL livre — o próprio arg já é o SQL do banco
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {})
                if name == "executar_consulta_sql_livre":
                    sql = args.get("query", "").strip()
                    if sql:
                        sqls.append(sql)
        # 2) Cube — pegar o SQL real que o Cube gerou (campo sql_executado_no_banco)
        if hasattr(msg, "name") and msg.name == "executar_consulta_cube":
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    sql_real = parsed.get("sql_executado_no_banco", "").strip()
                    if sql_real and sql_real != "SQL não disponível":
                        sqls.append(sql_real)
                except (json.JSONDecodeError, AttributeError):
                    pass
    return ";;\n".join(sqls) if sqls else None


def _registrar_conversa(session_id: str, funcionario: str,
                        pergunta: str, resposta: str, messages: list) -> None:
    """Insere o par pergunta/resposta na tabela AI_CONVERSAS (auditoria)."""
    try:
        sql_executado = _extrair_sqls(messages)
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            """INSERT INTO AI_CONVERSAS
               (SESSION_ID, FUNCIONARIO, PERGUNTA, RESPOSTA, SQL_EXECUTADO, CREATED_AT)
               VALUES (:sid, :func, :perg, :resp, :sqls,
                       SYSTIMESTAMP AT TIME ZONE 'America/Sao_Paulo')""",
            sid=session_id, func=funcionario,
            perg=pergunta, resp=resposta,
            sqls=sql_executado,
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[WARN] Falha ao registrar conversa: {e}")


def _listar_chats(funcionario: str) -> list[dict]:
    """Retorna os últimos 30 chats do funcionário, do mais recente ao mais antigo."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            """SELECT SESSION_ID, TITULO,
                      TO_CHAR(CREATED_AT, 'DD/MM/YYYY HH24:MI') AS DT_CRIACAO
               FROM AI_CHATS
               WHERE FUNCIONARIO = :func
               ORDER BY CREATED_AT DESC
               FETCH FIRST 30 ROWS ONLY""",
            func=funcionario,
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"session_id": r[0], "titulo": r[1], "created_at": r[2]} for r in rows]
    except Exception as e:
        print(f"[WARN] Falha ao listar chats: {e}")
        return []


def _deletar_chat(session_id: str, funcionario: str) -> bool:
    """Remove o chat e seu histórico de checkpoints. Verifica ownership."""
    try:
        conn = get_connection()
        cur  = conn.cursor()
        # Garante que o chat pertence ao funcionário (sem acesso cruzado)
        cur.execute(
            "SELECT COUNT(*) FROM AI_CHATS WHERE SESSION_ID=:sid AND FUNCIONARIO=:func",
            sid=session_id, func=funcionario,
        )
        if cur.fetchone()[0] == 0:
            cur.close(); conn.close()
            return False
        cur.execute("DELETE FROM AI_SESSAO_CHAT WHERE SESSION_ID = :sid", sid=session_id)
        cur.execute("DELETE FROM AI_CHATS WHERE SESSION_ID = :sid", sid=session_id)
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[WARN] Falha ao deletar chat: {e}")
        return False


def _validar_ownership_sessao(session_id: str, funcionario: str) -> bool:
    """
    Verifica se a sessão pertence ao funcionário consultando AI_CHATS.
    Retorna True se o registro existe (ownership confirmado).
    Retorna False se o registro NÃO existe — o chamador deve tratar como acesso negado
    OU como sessão nova legítima (ainda não registrada).
    """
    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM AI_CHATS WHERE SESSION_ID=:sid AND FUNCIONARIO=:func",
            sid=session_id, func=funcionario,
        )
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[WARN] Falha ao validar ownership da sessão: {e}")
        return False

# Mapeamento de nomes internos de tools → mensagens amigáveis para o usuário
_TOOL_STATUS: dict[str, str] = {
    "buscar_representante":          "Identificando o representante...",
    "buscar_grupo_cliente":          "Consultando grupo do cliente...",
    "buscar_departamento":           "Verificando o departamento...",
    "buscar_cidade":                 "Localizando a cidade...",
    "buscar_produto":                "Procurando o produto...",
    "buscar_cadastro_cliente":       "Buscando dados do cliente...",
    "consultar_esquema_cube":        "Mapeando as métricas disponíveis...",
    "executar_consulta_cube":        "Consultando os indicadores...",
    "executar_positivacao_privado":  "Calculando positivação...",
    "executar_positivacao_publico":  "Calculando positivação do setor público...",
    "executar_consulta_sql_livre":   "Calculando no banco de dados...",
}

_SENTINEL = object()  # Marca o fim da fila


class _StatusCallbackHandler(BaseCallbackHandler):
    """Intercepta chamadas de tools e coloca status na fila."""

    def __init__(self, queue: Queue):
        super().__init__()
        self._queue = queue

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = serialized.get("name", "")
        msg  = _TOOL_STATUS.get(name, "Processando...")
        self._queue.put({"type": "status", "message": msg})

# ---------------------------------------------------------------------------
# Token de segurança — deve ser o mesmo valor configurado no .env do Laravel
# IA_FASTAPI_SECRET_TOKEN=
# ---------------------------------------------------------------------------
FASTAPI_SECRET_TOKEN = os.getenv("IA_FASTAPI_SECRET_TOKEN", "")

# Pool de threads dimensionado para até ~20 perguntas simultâneas.
# Cada request de streaming ocupa 1 thread enquanto o LLM raciocina (10-60s).
# asyncio.get_event_loop().set_default_executor() é chamado no startup.
_THREAD_POOL = ThreadPoolExecutor(max_workers=20, thread_name_prefix="bi_ia")

# ---------------------------------------------------------------------------
# Origens permitidas (Laravel → FastAPI, sempre no mesmo servidor)
# ---------------------------------------------------------------------------
_ALLOWED_ORIGINS = os.getenv(
    "FASTAPI_ALLOWED_ORIGINS",
    "http://localhost,http://127.0.0.1"
).split(",")

app = FastAPI(
    title="Pulse AI",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,   # Desabilita /openapi.json
)


# ---------------------------------------------------------------------------
# Middleware: Security headers em TODAS as respostas
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: FastAPIRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        if "server" in response.headers:
            del response.headers["server"]
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS: apenas origens do Laravel (mesmo servidor)
# Nota: TrustedHostMiddleware removido — desnecessário pois o bind em 127.0.0.1
# já garante que apenas conexões locais são aceitas.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


@app.on_event("startup")
async def _startup():
    loop = asyncio.get_event_loop()
    loop.set_default_executor(_THREAD_POOL)
    print(f"[Startup] ThreadPoolExecutor configurado: max_workers=20")
    print(f"[Startup] Origens CORS permitidas: {_ALLOWED_ORIGINS}")

security = HTTPBearer()

# ---------------------------------------------------------------------------
# Compilar o grafo uma única vez ao subir o servidor
# ---------------------------------------------------------------------------
try:
    compiled_graph = get_compiled_graph()
except Exception as e:
    compiled_graph = None
    print(f"[ERRO] Falha ao compilar o grafo LangGraph: {e}")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class UserContext(BaseModel):
    nome: str = ""
    funcionario: str = ""
    representante: str = ""
    departamento: str = ""
    tipo: str = ""
    tipo_label: str = ""
    can_see_all: bool = False


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_context: Optional[UserContext] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class ChatMeta(BaseModel):
    session_id: str
    titulo: str
    created_at: str


# ---------------------------------------------------------------------------
# Autenticação via Bearer Token
# ---------------------------------------------------------------------------
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not FASTAPI_SECRET_TOKEN:
        raise HTTPException(status_code=500, detail="Token de segurança não configurado no servidor.")
    if credentials.credentials != FASTAPI_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido ou não autorizado.")
    return credentials.credentials


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    """Verifica se o servidor está online (sem autenticação)."""
    return {
        "status": "online",
        "graph_loaded": compiled_graph is not None,
    }


@app.get("/chats")
def listar_chats(funcionario: str, token: str = Depends(verify_token)):
    """Retorna a lista dos últimos 30 chats do funcionário."""
    if not funcionario or not funcionario.strip():
        raise HTTPException(status_code=422, detail="Parâmetro funcionario obrigatório.")
    return _listar_chats(funcionario.strip())


class ChatRegistroBody(BaseModel):
    session_id: str
    funcionario: str
    titulo: str = "Nova conversa"


@app.post("/chats")
def registrar_chat_endpoint(body: ChatRegistroBody, token: str = Depends(verify_token)):
    """Pré-registra um chat com título padrão (chamado ao criar nova conversa)."""
    _registrar_chat(body.session_id, body.funcionario, body.titulo)
    return {"registered": True}


@app.delete("/chats/{session_id}")
def deletar_chat(session_id: str, funcionario: str, token: str = Depends(verify_token)):
    """Remove um chat e seus checkpoints. Valida ownership."""
    if not funcionario or not funcionario.strip():
        raise HTTPException(status_code=422, detail="Parâmetro funcionario obrigatório.")
    ok = _deletar_chat(session_id, funcionario.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Chat não encontrado ou acesso negado.")
    return {"deleted": True}


@app.get("/history/{session_id}")
def get_history(session_id: str, funcionario: str, token: str = Depends(verify_token)):
    """
    Retorna o histórico de mensagens (humano + agente) de um chat.
    Valida que o chat pertence ao funcionário antes de devolver.
    """
    if not funcionario or not funcionario.strip():
        raise HTTPException(status_code=422, detail="Parâmetro funcionario obrigatório.")
    if compiled_graph is None:
        raise HTTPException(status_code=503, detail="Motor de IA não disponível.")

    # Valida ownership
    chats = _listar_chats(funcionario.strip())
    ids = [c["session_id"] for c in chats]
    if session_id not in ids:
        raise HTTPException(status_code=403, detail="Acesso negado ou chat não encontrado.")

    try:
        config = {"configurable": {"thread_id": session_id}}
        state  = compiled_graph.get_state(config)
        if not state or not state.values:
            return []

        messages = state.values.get("messages", [])
        result   = []
        for msg in messages:
            kind = getattr(msg, "type", None) or msg.__class__.__name__.lower()
            # Inclui apenas human e ai (descarta tool calls intermediários)
            if kind in ("human", "ai"):
                content = msg.content
                # AIMessage com tool_calls mas sem conteúdo textual = descarta
                if kind == "ai" and not content:
                    continue
                # Se AIMessage tem lista (multi-part), pega só texto plano
                if isinstance(content, list):
                    content = " ".join(
                        part.get("text", "") for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ).strip()
                    if not content:
                        continue
                result.append({"role": "user" if kind == "human" else "agent", "content": str(content)})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler histórico: {str(e)}")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, token: str = Depends(verify_token)):
    """
    Recebe uma mensagem do Laravel, executa o agente LangGraph e retorna a resposta.
    O user_context é passado via config do LangGraph — o executor_node aplica
    o filtro de segurança de representante em TODOS os requests, sem exceção.
    """
    if compiled_graph is None:
        raise HTTPException(status_code=503, detail="Motor de IA não disponível. Verifique os logs do servidor.")

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=422, detail="Mensagem não pode ser vazia.")

    if len(request.message) > 4000:
        raise HTTPException(status_code=422, detail="Mensagem excede o limite de 4000 caracteres.")

    _func = (request.user_context.funcionario if request.user_context else "").strip()

    # Defesa em profundidade: o session_id deve pertencer ao funcionário autenticado.
    # Formato esperado: bi_ia_{funcionario} ou bi_ia_{funcionario}_{timestamp}
    if _func and request.session_id.startswith("bi_ia_"):
        _expected_prefix = f"bi_ia_{_func}"
        _sid = request.session_id
        if not (_sid == _expected_prefix or _sid.startswith(_expected_prefix + "_")):
            raise HTTPException(status_code=403, detail="Sessão não pertence ao usuário autenticado.")

    try:
        config = {
            "configurable": {
                "thread_id":    request.session_id,
                "user_context": request.user_context.model_dump() if request.user_context else {},
            }
        }

        resultado = compiled_graph.invoke(
            {"messages": [HumanMessage(content=request.message.strip())]},
            config=config,
        )
        resposta = resultado["messages"][-1].content

        # Registra a interação na tabela de auditoria
        _registrar_conversa(
            request.session_id, _func or "desconhecido",
            request.message.strip(), resposta or "",
            resultado.get("messages", []),
        )

        return ChatResponse(response=resposta, session_id=request.session_id)

    except Exception as e:
        if _is_rate_limit(e):
            raise HTTPException(status_code=429, detail=_MSG_RATE_LIMIT)
        raise HTTPException(status_code=500, detail=f"Erro interno do agente: {str(e)}")


# Mensagem amigável exibida ao usuário quando a OpenAI retorna HTTP 429
_MSG_RATE_LIMIT = (
    "⚠️ O serviço de IA está com muitas consultas simultâneas no momento. "
    "Aguarde alguns segundos e tente novamente."
)

def _is_rate_limit(exc: Exception) -> bool:
    """Detecta erros 429 / RateLimitError da OpenAI, mesmo quando embrulhados pelo LangChain."""
    err = str(exc)
    return (
        "429" in err
        or "rate_limit" in err.lower()
        or "RateLimitError" in type(exc).__name__
        or (hasattr(exc, "__cause__") and exc.__cause__ is not None and _is_rate_limit(exc.__cause__))
    )


# ---------------------------------------------------------------------------
# Endpoint streaming — SSE com eventos reais do LangGraph
# ---------------------------------------------------------------------------
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, token: str = Depends(verify_token)):
    """
    Versão streaming do /chat.
    Emite eventos SSE (text/event-stream) enquanto o agente executa:
      - type=status : qual ferramenta está rodando agora
      - type=response: resposta final do agente
      - type=error  : erro durante a execução
    """
    if compiled_graph is None:
        raise HTTPException(status_code=503, detail="Motor de IA não disponível.")

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=422, detail="Mensagem não pode ser vazia.")

    if len(request.message) > 4000:
        raise HTTPException(status_code=422, detail="Mensagem excede o limite de 4000 caracteres.")

    # Defesa em profundidade: session_id deve pertencer ao funcionário autenticado.
    _stream_func = (request.user_context.funcionario if request.user_context else "").strip()
    if _stream_func and request.session_id.startswith("bi_ia_"):
        _expected_prefix = f"bi_ia_{_stream_func}"
        _sid = request.session_id
        if not (_sid == _expected_prefix or _sid.startswith(_expected_prefix + "_")):
            raise HTTPException(status_code=403, detail="Sessão não pertence ao usuário autenticado.")

    async def event_generator() -> AsyncGenerator[str, None]:
        queue: Queue = Queue()
        callback     = _StatusCallbackHandler(queue)

        config_with_cb = {
            "configurable": {
                "thread_id":    request.session_id,
                "user_context": request.user_context.model_dump() if request.user_context else {},
            },
            "callbacks": [callback],
        }

        # Registra o chat na tabela de metadados (primeira mensagem = título)
        _func = (request.user_context.funcionario if request.user_context else "") or "desconhecido"
        _titulo = request.message.strip()[:150]
        _registrar_chat(request.session_id, _func, _titulo)

        # Roda o invoke síncrono em thread separada para não bloquear o event loop
        loop = asyncio.get_event_loop()

        async def run_graph():
            try:
                resultado = await loop.run_in_executor(
                    None,
                    lambda: compiled_graph.invoke(
                        {"messages": [HumanMessage(content=request.message.strip())]},
                        config=config_with_cb,
                    ),
                )
                resposta = resultado["messages"][-1].content or ""
                queue.put({"type": "response", "message": resposta})

                # Registra a interação na tabela de auditoria (fire-and-forget)
                try:
                    _registrar_conversa(
                        request.session_id, _func,
                        request.message.strip(), resposta,
                        resultado.get("messages", []),
                    )
                except Exception:
                    pass
            except Exception as e:
                if _is_rate_limit(e):
                    queue.put({"type": "error", "message": _MSG_RATE_LIMIT})
                else:
                    queue.put({"type": "error", "message": str(e) or "Erro interno do agente."})
            finally:
                queue.put(_SENTINEL)

        graph_task = asyncio.ensure_future(run_graph())

        try:
            while True:
                # Drena eventos da fila de forma não-bloqueante
                await asyncio.sleep(0.05)
                while True:
                    try:
                        item = queue.get_nowait()
                    except Empty:
                        break
                    if item is _SENTINEL:
                        return
                    yield f"data: {json.dumps(item)}\n\n"
        finally:
            await graph_task

    return StreamingResponse(event_generator(), media_type="text/event-stream")
