# admin.py - Ferramenta separada para gerenciar usuários

import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash

# --- Configuração ---
app = Flask(__name__)
app.secret_key = 'admin-chave-secreta'
DATABASE = os.path.join(app.instance_path, 'chamados.db')
DEFAULT_PASSWORD = '12345'


# --- Funções de Banco de Dados ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# --- Rotas da Ferramenta de Admin ---

@app.route('/')
def admin_index():
    """Mostra a lista de todos os usuários."""
    db = get_db()
    # Seleciona também o telefone para exibir na tabela
    users = db.execute('SELECT id, email, municipio, responsavel, telefone FROM users ORDER BY responsavel').fetchall()
    db.close()
    return render_template('admin.html', users=users)


@app.route('/add_user', methods=['POST'])
def add_user():
    """Adiciona um novo usuário ao banco de dados."""
    email = request.form['email']
    municipio = request.form['municipio']
    responsavel = request.form['responsavel']
    telefone = request.form['telefone']

    if not all([email, municipio, responsavel, telefone]):
        flash('Todos os campos são obrigatórios.', 'danger')
        return redirect(url_for('admin_index'))

    db = get_db()
    try:
        # Adiciona o usuário com a senha padrão e a flag para redefinir
        db.execute(
            'INSERT INTO users (email, password, municipio, responsavel, telefone, must_reset_password) VALUES (?, ?, ?, ?, ?, ?)',
            (email, DEFAULT_PASSWORD, municipio, responsavel, telefone, 1)  # 1 significa True
        )
        db.commit()
        flash(f'Usuário {email} adicionado com sucesso!', 'success')
    except sqlite3.IntegrityError:
        flash(f'O e-mail {email} já está cadastrado.', 'danger')
    finally:
        db.close()

    return redirect(url_for('admin_index'))


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """Deleta um usuário do banco de dados."""
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    db.close()
    flash('Usuário removido com sucesso.', 'success')
    return redirect(url_for('admin_index'))


# --- NOVA ROTA PARA REDEFINIR SENHA ---
@app.route('/reset_password/<int:user_id>', methods=['POST'])
def reset_password(user_id):
    """Redefine a senha de um usuário para o padrão e força a alteração."""
    db = get_db()
    # Atualiza a senha para o valor padrão e ativa a flag 'must_reset_password'
    db.execute(
        'UPDATE users SET password = ?, must_reset_password = 1 WHERE id = ?',
        (DEFAULT_PASSWORD, user_id)
    )
    db.commit()
    db.close()
    flash('Senha do usuário redefinida para o padrão com sucesso!', 'success')
    return redirect(url_for('admin_index'))


# --- Ponto de Entrada ---
if __name__ == '__main__':
    # Executa em uma porta diferente para não conflitar com o app principal
    app.run(debug=True, port=5001)
