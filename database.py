# database.py - Adiciona uma flag para controlar a redefinição de senha

import sqlite3
import os
import pandas as pd

# A werkzeug não é mais necessária aqui, pois a senha padrão é texto simples
# Ela será usada apenas no app.py para criptografar a nova senha do usuário

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
    """Cria as tabelas e adiciona a nova coluna 'must_reset_password' se não existir."""
    # Cria a tabela users se não existir
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

    # Bloco para adicionar a nova coluna de forma segura, sem dar erro se ela já existir
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN DEFAULT 1')
        print("Coluna 'must_reset_password' adicionada à tabela 'users'.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Coluna 'must_reset_password' já existe.")
        else:
            raise e

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
    print("Tabelas verificadas/criadas.")
    conn.commit()


# --- Funções para popular as tabelas ---
def populate_users():
    """Lê a aba 'Cadastro' e insere novos usuários com a senha padrão."""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='Cadastro')
        print(f"Encontrados {len(df)} registros na aba 'Cadastro'.")

        for index, row in df.iterrows():
            cursor.execute("SELECT id FROM users WHERE email = ?", (row['Email'],))
            if cursor.fetchone() is None:
                # Insere o novo usuário com a senha padrão e a flag para redefinir
                cursor.execute(
                    "INSERT INTO users (email, password, municipio, responsavel, telefone, must_reset_password) VALUES (?, ?, ?, ?, ?, ?)",
                    (row['Email'], DEFAULT_PASSWORD, row['Município'], row['Responsável'], str(row['Telefone']), 1)
                    # 1 significa True
                )
                print(f"Usuário '{row['Email']}' inserido.")
        conn.commit()
    except Exception as e:
        print(f"\nERRO ao ler a aba 'Cadastro': {e}")


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
        print(f"\nAVISO: '{EXCEL_FILE}' não encontrado. Banco de dados não foi populado.")
    else:
        populate_users()
        populate_smartphones()
    conn.close()
    print("\nProcesso de inicialização do banco de dados concluído.")
