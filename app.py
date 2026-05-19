import streamlit as st
import json
import uuid
import sys
import os

# Ajuste do path para importar os módulos locais do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage
from langgraph_app import get_compiled_graph

# Configuração da Página
st.set_page_config(
    page_title="BI Copilot - Assistente Comercial",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar estado da sessão
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []
    
if "graph_app" not in st.session_state:
    try:
        # Tenta compilar o LangGraph e armazená-lo para otimização
        st.session_state.graph_app = get_compiled_graph()
    except Exception as e:
        st.error(f"Erro ao inicializar o motor de IA: {e}")
        st.stop()

# Estilos CSS Injetados
st.markdown("""
<style>
    .reportview-container {
        background: #fafafa
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1 {
        color: #1e3d59;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .stChatMessage {
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Layout: Título
st.title("🧭 Assistente de BI Inteligente")
st.markdown("Pergunte em linguagem natural sobre as vendas e o faturamento corporativo.")

# Cria o contêiner do histórico de chat
chat_container = st.container()

# Exibir mensagens anteriores
with chat_container:
    if not st.session_state.messages:
        # Mensagem inicial de boas-vindas
        with st.chat_message("assistant"):
            st.markdown("Olá! Sou o seu assistente de BI integrado à Camada Semântica. Como posso te ajudar hoje? (ex: *Qual foi o faturamento total da Distribuidora 1?*)")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Caixa de Entrada do Usuário
if user_input := st.chat_input("Pergunte aos seus dados..."):
    # Salva e mostra a mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": user_input})
    with chat_container:
        with st.chat_message("user"):
            st.markdown(user_input)

    # Invoca o LangGraph
    with chat_container:
        with st.chat_message("assistant"):
            with st.spinner("Analisando dados e estruturando a consulta..."):
                try:
                    config = {"configurable": {"thread_id": st.session_state.session_id}}
                    
                    resultado = st.session_state.graph_app.invoke(
                        {"messages": [HumanMessage(content=user_input)]}, 
                        config=config
                    )
                    
                    # Recuperar a última mensagem devolvida pelo Agente
                    resposta_final = resultado["messages"][-1].content
                    
                    st.markdown(resposta_final)
                    st.session_state.messages.append({"role": "assistant", "content": resposta_final})
                    
                    # DEBUG VISUAL DA QUERY CUBE.DEV E SQL
                    cube_payload_str = None
                    # List of dicts to store SQLs from the DB
                    db_sqls_executed = []
                    
                    for msg in resultado["messages"]:
                        # 1. Pega os Argumentos de Entrada (O JSON enviado pelo LLM no caso do Cube.dev)
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            for t in msg.tool_calls:
                                if t['name'] == 'executar_consulta_cube':
                                    cube_payload_str = t['args'].get('query_json_str', t['args'].get('query_json', '{}'))
                                    
                        # 2. Pega a Resposta da Ferramenta (Onde abstraímos o SQL Real em JSON para Cube/Positivação/Magico)
                        if getattr(msg, 'type', '') == 'tool':
                            try:
                                import json
                                res_dict = json.loads(msg.content)
                                if isinstance(res_dict, dict) and "sql_executado_no_banco" in res_dict:
                                    db_sqls_executed.append({
                                        "tool": msg.name,
                                        "sql": res_dict["sql_executado_no_banco"]
                                    })
                            except:
                                pass
                    
                    # Exibe no Expander as 4 Abas Analíticas
                    rag_context_text = resultado.get("rag_context", "")
                    if cube_payload_str or db_sqls_executed or rag_context_text:
                        with st.expander("🛠️ Ver Bastidores e Queries (Cube / SQL / RAG / Fluxo)"):
                            tab1, tab2, tab3, tab4 = st.tabs(["JSON Cube", "SQL Executado", "Regras Extraídas RAG", "Fluxo do Agente"])
                            
                            with tab1:
                                if cube_payload_str:
                                    st.markdown("**Requisição Semântica gerada pelo LLM:**")
                                    st.code(cube_payload_str, language="json")
                                else:
                                    st.info("Nenhuma consulta JSON Cube.dev orquestrada nesta iteração.")
                                    
                            with tab2:
                                if db_sqls_executed:
                                    for sql_entry in db_sqls_executed:
                                        st.markdown(f"**Query SQL Direta originada na Tool `{sql_entry['tool']}`:**")
                                        st.code(sql_entry['sql'], language="sql")
                                else:
                                    st.info("Nenhuma Query SQL direta rodou explicitamente neste passo.")
                                    
                            with tab3:
                                st.markdown("**Contexto Purificado do Banco Vetorial (ChromaDB):**")
                                if rag_context_text and len(rag_context_text.strip()) > 5:
                                    st.markdown(rag_context_text)
                                else:
                                    st.info("O Agente julgou a pergunta e foi em frente. Nenhuma regra restritiva vetorial cruzou matematicamente o limite do sistema para esta questão.")
                                    
                            with tab4:
                                st.markdown("**Rastro Cognitivo do Agente (CoT):**")
                                for m in resultado["messages"]:
                                    if m.type == "human":
                                        st.write(f"🧑‍💼 **Usuário:** {m.content}")
                                    elif m.type == "ai":
                                        if hasattr(m, 'tool_calls') and m.tool_calls:
                                            for call in m.tool_calls:
                                                st.write(f"🧠 **IA Decidiu Executar Ferramenta:** `{call['name']}`")
                                                st.caption(f"Argumentos: `{call['args']}`")
                                        if m.content:
                                            st.write(f"🤖 **IA Pensou/Respondeu:** {m.content[:200]}...")
                                    elif m.type == "tool":
                                        st.write(f"⚙️ **Retorno da Ferramenta (`{m.name}`):** Leitura de Base concluída ({len(m.content)} chars).")
                        
                        # Salva a bolha do histórico referenciando os bastidores
                        st.session_state.messages.append({"role": "assistant", "content": f"🛠️ **Regras vetoriais lidas e dados extraídos.**"})
                        
                except Exception as e:
                    st.error(f"Infelizmente encontrei um erro crítico: {str(e)}")
