# app.py - Versão com lógica de redefinição de senha corrigida

import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-super-aleatoria'
DATABASE = os.path.join(app.instance_path, 'chamados.db')
DEFAULT_PASSWORD = '12345'  # Senha padrão para verificação

os.makedirs(app.instance_path, exist_ok=True)


# --- Funções de Banco de Dados ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# --- Rotas da Aplicação Principal ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    # CORREÇÃO: Verificação explícita se o valor é 1 (True)
    if user and user['must_reset_password'] == 1:
        flash('Por favor, redefina sua senha para continuar.', 'warning')
        return redirect(url_for('redefinir_senha'))

    smartphones = db.execute(
        'SELECT * FROM smartphones WHERE municipio = ? AND situacao NOT IN (?, ?, ?)',
        (user['municipio'], 'Perdido', 'Roubado', 'Danificado')
    ).fetchall()
    recentes_chamados = db.execute(
        'SELECT * FROM chamados WHERE solicitante_email = ? ORDER BY timestamp DESC LIMIT 5',
        (user['email'],)
    ).fetchall()
    db.close()

    return render_template('chamado.html', user=user, smartphones=smartphones, chamados=recentes_chamados)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()

        if user:
            is_password_correct = False
            # Se a senha for a padrão, compara como texto simples
            if user['password'] == DEFAULT_PASSWORD and password == DEFAULT_PASSWORD:
                is_password_correct = True
            # Se não for a padrão, significa que já foi criptografada
            elif user['password'] != DEFAULT_PASSWORD:
                is_password_correct = check_password_hash(user['password'], password)

            if is_password_correct:
                session['user_id'] = user['id']

                # CORREÇÃO: Verificação explícita se o valor é 1 (True)
                if user['must_reset_password'] == 1:
                    flash('Este é seu primeiro acesso. Por favor, crie uma nova senha.', 'info')
                    return redirect(url_for('redefinir_senha'))

                return redirect(url_for('index'))

        flash('E-mail ou senha inválidos.', 'danger')
    return render_template('login.html')


# --- ROTA PARA REDEFINIR SENHA ---
@app.route('/redefinir_senha', methods=['GET', 'POST'])
def redefinir_senha():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not new_password or len(new_password) < 8:
            flash('A nova senha deve ter no mínimo 8 caracteres.', 'danger')
            return redirect(url_for('redefinir_senha'))

        if new_password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return redirect(url_for('redefinir_senha'))

        hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')

        db = get_db()
        db.execute(
            'UPDATE users SET password = ?, must_reset_password = 0 WHERE id = ?',
            (hashed_password, session['user_id'])
        )
        db.commit()
        db.close()

        flash('Senha redefinida com sucesso! Você já pode usar o sistema.', 'success')
        return redirect(url_for('index'))

    return render_template('redefinir_senha.html')


# (As outras rotas como logout, submit_chamado, meus_chamados permanecem as mesmas)
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))


@app.route('/submit_chamado', methods=['POST'])
def submit_chamado():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    imei = request.form.get('selectedDevice')
    tipo_problema = request.form.get('tipoProblema')
    observacoes = request.form.get('observacoes')
    if not all([imei, tipo_problema, observacoes]):
        flash('Todos os campos do chamado são obrigatórios.', 'danger')
        return redirect(url_for('index'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    db.execute(
        'INSERT INTO chamados (solicitante_email, municipio, smartphone_imei, tipo_problema, observacoes) VALUES (?, ?, ?, ?, ?)',
        (user['email'], user['municipio'], imei, tipo_problema, observacoes))
    db.commit()
    db.close()
    flash('Chamado registrado com sucesso!', 'success')
    return redirect(url_for('index'))


@app.route('/meus_chamados')
def meus_chamados():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    todos_chamados = db.execute('SELECT * FROM chamados WHERE solicitante_email = ? ORDER BY timestamp DESC',
                                (user['email'],)).fetchall()
    db.close()
    return render_template('meus_chamados.html', user=user, chamados=todos_chamados)


if __name__ == '__main__':
    app.run(debug=True)
