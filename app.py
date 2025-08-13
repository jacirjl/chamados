# app.py - Arquivo principal da aplicação Flask (versão com senha em texto simples)

import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash

# A biblioteca werkzeug.security foi removida

# --- Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-super-aleatoria'
DATABASE = os.path.join(app.instance_path, 'chamados.db')
os.makedirs(app.instance_path, exist_ok=True)


# --- Funções de Banco de Dados ---
def get_db():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# --- Rotas da Aplicação (URLs) ---

@app.route('/')
def index():
    """Página principal. Redireciona para o login se o usuário não estiver logado."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    smartphones = db.execute(
        'SELECT * FROM smartphones WHERE municipio = ? AND situacao NOT IN (?, ?, ?)',
        (user['municipio'], 'Perdido', 'Roubado', 'Danificado')
    ).fetchall()
    db.close()

    return render_template('chamado.html', user=user, smartphones=smartphones)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login. Valida as credenciais do usuário."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()

        # --- ALTERAÇÃO PRINCIPAL ---
        # A verificação agora é uma comparação de texto simples.
        if user and user['password'] == password:
            session['user_id'] = user['id']
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('E-mail ou senha inválidos. Tente novamente.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Remove o usuário da sessão (faz logout)."""
    session.pop('user_id', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))


@app.route('/submit_chamado', methods=['POST'])
def submit_chamado():
    """Recebe os dados do formulário e registra um novo chamado no banco de dados."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    imei = request.form.get('selectedDevice')
    tipo_problema = request.form.get('tipoProblema')
    observacoes = request.form.get('observacoes')

    if not imei or not tipo_problema or not observacoes:
        flash('Todos os campos do chamado são obrigatórios.', 'danger')
        return redirect(url_for('index'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    db.execute(
        'INSERT INTO chamados (solicitante_email, municipio, smartphone_imei, tipo_problema, observacoes) VALUES (?, ?, ?, ?, ?)',
        (user['email'], user['municipio'], imei, tipo_problema, observacoes)
    )
    db.commit()
    db.close()

    flash('Chamado registrado com sucesso!', 'success')
    return redirect(url_for('index'))


# --- Ponto de Entrada da Aplicação ---
if __name__ == '__main__':
    app.run(debug=True)
