# database.py - Script para criar e popular o banco de dados com senha em texto simples

import sqlite3
import os
import pandas as pd

# A biblioteca werkzeug.security foi removida

# --- Configurações ---
INSTANCE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
DATABASE = os.path.join(INSTANCE_FOLDER, 'chamados.db')
EXCEL_FILE = 'suporte.xlsx'
DEFAULT_PASSWORD = '12345'  # AVISO: Senha em texto simples

# Garante que a pasta 'instance' exista
os.makedirs(INSTANCE_FOLDER, exist_ok=True)

# Conecta ao banco de dados
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

print("Conectado ao banco de dados.")


# --- Funções para criar as tabelas ---
def create_tables():
    """Cria as tabelas no banco de dados se elas não existirem."""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, -- Senha será armazenada como texto
        municipio TEXT NOT NULL,
        responsavel TEXT NOT NULL,
        telefone TEXT NOT NULL
    );
    ''')
    print("Tabela 'users' verificada/criada.")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS smartphones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT UNIQUE NOT NULL,
        marca TEXT NOT NULL,
        modelo TEXT NOT NULL,
        situacao TEXT NOT NULL,
        municipio TEXT NOT NULL
    );
    ''')
    print("Tabela 'smartphones' verificada/criada.")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chamados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        solicitante_email TEXT NOT NULL,
        municipio TEXT NOT NULL,
        smartphone_imei TEXT NOT NULL,
        tipo_problema TEXT NOT NULL,
        observacoes TEXT NOT NULL
    );
    ''')
    print("Tabela 'chamados' verificada/criada.")


# --- Funções para popular as tabelas a partir do Excel ---
def populate_users():
    """Lê a aba 'Cadastro' do Excel e insere os usuários no banco de dados."""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='Cadastro')
        print(f"Encontrados {len(df)} registros na aba 'Cadastro'.")

        for index, row in df.iterrows():
            cursor.execute("SELECT id FROM users WHERE email = ?", (row['Email'],))
            if cursor.fetchone() is None:
                # --- ALTERAÇÃO PRINCIPAL ---
                # A senha padrão é inserida diretamente, sem criptografia.
                cursor.execute(
                    "INSERT INTO users (email, password, municipio, responsavel, telefone) VALUES (?, ?, ?, ?, ?)",
                    (row['Email'], DEFAULT_PASSWORD, row['Município'], row['Responsável'], str(row['Telefone']))
                )
                print(f"Usuário '{row['Email']}' inserido com senha padrão.")
            else:
                print(f"Usuário '{row['Email']}' já existe. Pulando.")

        conn.commit()
    except Exception as e:
        print(f"\nERRO: Não foi possível ler a aba 'Cadastro'. Verifique o nome da aba e os cabeçalhos.")
        print(f"Detalhe do erro: {e}")


def populate_smartphones():
    """Lê a aba 'smartphones' do Excel e insere os dispositivos no banco de dados."""
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='smartphones')
        print(f"\nEncontrados {len(df)} registros na aba 'smartphones'.")

        for index, row in df.iterrows():
            cursor.execute("SELECT id FROM smartphones WHERE imei = ?", (str(row['IMEI 1']),))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO smartphones (imei, marca, modelo, situacao, municipio) VALUES (?, ?, ?, ?, ?)",
                    (str(row['IMEI 1']), row['Marca'], row['Modelo'], row['Situação'], row['Município'])
                )
                print(f"Smartphone com IMEI '{row['IMEI 1']}' inserido.")
            else:
                print(f"Smartphone com IMEI '{row['IMEI 1']}' já existe. Pulando.")

        conn.commit()
    except Exception as e:
        print(f"\nERRO: Não foi possível ler a aba 'smartphones'. Verifique o nome da aba e os cabeçalhos.")
        print(f"Detalhe do erro: {e}")


# --- Execução Principal ---
if __name__ == '__main__':
    create_tables()

    if not os.path.exists(EXCEL_FILE):
        print(f"\nAVISO: Arquivo '{EXCEL_FILE}' não encontrado. O banco de dados foi criado, mas não foi populado.")
    else:
        populate_users()
        populate_smartphones()

    conn.close()
    print("\nProcesso de inicialização do banco de dados concluído.")
