import streamlit as st
import json
import uuid
import sys
import os

# ─────────────────────────────────────────────────────────────────────────────
# Ponte Streamlit Cloud → variáveis de ambiente.
# No Streamlit Community Cloud os segredos vivem em st.secrets e NÃO viram env
# vars sozinhos; os módulos do agente (tools/langgraph_app/cube_tools) leem via
# os.getenv. Copiamos os valores string para o ambiente ANTES de qualquer import
# desses módulos. A seção [auth] (tabela) é ignorada — st.login a lê direto.
# ─────────────────────────────────────────────────────────────────────────────
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass

# Ajuste do path para importar os módulos locais do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────
DEMO_MODE = os.getenv("DEMO_MODE", "false").strip().lower() in ("1", "true", "yes")
LIMITE_PERGUNTAS = int(os.getenv("DEMO_LIMITE_PERGUNTAS", "10"))     # por pessoa
LIMITE_GLOBAL_DIA = int(os.getenv("DEMO_LIMITE_GLOBAL_DIA", "300"))  # disjuntor global
LINKEDIN_URL = os.getenv("LINKEDIN_URL", "https://www.linkedin.com/in/raulrmo/")
GITHUB_URL = os.getenv("GITHUB_URL", "https://github.com/RaulRMO10/BI_COPILOT")

