# database.py

import sqlite3
import os
import pandas as pd
from werkzeug.security import generate_password_hash

# --- Configurações ---
INSTANCE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
DATABASE = os.path.join(INSTANCE_FOLDER, 'chamados.db')
EXCEL_FILE = 'suporte.xlsx'
DEFAULT_PASSWORD = '12345'

os.makedirs(INSTANCE_FOLDER, exist_ok=True)
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()
print("Conectado ao banco de dados.")


# --- Funções para criar/atualizar as tabelas ---
def setup_tables():
    """Cria as tabelas com a nova estrutura."""

    # --- NOVAS TABELAS ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    );
    ''')
    print("Tabela 'status' criada/verificada.")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tipos_problema (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    );
    ''')
    print("Tabela 'tipos_problema' criada/verificada.")

    # --- TABELAS ANTIGAS ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        municipio TEXT NOT NULL, responsavel TEXT NOT NULL, telefone TEXT NOT NULL,
        must_reset_password BOOLEAN DEFAULT 1, is_admin BOOLEAN DEFAULT 0
    );
    ''')
    print("Tabela 'users' criada/verificada.")

    cursor.execute('DROP TABLE IF EXISTS equipamentos')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS equipamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, municipio TEXT NOT NULL, imei1 TEXT UNIQUE, imei2 TEXT,
        marca TEXT, modelo TEXT, capacidade TEXT, numeroDeSerie TEXT, dataEntrega TEXT,
        localdeUso TEXT, situacao TEXT, patrimonio TEXT
    );
    ''')
    print("Tabela 'equipamentos' criada/verificada.")

    # --- TABELA CHAMADOS ATUALIZADA ---
    cursor.execute('DROP TABLE IF EXISTS chamados')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chamados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        solicitante_email TEXT NOT NULL,
        municipio TEXT NOT NULL,
        smartphone_imei TEXT NOT NULL,
        tipo_problema_id INTEGER NOT NULL,
        observacoes TEXT NOT NULL,
        status_id INTEGER NOT NULL,
        foto TEXT,
        solucao TEXT,
        admin_responsavel_id INTEGER,
        FOREIGN KEY (tipo_problema_id) REFERENCES tipos_problema (id),
        FOREIGN KEY (status_id) REFERENCES status (id),
        FOREIGN KEY (admin_responsavel_id) REFERENCES users (id)
    );
    ''')
    print("Tabela 'chamados' atualizada/verificada.")

    conn.commit()


def populate_lookup_tables():
    """Popula as novas tabelas com valores padrão."""
    default_status = ['Aberto', 'Em Andamento', 'Aguardando Peça', 'Finalizado', 'Cancelado']
    default_problemas = ['Octostudio', 'Sistema Operacional', 'Hardware/Dispositivo', 'Dúvidas/Outros']

    try:
        cursor.executemany("INSERT OR IGNORE INTO status (nome) VALUES (?)", [(s,) for s in default_status])
        cursor.executemany("INSERT OR IGNORE INTO tipos_problema (nome) VALUES (?)", [(p,) for p in default_problemas])
        conn.commit()
        print("Tabelas 'status' e 'tipos_problema' populadas com valores padrão.")
    except Exception as e:
        print(f"Erro ao popular tabelas de lookup: {e}")


def populate_users():
    """Lê a aba 'Cadastro' e insere/atualiza usuários."""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='Cadastro')
        df.columns = [str(col).lower().strip() for col in df.columns]

        for index, row in df.iterrows():
            cursor.execute("SELECT id FROM users WHERE email = ?", (row['email'],))
            if cursor.fetchone() is None:
                is_admin_flag = 1 if 'admin' in df.columns and str(row.get('admin', '')).lower() == 'sim' else 0
                cursor.execute(
                    "INSERT INTO users (email, password, municipio, responsavel, telefone, must_reset_password, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (row['email'], DEFAULT_PASSWORD, row['município'], row['responsável'], str(row['telefone']), 1,
                     is_admin_flag)
                )
        conn.commit()
        print("Usuários populados com sucesso.")
    except Exception as e:
        print(f"\nAVISO: Não foi possível popular usuários. Aba 'Cadastro' não encontrada ou erro: {e}")


def populate_equipamentos():
    """Lê a aba de equipamentos da planilha e insere os dados na nova tabela."""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='equipamentos')

        df.columns = [str(col).lower().strip() for col in df.columns]

        column_map = {
            'município': 'municipio', 'imei 1': 'imei1', 'imei 2': 'imei2', 'marca': 'marca',
            'modelo': 'modelo', 'capacidade': 'capacidade', 'numero de serie': 'numeroDeSerie',
            'data da entrega': 'dataEntrega', 'local de uso': 'localdeUso', 'situação': 'situacao',
            'patrimonio': 'patrimonio'
        }
        df.rename(columns=column_map, inplace=True)

        expected_cols = list(column_map.values())
        df_cols_to_insert = {col: df[col] for col in expected_cols if col in df.columns}
        df_to_insert = pd.DataFrame(df_cols_to_insert)

        df_to_insert.to_sql('equipamentos', conn, if_exists='append', index=False)
        print("Equipamentos populados com sucesso.")
    except Exception as e:
        print(f"\nAVISO: Não foi possível popular equipamentos. Aba 'equipamentos' não encontrada ou erro: {e}")


# --- Execução Principal ---
if __name__ == '__main__':
    setup_tables()
    populate_lookup_tables()

    if os.path.exists(EXCEL_FILE):
        populate_users()
        populate_equipamentos()
    else:
        print(
            f"\nAVISO: '{EXCEL_FILE}' não encontrado. As tabelas foram criadas, mas não populadas com dados da planilha.")

    conn.close()
    print("\nProcesso de inicialização do banco de dados concluído.")