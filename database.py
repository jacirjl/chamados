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

    # --- Tabela de Usuários (Inalterada) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        municipio TEXT NOT NULL,
        responsavel TEXT NOT NULL,
        telefone TEXT NOT NULL,
        must_reset_password BOOLEAN DEFAULT 1,
        is_admin BOOLEAN DEFAULT 0
    );
    ''')

    # --- Tabela de Equipamentos ---
    cursor.execute('DROP TABLE IF EXISTS smartphones')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS equipamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        municipio TEXT NOT NULL,
        imei1 TEXT UNIQUE,
        imei2 TEXT UNIQUE,
        marca TEXT,
        modelo TEXT,
        capacidade TEXT,
        numeroDeSerie TEXT,
        dataEntrega TEXT,
        localdeUso TEXT,
        situacao TEXT,
        patrimonio TEXT
    );
    ''')
    print("Tabela 'equipamentos' criada/verificada.")

    # --- Tabela de Chamados (Com novo campo 'solucao') ---
    cursor.execute('DROP TABLE IF EXISTS chamados')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chamados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        solicitante_email TEXT NOT NULL,
        municipio TEXT NOT NULL,
        smartphone_imei TEXT NOT NULL,
        tipo_problema TEXT NOT NULL,
        observacoes TEXT NOT NULL,
        status TEXT DEFAULT 'Aberto', 
        foto TEXT,
        solucao TEXT
    );
    ''')
    print("Tabela 'chamados' criada/verificada.")

    conn.commit()


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
            'município': 'municipio', 'imei1': 'imei1', 'imei2': 'imei2', 'marca': 'marca',
            'modelo': 'modelo', 'capacidade': 'capacidade', 'numerodeserie': 'numeroDeSerie',
            'dataentrega': 'dataEntrega', 'localdeuso': 'localdeUso', 'situação': 'situacao',
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
    if not os.path.exists(EXCEL_FILE):
        print(f"\nAVISO: '{EXCEL_FILE}' não encontrado. As tabelas foram criadas, mas não populadas.")
    else:
        populate_users()
        populate_equipamentos()
    conn.close()
    print("\nProcesso de inicialização do banco de dados concluído.")