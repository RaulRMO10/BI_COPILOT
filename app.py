import streamlit as st
import json
import uuid
import sys
import os

# Ajuste do path para importar os módulos locais do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage

# Configuração da Página
st.set_page_config(
    page_title="BI Copilot - Assistente Comercial",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# Usuários de demonstração (dados reais do seed — senha única de demo)
# O user_context alimenta a RLS do agente: diretor vê tudo; consultores são
# filtrados no código (secure_tool_node) para a própria carteira/departamento.
# ─────────────────────────────────────────────────────────────────────────────
SENHA_DEMO = "demo123"
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

# Estilos CSS Injetados
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1 { color: #1e3d59; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .stChatMessage { border-radius: 10px; padding: 10px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TELA DE LOGIN
# ─────────────────────────────────────────────────────────────────────────────
if "usuario" not in st.session_state:
    col_esq, col_login, col_dir = st.columns([1, 1.2, 1])
    with col_login:
        st.title("🧭 BI Copilot")
        st.caption("Assistente Comercial Inteligente — ambiente de demonstração")

        with st.form("login"):
            login = st.text_input("Usuário").strip().lower()
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            if login in USUARIOS_DEMO and senha == SENHA_DEMO:
                st.session_state.usuario = USUARIOS_DEMO[login]
                st.session_state.messages = []
                st.session_state.session_id = (
                    f"bi_ia_{USUARIOS_DEMO[login]['user_context']['funcionario']}_{uuid.uuid4().hex[:8]}"
                )
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

        with st.expander("🔑 Credenciais de demonstração"):
            st.markdown(f"Senha para todos: `{SENHA_DEMO}`")
            for u, dados in USUARIOS_DEMO.items():
                st.markdown(f"- `{u}` — {dados['icone']} **{dados['user_context']['nome']}** · {dados['cargo']}")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# APP LOGADO
# ─────────────────────────────────────────────────────────────────────────────
usuario = st.session_state.usuario
ctx = usuario["user_context"]

if "graph_app" not in st.session_state:
    try:
        from langgraph_app import get_compiled_graph
        st.session_state.graph_app = get_compiled_graph()
    except Exception as e:
        st.error(f"Erro ao inicializar o motor de IA: {e}")
        st.stop()

# Sidebar: identidade + ações
with st.sidebar:
    st.markdown(f"### {usuario['icone']} {ctx['nome']}")
    st.caption(usuario["cargo"])
    if ctx["representante"]:
        st.caption(f"Representante `{ctx['representante']}` · Depto `{ctx['departamento']}`")
    else:
        st.caption("Acesso total (sem filtro de representante)")
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
    st.caption("Dados de demonstração: Olist (CC BY-NC-SA) + CMED/ANVISA + IBGE + camadas sintéticas. "
               "Nenhum dado real de empresa.")

st.title("🧭 Assistente de BI Inteligente")
st.markdown("Pergunte em linguagem natural sobre vendas, carteira, metas, crédito e estoque.")

chat_container = st.container()

with chat_container:
    if not st.session_state.messages:
        with st.chat_message("assistant"):
            sugestao = ("*Qual foi o faturamento deste mês?* ou *Como está o quadrante de julho?*"
                        if ctx["can_see_all"]
                        else "*Como estou em relação à minha meta?* ou *Quais meus melhores clientes do mês?*")
            st.markdown(f"Olá, **{ctx['nome'].split()[0] if ctx['nome'] else 'tudo bem'}**! "
                        f"Sou seu assistente de BI. Experimente: {sugestao}")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Caixa de Entrada do Usuário
if user_input := st.chat_input("Pergunte aos seus dados..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.markdown(user_input)

    with chat_container:
        with st.chat_message("assistant"):
            with st.spinner("Analisando dados e estruturando a consulta..."):
                try:
                    # user_context: é isto que ativa a RLS no executor/secure_tool_node
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.session_id,
                            "user_context": ctx,
                        }
                    }

                    resultado = st.session_state.graph_app.invoke(
                        {"messages": [HumanMessage(content=user_input)]},
                        config=config
                    )

                    resposta_final = resultado["messages"][-1].content
                    if isinstance(resposta_final, list):  # conteúdo multi-parte (ex.: Claude)
                        resposta_final = " ".join(
                            p.get("text", "") for p in resposta_final
                            if isinstance(p, dict) and p.get("type") == "text"
                        )

                    st.markdown(resposta_final)
                    st.session_state.messages.append({"role": "assistant", "content": resposta_final})

                    # ── Bastidores: JSON Cube, SQL executado e fluxo do agente ──
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
                                    db_sqls_executed.append({
                                        "tool": msg.name,
                                        "sql": res_dict["sql_executado_no_banco"]
                                    })
                            except Exception:
                                pass

                    rag_context = resultado.get("rag_context", "")
                    if cube_payload_str or db_sqls_executed or rag_context:
                        with st.expander("🛠️ Bastidores (JSON Cube / SQL / Regras / Fluxo)"):
                            tab1, tab2, tab4, tab3 = st.tabs(
                                ["JSON Cube", "SQL Executado", "Regras de Negócio (RAG)", "Fluxo do Agente"])

                            with tab4:
                                st.markdown("**Política comercial injetada no contexto do agente** "
                                            "(regras inteiras, sempre presentes — fonte: `regras/politica_comercial.md`):")
                                if rag_context:
                                    st.markdown(rag_context)
                                else:
                                    st.info("Caderno de regras não carregado nesta interação.")

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
                                            conteudo = " ".join(p.get("text", "") for p in conteudo
                                                                if isinstance(p, dict))
                                        if conteudo:
                                            st.write(f"🤖 **IA respondeu:** {str(conteudo)[:200]}...")
                                    elif m.type == "tool":
                                        st.write(f"⚙️ **Retorno de `{m.name}`:** {len(str(m.content))} chars lidos.")

                except Exception as e:
                    st.error(f"Infelizmente encontrei um erro crítico: {str(e)}")
