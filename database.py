# database.py - Adiciona o campo 'is_admin' para controle de acesso

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
    """Cria as tabelas e adiciona as novas colunas se não existirem."""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        municipio TEXT NOT NULL,
        responsavel TEXT NOT NULL,
        telefone TEXT NOT NULL
    );
      ''')
     # Cria as outras tabelas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS smartphones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, imei TEXT UNIQUE NOT NULL, marca TEXT NOT NULL,
        modelo TEXT NOT NULL, situacao TEXT NOT NULL, municipio TEXT NOT NULL
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chamados (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        solicitante_email TEXT NOT NULL, municipio TEXT NOT NULL, smartphone_imei TEXT NOT NULL,
        tipo_problema TEXT NOT NULL, observacoes TEXT NOT NULL
    );
    ''')


    # Adiciona a coluna 'must_reset_password' se não existir
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN DEFAULT 1')
    except sqlite3.OperationalError:
        pass  # Coluna já existe

    # NOVO: Adiciona a coluna 'is_admin' se não existir
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0')
        print("Coluna 'is_admin' adicionada à tabela 'users'.")
    except sqlite3.OperationalError:
        print("Coluna 'is_admin' já existe.")

    # (Criação das outras tabelas permanece a mesma)

    print("Tabelas verificadas/criadas.")
    conn.commit()


def populate_users():
    """Lê a aba 'Cadastro' e insere/atualiza usuários, incluindo o status de admin."""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='Cadastro')
        print(f"Encontrados {len(df)} registros na aba 'Cadastro'.")

        # Converte nomes de colunas para minúsculo para facilitar a busca
        df.columns = [col.lower() for col in df.columns]

        for index, row in df.iterrows():
            is_admin_flag = 1 if 'admin' in df.columns and str(row.get('admin', '')).lower() == 'sim' else 0

            cursor.execute("SELECT id FROM users WHERE email = ?", (row['email'],))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO users (email, password, municipio, responsavel, telefone, must_reset_password, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (row['email'], DEFAULT_PASSWORD, row['município'], row['responsável'], str(row['telefone']), 1,
                     is_admin_flag)
                )
                print(f"Usuário '{row['email']}' inserido (Admin: {'Sim' if is_admin_flag else 'Não'}).")
        conn.commit()
    except Exception as e:
        print(f"\nERRO ao ler a aba 'Cadastro': {e}")


# (A função populate_smartphones permanece a mesma)
# (A função populate_smartphones permanece a mesma e é omitida por brevidade)
def populate_smartphones():
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='smartphones')
        for index, row in df.iterrows():
            cursor.execute("SELECT id FROM smartphones WHERE imei = ?", (str(row['IMEI 1']),))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO smartphones (imei, marca, modelo, situacao, municipio) VALUES (?, ?, ?, ?, ?)",
                    (str(row['IMEI 1']), row['Marca'], row['Modelo'], row['Situação'], row['Município'])
                )
        conn.commit()
        print(f"\nSmartphones populados com sucesso.")
    except Exception as e:
        print(f"\nERRO ao ler a aba 'smartphones': {e}")


# --- Execução Principal ---
if __name__ == '__main__':
    setup_tables()
    if not os.path.exists(EXCEL_FILE):
        print(f"\nAVISO: '{EXCEL_FILE}' não encontrado.")
    else:
        populate_users()
        populate_smartphones()
    conn.close()
    print("\nProcesso de inicialização do banco de dados concluído.")