st.set_page_config(
    page_title="BI Copilot — Assistente Comercial",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Perfis (personas) — dados reais do seed. No modo demo o usuário loga com Google
# (identidade/crédito) e escolhe qual perfil explorar (mostra a RLS em ação).
# ─────────────────────────────────────────────────────────────────────────────
SENHA_DEMO = "demo123"  # usado apenas no login LOCAL (DEMO_MODE=false)
USUARIOS_DEMO = {
    "joao": {
        "icone": "👔",
        "cargo": "Diretor Comercial — visão total",
        "user_context": {
            "nome": "Dr. João Felipe Azevedo", "funcionario": "001",
            "representante": "", "departamento": "", "tipo": "1",
            "tipo_label": "Diretor", "can_see_all": True,
        },
    },
    "brenda": {
        "icone": "💼",
        "cargo": "Consultora — Carteira Privada (rep 001)",
        "user_context": {
            "nome": "Brenda Alves", "funcionario": "1001",
            "representante": "001", "departamento": "001", "tipo": "3",
            "tipo_label": "Consultora de Vendas", "can_see_all": False,
        },
    },
    "hellena": {
        "icone": "🏛️",
        "cargo": "Consultora — Canal Público / Municípios (rep 029)",
        "user_context": {
            "nome": "Dra. Hellena Rodrigues", "funcionario": "1029",
            "representante": "029", "departamento": "002", "tipo": "3",
            "tipo_label": "Consultora de Vendas", "can_see_all": False,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Perguntas-exemplo por perfil (todas testadas contra o agente).
# (texto, é_segurança) — as de segurança demonstram a RLS bloqueando o acesso.
# ─────────────────────────────────────────────────────────────────────────────
EXEMPLOS = {
    "joao": [
        ("Qual foi o faturamento no mês passado?", False),
        ("Me mostra o quadrante de vendas do mês passado", False),
        ("Quantos clientes inadimplentes temos e qual o valor total em atraso?", False),
        ("Compare o faturamento total da empresa no mês passado com o mês anterior", False),
        ("Qual foi a positivação de clientes no mês passado?", False),
        ("Qual foi o ticket médio no mês passado?", False),
        ("Qual foi a margem de desconto média no mês passado?", False),
        ("Quais foram os 10 produtos mais vendidos no mês passado?", False),
        ("Qual o total de limite de crédito concedido e quanto está disponível?", False),
        ("Quantas cidades foram positivadas no mês passado?", False),
    ],
    "brenda": [
        ("Quais são meus 5 melhores clientes do mês passado?", False),
        ("Como fiquei em relação à minha meta no mês passado?", False),
        ("Quais clientes da minha carteira estão em risco de perda no mês passado?", False),
        ("Qual foi meu faturamento no mês passado?", False),
        ("Quais dos meus clientes estão inadimplentes?", False),
        ("Quantos clientes eu positivei no mês passado?", False),
        ("Qual foi meu ticket médio no mês passado?", False),
        ("Me mostra meu quadrante do mês passado", False),
        ("Mostre os clientes da Hellena", True),
        ("Qual o faturamento dos outros representantes?", True),
    ],
    "hellena": [
        ("Quais municípios da minha carteira mais compraram no mês passado?", False),
        ("Qual foi meu faturamento no mês passado?", False),
        ("Quais municípios da minha carteira estão em risco de perda no mês passado?", False),
        ("Como fiquei em relação à minha meta no mês passado?", False),
        ("Qual foi minha positivação no mês passado?", False),
        ("Qual foi meu ticket médio no mês passado?", False),
        ("Quantos municípios ativos tenho na carteira?", False),
        ("Me mostra meu quadrante do mês passado", False),
        ("Quais dos meus clientes estão inadimplentes?", True),
        ("Mostre a carteira da Brenda", True),
    ],
}

st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1 { color: #1e3d59; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .stChatMessage { border-radius: 10px; padding: 10px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers do MODO DEMO (crédito, feedback, identidade, notificação)
# ═════════════════════════════════════════════════════════════════════════════
def _db():
    from tools import get_connection
    return get_connection()


def _auth_google_configurado() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _notificar(texto: str) -> None:
    """Envia um aviso ao Discord (se DISCORD_WEBHOOK_URL estiver setado). Não bloqueia."""
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests
        requests.post(url, json={"content": texto[:1900]}, timeout=4)
    except Exception:
        pass


def _demo_registrar_usuario(email: str, nome: str) -> bool:
    """Upsert do visitante. Retorna True se é a primeira vez que ele acessa."""
    conn = _db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO demo_usuarios (email, nome, limite) VALUES (%s, %s, %s)
        ON CONFLICT (email) DO UPDATE SET ultimo_acesso = now() AT TIME ZONE 'America/Sao_Paulo'
        RETURNING (xmax = 0) AS novo
    """, (email, nome, LIMITE_PERGUNTAS))
    novo = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return novo


def _demo_status(email: str):
    """Retorna (limite_do_usuario, perguntas_usadas, total_global_hoje)."""
    conn = _db()
    cur = conn.cursor()
    cur.execute("SELECT limite FROM demo_usuarios WHERE email = %s", (email,))
    row = cur.fetchone()
    limite = row[0] if row else LIMITE_PERGUNTAS
    cur.execute("SELECT count(*) FROM demo_uso WHERE email = %s", (email,))
    usadas = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM demo_uso WHERE criado_em::date = current_date")
    global_dia = cur.fetchone()[0]
    cur.close(); conn.close()
    return limite, usadas, global_dia


def _demo_registrar_pergunta(email: str, persona: str, pergunta: str) -> int | None:
    """Registra a pergunta (conta crédito) e devolve o id da linha para depois
    gravar a resposta na mesma linha."""
    conn = _db()
    cur = conn.cursor()
    cur.execute("INSERT INTO demo_uso (email, persona, pergunta) VALUES (%s, %s, %s) RETURNING id",
                (email, persona, pergunta[:500]))
    uso_id = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return uso_id


def _demo_registrar_resposta(uso_id: int, resposta: str, sql: str = "") -> None:
    """Grava a resposta do agente (e o SQL gerado) na linha da pergunta."""
    if not uso_id:
        return
    conn = _db()
    cur = conn.cursor()
    cur.execute("UPDATE demo_uso SET resposta = %s, sql_executado = %s WHERE id = %s",
                (resposta[:4000] if resposta else None, (sql or None), uso_id))
    conn.commit(); cur.close(); conn.close()


def _demo_feedback(email: str, nome: str, rating: str, comentario: str = "") -> None:
    conn = _db()
    cur = conn.cursor()
    cur.execute("INSERT INTO demo_feedback (email, nome, rating, comentario) VALUES (%s, %s, %s, %s)",
                (email, nome, rating, comentario[:1000]))
    conn.commit(); cur.close(); conn.close()
    emoji = "👍" if rating == "positivo" else "👎"
    _notificar(f"{emoji} Feedback de {nome} ({email})" + (f": {comentario}" if comentario else ""))


def _obter_identidade():
    """Retorna (email, nome) do visitante. Interrompe a execução se não logado.
    Usa login Google nativo quando [auth] está configurado; senão, um formulário
    simples de e-mail (para testar localmente sem OAuth)."""
    if _auth_google_configurado():
        if not st.user.is_logged_in:
            _tela_boas_vindas(google=True)
            st.stop()
        email = st.user.email
        nome = getattr(st.user, "name", None) or email.split("@")[0]
        return email, nome

    # Fallback local (sem OAuth): identidade por formulário, guardada na sessão
    if "demo_ident" not in st.session_state:
        _tela_boas_vindas(google=False)
        st.stop()
    ident = st.session_state.demo_ident
    return ident["email"], ident["nome"]


# ═════════════════════════════════════════════════════════════════════════════
# Telas
# ═════════════════════════════════════════════════════════════════════════════
def _tela_boas_vindas(google: bool):
    _, meio, _ = st.columns([1, 1.4, 1])
    with meio:
        st.title("🧭 BI Copilot")
        st.markdown("### Um copiloto de BI que conversa com seus dados")
        st.markdown(
            "Faça perguntas em português sobre uma **distribuidora farmacêutica fictícia** "
            "e veja o agente escolher a ferramenta, montar a consulta e responder — "
            "respeitando o **perfil de acesso** de quem pergunta.\n\n"
            f"Você tem **{LIMITE_PERGUNTAS} perguntas de cortesia**. Dados 100% sintéticos "
            "(Olist + CMED + IBGE), nenhum dado real de empresa."
        )
        st.divider()
        if google:
            st.markdown("Entre para começar — usamos seu login apenas para organizar as perguntas de cortesia.")
            if st.button("🔓  Entrar com Google", use_container_width=True, type="primary"):
                st.login()
        else:
            st.info("Modo de teste local (sem OAuth). Informe um nome e e-mail para simular a identidade.")
            with st.form("ident_local"):
                nome = st.text_input("Seu nome").strip()
                email = st.text_input("Seu e-mail").strip().lower()
                if st.form_submit_button("Começar", use_container_width=True, type="primary"):
                    if nome and "@" in email:
                        st.session_state.demo_ident = {"nome": nome, "email": email}
                        st.rerun()
                    else:
                        st.error("Informe um nome e um e-mail válido.")


def _tela_escolha_persona(email: str, nome: str):
    st.title(f"🧭 Olá, {nome.split()[0]}!")
    st.markdown("Escolha **de qual cadeira** você quer explorar o BI. O mesmo assistente "
                "responde de formas diferentes conforme o acesso do perfil — é a segurança em ação.")
    st.write("")
    cols = st.columns(3)
    exemplos = {
        "joao": "Ex.: *Qual o quadrante deste mês?* · *Quantos inadimplentes temos?*",
        "brenda": "Ex.: *Meus 5 melhores clientes?* · *Posso dar 25% de desconto?*",
        "hellena": "Ex.: *Quais municípios da minha carteira mais compraram?*",
    }
    for col, (chave, dados) in zip(cols, USUARIOS_DEMO.items()):
        with col:
            with st.container(border=True):
                st.markdown(f"### {dados['icone']} {dados['user_context']['nome']}")
                st.caption(dados["cargo"])
                st.markdown(exemplos[chave])
                if st.button("Explorar como este perfil", key=f"persona_{chave}", use_container_width=True):
                    st.session_state.usuario = dados
                    st.session_state.persona_key = chave
                    st.session_state.messages = []
                    st.session_state.session_id = f"bi_ia_{dados['user_context']['funcionario']}_{uuid.uuid4().hex[:8]}"
                    st.rerun()


def _tela_limite_global():
    _, meio, _ = st.columns([1, 1.4, 1])
    with meio:
        st.title("🧭 BI Copilot")
        st.warning("A demonstração atingiu o limite de uso de hoje. 🙏")
        st.markdown("Muita gente testando ao mesmo tempo! Volte amanhã para experimentar, "
                    f"ou veja o projeto agora mesmo:\n\n- 👨‍💻 [Código no GitHub]({GITHUB_URL})\n- 💼 [LinkedIn]({LINKEDIN_URL})")


def _tela_parede(email: str, nome: str):
    """Mostrada quando o visitante esgota as perguntas de cortesia."""
    st.title("🎉 Você explorou o BI Copilot!")
    st.markdown(f"Suas **{LIMITE_PERGUNTAS} perguntas de cortesia** acabaram, {nome.split()[0]}. "
                "Espero que tenha curtido ver um agente de BI trabalhando de verdade.")
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        st.link_button("👨‍💻 Ver o código no GitHub", GITHUB_URL, use_container_width=True)
    with c2:
        st.link_button("💼 Conectar no LinkedIn", LINKEDIN_URL, use_container_width=True)
    st.divider()
    st.markdown("#### O que você achou? Sua avaliação me ajuda muito 🙏")
    if st.session_state.get("feedback_enviado"):
        st.success("Obrigado pela avaliação! 💚")
        return
    with st.form("feedback_final"):
        rating = st.radio("De modo geral, o assistente te ajudaria no dia a dia?",
                          ["👍 Sim, achei útil", "👎 Ainda não"], horizontal=True)
        comentario = st.text_area("Quer deixar um comentário? (opcional)")
        if st.form_submit_button("Enviar avaliação", type="primary"):
            _demo_feedback(email, nome, "positivo" if rating.startswith("👍") else "negativo", comentario)
            st.session_state.feedback_enviado = True
            st.rerun()


def _tela_login_local():
    """Login por senha para desenvolvimento (DEMO_MODE=false)."""
    _, col_login, _ = st.columns([1, 1.2, 1])
    with col_login:
        st.title("🧭 BI Copilot")
        st.caption("Assistente Comercial Inteligente — ambiente de desenvolvimento")
        with st.form("login"):
            login = st.text_input("Usuário").strip().lower()
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            if login in USUARIOS_DEMO and senha == SENHA_DEMO:
                st.session_state.usuario = USUARIOS_DEMO[login]
                st.session_state.persona_key = login
                st.session_state.messages = []
                st.session_state.session_id = f"bi_ia_{USUARIOS_DEMO[login]['user_context']['funcionario']}_{uuid.uuid4().hex[:8]}"
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
        with st.expander("🔑 Credenciais de demonstração"):
            st.markdown(f"Senha para todos: `{SENHA_DEMO}`")
            for u, dados in USUARIOS_DEMO.items():
                st.markdown(f"- `{u}` — {dados['icone']} **{dados['user_context']['nome']}** · {dados['cargo']}")


# ═════════════════════════════════════════════════════════════════════════════
# FLUXO PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
demo_email = demo_nome = None
if DEMO_MODE:
    demo_email, demo_nome = _obter_identidade()
    if _demo_registrar_usuario(demo_email, demo_nome):
        _notificar(f"🎉 Novo visitante no BI Copilot: {demo_nome} ({demo_email})")
    limite, usadas, global_dia = _demo_status(demo_email)
    if global_dia >= LIMITE_GLOBAL_DIA:
        _tela_limite_global()
        st.stop()
    if "usuario" not in st.session_state:
        _tela_escolha_persona(demo_email, demo_nome)
        st.stop()
else:
    if "usuario" not in st.session_state:
        _tela_login_local()
        st.stop()

usuario = st.session_state.usuario
ctx = usuario["user_context"]

if "graph_app" not in st.session_state:
    try:
        from langgraph_app import get_compiled_graph
        st.session_state.graph_app = get_compiled_graph()
    except Exception as e:
        st.error(f"Erro ao inicializar o motor de IA: {e}")
        st.stop()

# ── Sidebar ──
with st.sidebar:
    st.markdown(f"### {usuario['icone']} {ctx['nome']}")
    st.caption(usuario["cargo"])
    if ctx["representante"]:
        st.caption(f"Representante `{ctx['representante']}` · Depto `{ctx['departamento']}`")
    else:
        st.caption("Acesso total (sem filtro de representante)")

    if DEMO_MODE:
        limite, usadas, _ = _demo_status(demo_email)
        restantes = max(0, limite - usadas)
        st.divider()
        st.markdown(f"**Perguntas de cortesia:** {restantes} de {limite}")
        st.progress(restantes / limite if limite else 0)
        st.caption(f"Logado como {demo_nome}")
        if st.button("🔄 Trocar de perfil", use_container_width=True):
            for chave in ("usuario", "messages", "session_id"):
                st.session_state.pop(chave, None)
            st.rerun()
    else:
        st.divider()
        if st.button("💬 Nova conversa", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = f"bi_ia_{ctx['funcionario']}_{uuid.uuid4().hex[:8]}"
            st.rerun()
        if st.button("🚪 Sair", use_container_width=True):
            for chave in ("usuario", "messages", "session_id"):
                st.session_state.pop(chave, None)
            st.rerun()

    st.divider()
    st.caption("Dados de demonstração: Olist (CC BY-NC-SA) + CMED/ANVISA + IBGE + camadas "
               "sintéticas. Nenhum dado real de empresa.")

st.title("🧭 Assistente de BI Inteligente")
st.markdown("Pergunte em linguagem natural sobre vendas, carteira, metas, crédito e estoque.")

# ── No modo demo, checa se o crédito acabou ANTES de deixar perguntar ──
credito_esgotado = False
if DEMO_MODE:
    limite, usadas, _ = _demo_status(demo_email)
    if usadas >= limite:
        credito_esgotado = True
        _tela_parede(demo_email, demo_nome)

chat_container = st.container()

chat_vazio = not st.session_state.messages

with chat_container:
    if chat_vazio:
        with st.chat_message("assistant"):
            primeiro_nome = ctx['nome'].split()[0] if ctx['nome'] else 'tudo bem'
            st.markdown(f"Olá, **{primeiro_nome}**! Sou seu assistente de BI. "
                        "Digite qualquer pergunta no chat abaixo — ou abra **Perguntas de exemplo** "
                        "para ver sugestões (as marcadas com 🔒 demonstram o controle de acesso).")

    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# ── Perguntas de exemplo (sugestões — o usuário pode digitar o que quiser) ──
# Ficam num popover que abre ao clicar; disponível a qualquer momento.
_pendente = None
if not credito_esgotado:
    exemplos = EXEMPLOS.get(st.session_state.get("persona_key", ""), [])
    if exemplos:
        with st.popover("💡 Perguntas de exemplo", use_container_width=False):
            st.caption("São apenas sugestões — você pode digitar qualquer pergunta no chat. "
                       "As marcadas com 🔒 mostram o controle de acesso em ação.")
            for _idx, (_texto, _seg) in enumerate(exemplos):
                _label = ("🔒 " + _texto) if _seg else _texto
                if st.button(_label, key=f"ex_{_idx}", use_container_width=True):
                    _pendente = _texto

# ── Entrada do usuário (bloqueada se o crédito acabou) ──
user_input = _pendente or (None if credito_esgotado else st.chat_input("Pergunte aos seus dados..."))

if user_input:
    _uso_id = None
    if DEMO_MODE:
        _uso_id = _demo_registrar_pergunta(demo_email, st.session_state.get("persona_key", "?"), user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.markdown(user_input)

    with chat_container:
        with st.chat_message("assistant"):
            with st.spinner("Analisando dados e estruturando a consulta..."):
                try:
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.session_id,
                            "user_context": ctx,
                        }
                    }
                    resultado = st.session_state.graph_app.invoke(
                        {"messages": [HumanMessage(content=user_input)]},
                        config=config,
                    )
                    resposta_final = resultado["messages"][-1].content
                    if isinstance(resposta_final, list):
                        resposta_final = " ".join(
                            p.get("text", "") for p in resposta_final
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    st.markdown(resposta_final)
                    st.session_state.messages.append({"role": "assistant", "content": resposta_final})

                    # ── Bastidores: JSON Cube, SQL, Regras (RAG), Fluxo ──
                    cube_payload_str = None
                    db_sqls_executed = []
                    for msg in resultado["messages"]:
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            for t in msg.tool_calls:
                                if t['name'] == 'executar_consulta_cube':
                                    cube_payload_str = t['args'].get('query_json_str', '{}')
                        if getattr(msg, 'type', '') == 'tool':
                            try:
                                res_dict = json.loads(msg.content)
                                if isinstance(res_dict, dict) and "sql_executado_no_banco" in res_dict:
                                    db_sqls_executed.append({"tool": msg.name, "sql": res_dict["sql_executado_no_banco"]})
                            except Exception:
                                pass

                    # Grava a resposta (e o SQL) na linha da pergunta — histórico completo por pessoa
                    if DEMO_MODE:
                        _sql_log = ""
                        if cube_payload_str:
                            _sql_log += f"[Cube JSON] {cube_payload_str}\n"
                        for _s in db_sqls_executed:
                            _sql_log += f"[{_s['tool']}] {_s['sql']}\n"
                        _demo_registrar_resposta(_uso_id, resposta_final, _sql_log.strip())

                    rag_context = resultado.get("rag_context", "")
                    if cube_payload_str or db_sqls_executed or rag_context:
                        with st.expander("🛠️ Bastidores (JSON Cube / SQL / Regras / Fluxo)"):
                            tab1, tab2, tab4, tab3 = st.tabs(
                                ["JSON Cube", "SQL Executado", "Regras de Negócio (RAG)", "Fluxo do Agente"])
                            with tab1:
                                if cube_payload_str:
                                    st.markdown("**Requisição Semântica gerada pelo LLM "
                                                "(já com filtros de segurança injetados pelo código):**")
                                    st.code(cube_payload_str, language="json")
                                else:
                                    st.info("Nenhuma consulta Cube nesta interação.")
                            with tab2:
                                if db_sqls_executed:
                                    for sql_entry in db_sqls_executed:
                                        st.markdown(f"**SQL originado na tool `{sql_entry['tool']}`:**")
                                        st.code(sql_entry['sql'], language="sql")
                                else:
                                    st.info("Nenhuma query SQL direta neste passo.")
                            with tab4:
                                st.markdown("**Política comercial injetada no contexto do agente** "
                                            "(regras inteiras, sempre presentes — fonte: `regras/politica_comercial.md`):")
                                if rag_context:
                                    st.markdown(rag_context)
                                else:
                                    st.info("Caderno de regras não carregado nesta interação.")
                            with tab3:
                                st.markdown("**Rastro cognitivo do agente:**")
                                for m in resultado["messages"]:
                                    if m.type == "human":
                                        st.write(f"🧑‍💼 **Usuário:** {m.content}")
                                    elif m.type == "ai":
                                        if hasattr(m, 'tool_calls') and m.tool_calls:
                                            for call in m.tool_calls:
                                                st.write(f"🧠 **IA decidiu executar:** `{call['name']}`")
                                                st.caption(f"Argumentos: `{str(call['args'])[:300]}`")
                                        conteudo = m.content
                                        if isinstance(conteudo, list):
                                            conteudo = " ".join(p.get("text", "") for p in conteudo if isinstance(p, dict))
                                        if conteudo:
                                            st.write(f"🤖 **IA respondeu:** {str(conteudo)[:200]}...")
                                    elif m.type == "tool":
                                        st.write(f"⚙️ **Retorno de `{m.name}`:** {len(str(m.content))} chars lidos.")

                    # ── Feedback rápido por resposta (só no modo demo) ──
                    if DEMO_MODE:
                        fb_key = f"fb_{len(st.session_state.messages)}"
                        c1, c2, _ = st.columns([1, 1, 6])
                        if c1.button("👍", key=fb_key + "_up", help="Resposta útil"):
                            _demo_feedback(demo_email, demo_nome, "positivo", f"[resposta] {user_input}")
                            st.toast("Obrigado pelo feedback! 💚")
                        if c2.button("👎", key=fb_key + "_down", help="Resposta ruim"):
                            _demo_feedback(demo_email, demo_nome, "negativo", f"[resposta] {user_input}")
                            st.toast("Valeu! Vou melhorar. 🙏")

                except Exception as e:
                    st.error(f"Infelizmente encontrei um erro crítico: {str(e)}")
