import os
import yaml
import sys
from glob import glob
from tools import get_connection

YAML_DIR = os.path.join(os.path.dirname(__file__), 'cube_project', 'model')

def load_yaml_files():
    """Lê todos os arquivos YAML e extrai as measures e dimensions com seus tipos."""
    metrics_to_insert = []
    yaml_files = glob(os.path.join(YAML_DIR, '*.yaml'))

    if not yaml_files:
        print(f"Nenhum arquivo YAML encontrado no diretorio: {YAML_DIR}")
        return []

    for file_path in yaml_files:
        filename = os.path.basename(file_path)
        print(f"Lendo {filename}...")

        with open(file_path, 'r', encoding='utf-8') as file:
            try:
                content = yaml.safe_load(file)
                if not content or 'cubes' not in content:
                    continue

                for cube in content['cubes']:
                    cube_name = cube.get('name', 'unknown')

                    # Extrai measures
                    if 'measures' in cube:
                        for measure in cube['measures']:
                            metric_name = measure.get('name')
                            if metric_name:
                                metrics_to_insert.append({
                                    'nome': metric_name,
                                    'tipo': 'measure',
                                    'cubo': cube_name
                                })

                    # Extrai dimensions
                    if 'dimensions' in cube:
                        for dim in cube['dimensions']:
                            dim_name = dim.get('name')
                            if dim_name and dim_name != 'id':
                                metrics_to_insert.append({
                                    'nome': dim_name,
                                    'tipo': 'dimension',
                                    'cubo': cube_name
                                })
            except Exception as e:
                print(f"Erro ao parsear arquivo {filename}: {e}")

    return metrics_to_insert

def sync_to_db(metrics):
    """Insere as métricas extraídas no banco ignorando as que já existem."""
    if not metrics:
        print("Nenhuma métrica para sincronizar.")
        return

    conn = get_connection()
    if not conn:
        print("Erro: Não foi possível conectar ao banco de dados.")
        sys.exit(1)

    cursor = conn.cursor()
    inserted_count = 0

    try:
        cursor.execute("SELECT NOME_METRICA FROM AI_CONTROLE_METRICAS")
        existing_metrics = {row[0] for row in cursor.fetchall()}

        sql_insert = """
            INSERT INTO AI_CONTROLE_METRICAS
            (NOME_METRICA, TIPO, CUBE_FONTE, STATUS)
            VALUES (%s, %s, %s, 'INATIVA')
            ON CONFLICT (NOME_METRICA) DO NOTHING
        """

        for metric in metrics:
            chave = metric['nome']
            if chave not in existing_metrics:
                try:
                    cursor.execute(sql_insert, (metric['nome'], metric['tipo'], metric['cubo']))
                    inserted_count += cursor.rowcount
                except Exception as ex:
                    print(f"Erro inserindo {chave}: {ex}")

        conn.commit()
        print(f"Sincronização concluída! {inserted_count} novas métricas/dimensões dos YAMLs inseridas no banco como INATIVAS.")
        print("As métricas/dimensões já existentes não foram duplicadas.")

    except Exception as e:
        print(f"Erro ao inserir no banco: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("Iniciando varredura dos YAMLs Semânticos do Cube.js...")
    metrics_found = load_yaml_files()
    print(f"Total de entidades mapeadas nos YAMLs: {len(metrics_found)}")
    print("Sincronizando com o Dicionário IA no banco (AI_CONTROLE_METRICAS)...")
    sync_to_db(metrics_found)
