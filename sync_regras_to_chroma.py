import os
import sys
import chromadb
from tools import get_connection
# Usamos embeddings do LangChain/OpenAI
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

# Caminho de persistência para o ChromaDB
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_data")
COLLECTION_NAME = "regras_negocio"

def get_regras_from_db():
    """Busca todas as regras ativas na tabela do banco."""
    conn = get_connection()
    if not conn:
        print("Erro: Não foi possível conectar ao banco de dados para ler as regras.")
        sys.exit(1)
        
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ID, CONTEXTO, REGRA, TABELA_ALVO, PALAVRAS_CHAVE FROM AI_REGRAS_NEGOCIO WHERE STATUS = 'ATIVA'")
        rows = cursor.fetchall()
        
        regras = []
        for row in rows:
            regras.append({
                "id": str(row[0]),
                "contexto": row[1] or "",
                "regra": row[2] or "",
                "tabela_alvo": row[3] or "",
                "palavras_chave": row[4] or ""
            })
        return regras
    except Exception as e:
        print(f"Erro ao buscar regras no banco: {e}")
        return []
    finally:
        conn.close()

def sync_to_chroma(regras):
    """Vetoriza e salva as regras no ChromaDB local."""
    if not regras:
        print("Nenhuma regra ativa encontrada para sincronizar.")
        return

    print("Inicializando OpenAI Embeddings...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    print(f"Conectando ao banco vetorial Chroma em {CHROMA_PERSIST_DIR}...")
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PERSIST_DIR
    )
    
    # Limpa a coleção antiga para evitar regras órfãs
    try:
        vector_store.delete_collection()
        print("Coleção anterior deletada com sucesso para evitar regras velhas.")
        # Precisamos recriar a instância do vector store após deletar a coleção
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=CHROMA_PERSIST_DIR
        )
    except Exception as e:
        print(f"Nota: Nenhuma coleção antiga para deletar (ou erro leve ignorado): {e}")

    # Prepara os dados pro Chroma
    texts = []
    metadatas = []
    ids = []
    
    for r in regras:
        texts.append(r["regra"])
        # Metadados são excelentes para debug e filtros duros (onde a inteligência acontece)
        metadatas.append({
            "contexto": r["contexto"],
            "tabela_alvo": r["tabela_alvo"],
            "palavras_chave": r["palavras_chave"],
            "source": "AI_REGRAS_NEGOCIO"
        })
        ids.append(f"regra_{r['id']}")

    print(f"Vetorizando e persistindo {len(texts)} regras no ChromaDB...")
    try:
        # Chroma trata inserts/updates pelo ID automaticamente
        vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        print("✓ Sincronização concluída com sucesso! Vetores gerados e salvos localmente.")
    except Exception as e:
        print(f"Erro na sincronização vetorial: {e}")

if __name__ == "__main__":
    print("--- INICIANDO PIPELINE DE RAG (BANCO -> CHROMA_DB) ---")
    historico_regras = get_regras_from_db()
    
    if historico_regras:
        print(f"Foram encontradas {len(historico_regras)} regras marcadas como ATIVAS.")
        sync_to_chroma(historico_regras)
    else:
        print("Pipeline finalizado. Nenhuma ação necessária.")
