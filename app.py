# app.py - Versão com painel de admin integrado e acesso simplificado

import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-super-aleatoria'
DATABASE = os.path.join(app.instance_path, 'chamados.db')
DEFAULT_PASSWORD = '12345'

os.makedirs(app.instance_path, exist_ok=True)


# --- Funções de Banco de Dados ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# --- DECORADOR DE SEGURANÇA APRIMORADO ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))

        db = get_db()
        user = db.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        db.close()

        if user is None or not user['is_admin']:
            flash('Acesso negado. Esta área é restrita para administradores.', 'danger')
            return redirect(url_for('index'))

        return f(*args, **kwargs)

    return decorated_function


# --- Rotas da Aplicação Principal (Usuários) ---

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user and user['must_reset_password'] == 1:
        flash('Por favor, redefina sua senha para continuar.', 'warning')
        return redirect(url_for('redefinir_senha'))

    smartphones = db.execute('SELECT * FROM smartphones WHERE municipio = ? AND situacao NOT IN (?, ?, ?)',
                             (user['municipio'], 'Perdido', 'Roubado', 'Danificado')).fetchall()
    recentes_chamados = db.execute('SELECT * FROM chamados WHERE solicitante_email = ? ORDER BY timestamp DESC LIMIT 5',
                                   (user['email'],)).fetchall()
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
            is_password_correct = (user['password'] == DEFAULT_PASSWORD and password == DEFAULT_PASSWORD) or \
                                  (user['password'] != DEFAULT_PASSWORD and check_password_hash(user['password'],
                                                                                                password))
            if is_password_correct:
                session['user_id'] = user['id']
                if user['must_reset_password'] == 1:
                    flash('Este é seu primeiro acesso. Por favor, crie uma nova senha.', 'info')
                    return redirect(url_for('redefinir_senha'))
                return redirect(url_for('index'))
        flash('E-mail ou senha inválidos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))


@app.route('/redefinir_senha', methods=['GET', 'POST'])
def redefinir_senha():
    if 'user_id' not in session: return redirect(url_for('login'))
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
        db.execute('UPDATE users SET password = ?, must_reset_password = 0 WHERE id = ?',
                   (hashed_password, session['user_id']))
        db.commit()
        db.close()
        flash('Senha redefinida com sucesso!', 'success')
        return redirect(url_for('index'))
    return render_template('redefinir_senha.html')


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


# --- ROTAS DO PAINEL DE ADMINISTRAÇÃO ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ? AND is_admin = 1', (email,)).fetchone()
        db.close()
        is_password_correct = False
        if user:
            is_password_correct = (user['password'] == DEFAULT_PASSWORD and password == DEFAULT_PASSWORD) or \
                                  (user['password'] != DEFAULT_PASSWORD and check_password_hash(user['password'],
                                                                                                password))
        if is_password_correct:
            session['admin_id'] = user['id']
            session['admin_email'] = user['email']
            return redirect(url_for('admin_index'))
        else:
            flash('Credenciais de administrador inválidas ou usuário não é admin.', 'danger')
    return render_template('admin_login.html')


@app.route('/admin/')
@admin_required
def admin_index():
    db = get_db()
    users = db.execute('SELECT id, email, municipio, responsavel, telefone FROM users ORDER BY responsavel').fetchall()
    db.close()
    return render_template('admin.html', users=users)


@app.route('/admin/add_user', methods=['POST'])
@admin_required
def add_user():
    email = request.form['email']
    municipio = request.form['municipio']
    responsavel = request.form['responsavel']
    telefone = request.form['telefone']
    if not all([email, municipio, responsavel, telefone]):
        flash('Todos os campos são obrigatórios.', 'danger')
        return redirect(url_for('admin_index'))
    db = get_db()
    try:
        db.execute(
            'INSERT INTO users (email, password, municipio, responsavel, telefone, must_reset_password) VALUES (?, ?, ?, ?, ?, ?)',
            (email, DEFAULT_PASSWORD, municipio, responsavel, telefone, 1))
        db.commit()
        flash(f'Usuário {email} adicionado com sucesso!', 'success')
    except sqlite3.IntegrityError:
        flash(f'O e-mail {email} já está cadastrado.', 'danger')
    finally:
        db.close()
    return redirect(url_for('admin_index'))


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    db.close()
    flash('Usuário removido com sucesso.', 'success')
    return redirect(url_for('admin_index'))


@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    db = get_db()
    db.execute('UPDATE users SET password = ?, must_reset_password = 1 WHERE id = ?', (DEFAULT_PASSWORD, user_id))
    db.commit()
    db.close()
    flash('Senha do usuário redefinida para o padrão com sucesso!', 'success')
    return redirect(url_for('admin_index'))


if __name__ == '__main__':
    app.run(debug=True)
