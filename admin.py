# admin.py - Ferramenta de administração com login e permissões

import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuração ---
app = Flask(__name__)
app.secret_key = 'admin-chave-secreta-muito-segura'
DATABASE = os.path.join(app.instance_path, 'chamados.db')
DEFAULT_PASSWORD = '12345'


# --- Funções de Banco de Dados ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# --- Middleware de Verificação de Admin ---
@app.before_request
def require_admin_login():
    """Verifica se um admin está logado antes de acessar qualquer página, exceto a de login."""
    allowed_routes = ['admin_login', 'static']
    if request.endpoint not in allowed_routes and 'admin_id' not in session:
        return redirect(url_for('admin_login'))


# --- Rotas da Ferramenta de Admin ---

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    """Página de login para administradores."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        # Verifica se o usuário existe E se ele tem a flag is_admin
        user = db.execute('SELECT * FROM users WHERE email = ? AND is_admin = 1', (email,)).fetchone()
        db.close()

        is_password_correct = False
        if user:
            # Permite login com a senha padrão ou com a senha já redefinida
            if user['password'] == DEFAULT_PASSWORD and password == DEFAULT_PASSWORD:
                is_password_correct = True
            elif user['password'] != DEFAULT_PASSWORD:
                is_password_correct = check_password_hash(user['password'], password)

        if is_password_correct:
            session['admin_id'] = user['id']
            session['admin_email'] = user['email']
            return redirect(url_for('admin_index'))
        else:
            flash('Credenciais de administrador inválidas ou usuário não é admin.', 'danger')

    return render_template('admin_login.html')


@app.route('/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/')
def admin_index():
    """Página principal do painel de admin, mostra a lista de usuários."""
    db = get_db()
    users = db.execute('SELECT id, email, municipio, responsavel, telefone FROM users ORDER BY responsavel').fetchall()
    db.close()
    return render_template('admin.html', users=users)


# (A rota add_user permanece a mesma)
@app.route('/add_user', methods=['POST'])
def add_user():
    # ... (código inalterado) ...
    return redirect(url_for('admin_index'))


# (A rota delete_user permanece a mesma)
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    # ... (código inalterado) ...
    return redirect(url_for('admin_index'))


@app.route('/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    """Redefine a senha de um usuário para o padrão e força a alteração."""
    db = get_db()
    db.execute(
        'UPDATE users SET password = ?, must_reset_password = 1 WHERE id = ?',
        (DEFAULT_PASSWORD, user_id)
    )
    db.commit()
    db.close()
    flash('Senha do usuário redefinida para o padrão com sucesso!', 'success')
    return redirect(url_for('admin_index'))


if __name__ == '__main__':
    app.run(debug=True, port=5001)
