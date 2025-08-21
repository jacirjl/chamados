# app.py

import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-super-aleatoria'
app.instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')

DATABASE = os.path.join(app.instance_path, 'chamados.db')
UPLOAD_FOLDER = os.path.join(app.instance_path, 'uploads')
DEFAULT_PASSWORD = '12345'

os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --- Funções de Banco de Dados ---
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# --- Decoradores de Segurança ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user or not g.user['is_admin']:
            flash('Acesso negado. Esta área é restrita para administradores.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


# --- Processador de Contexto ---
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        db.close()


@app.context_processor
def inject_user():
    return dict(user=g.user)


# --- Rotas da Aplicação Principal ---
@app.route('/')
@login_required
def index():
    if g.user['must_reset_password']:
        return redirect(url_for('redefinir_senha'))
    if g.user['is_admin']:
        return redirect(url_for('dashboard'))

    db = get_db()
    equipamentos = db.execute('SELECT * FROM equipamentos WHERE municipio = ? AND situacao NOT IN (?, ?, ?)',
                              (g.user['municipio'], 'Perdido', 'Roubado', 'Danificado')).fetchall()
    tipos_problema = db.execute('SELECT * FROM tipos_problema ORDER BY nome').fetchall()
    db.close()

    return render_template('chamado.html', equipamentos=equipamentos, tipos_problema=tipos_problema)


@app.route('/abrir_chamado_admin')
@login_required
@admin_required
def abrir_chamado_admin():
    db = get_db()
    municipio_selecionado = request.args.get('municipio', None)
    todos_municipios = [row['municipio'] for row in
                        db.execute('SELECT DISTINCT municipio FROM equipamentos ORDER BY municipio').fetchall()]
    tipos_problema = db.execute('SELECT * FROM tipos_problema ORDER BY nome').fetchall()

    equipamentos = []
    if municipio_selecionado:
        equipamentos = db.execute('SELECT * FROM equipamentos WHERE municipio = ? AND situacao NOT IN (?, ?, ?)',
                                  (municipio_selecionado, 'Perdido', 'Roubado', 'Danificado')).fetchall()

    db.close()
    return render_template('chamado.html', equipamentos=equipamentos, tipos_problema=tipos_problema,
                           todos_municipios=todos_municipios, municipio_selecionado=municipio_selecionado)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()

        is_password_correct = False
        if user:
            is_password_correct = (user['password'] == DEFAULT_PASSWORD and password == DEFAULT_PASSWORD) or \
                                  (check_password_hash(user['password'], password))

        if is_password_correct:
            session.clear()
            session['user_id'] = user['id']

            if user['must_reset_password'] == 1:
                flash('Este é seu primeiro acesso ou sua senha foi redefinida. Por favor, crie uma nova senha.', 'info')
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
@login_required
def redefinir_senha():
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if not new_password or len(new_password) < 4:
            flash('A nova senha deve ter no mínimo 4 caracteres.', 'danger')
        elif new_password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
        else:
            hashed_password = generate_password_hash(new_password)
            db = get_db()
            db.execute('UPDATE users SET password = ?, must_reset_password = 0 WHERE id = ?',
                       (hashed_password, session['user_id']))
            db.commit()
            db.close()
            flash('Senha redefinida com sucesso!', 'success')
            return redirect(url_for('index'))
    return render_template('redefinir_senha.html')


@app.route('/submit_chamado', methods=['POST'])
@login_required
def submit_chamado():
    imei = request.form.get('selectedDevice')
    tipo_problema_id = request.form.get('tipoProblema')
    observacoes = request.form.get('observacoes')

    municipio_chamado = request.form.get('municipio_selecionado') if g.user['is_admin'] else g.user['municipio']

    if not all([imei, tipo_problema_id, observacoes, municipio_chamado]):
        flash('Todos os campos do chamado são obrigatórios.', 'danger')
        return redirect(url_for('abrir_chamado_admin') if g.user['is_admin'] else url_for('index'))

    foto_filename = None
    if 'foto' in request.files:
        foto_file = request.files['foto']
        if foto_file.filename != '':
            _, extensao = os.path.splitext(foto_file.filename)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            foto_filename = f"{timestamp}{extensao}"
            foto_file.save(os.path.join(UPLOAD_FOLDER, foto_filename))

    db = get_db()
    status_aberto_row = db.execute('SELECT id FROM status WHERE nome = ?', ('Aberto',)).fetchone()
    status_aberto_id = status_aberto_row[0] if status_aberto_row else 1

    db.execute(
        'INSERT INTO chamados (solicitante_email, municipio, smartphone_imei, tipo_problema_id, observacoes, status_id, foto) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (g.user['email'], municipio_chamado, imei, tipo_problema_id, observacoes, status_aberto_id, foto_filename))
    db.commit()
    db.close()

    flash('Chamado registrado com sucesso!', 'success')
    return redirect(url_for('meus_chamados'))


@app.route('/meus_chamados')
@login_required
def meus_chamados():
    db = get_db()
    status_options = db.execute('SELECT * FROM status ORDER BY id').fetchall()

    # Pega o filtro da URL, se existir (ex: /meus_chamados?status=2)
    status_filter_id = request.args.get('status', None, type=int)

    query = """
        SELECT c.id, c.timestamp, c.municipio, c.smartphone_imei, c.observacoes, c.foto, c.solucao, c.status_id,
               s.nome as status_nome,
               tp.nome as tipo_problema_nome
        FROM chamados c
        JOIN status s ON c.status_id = s.id
        JOIN tipos_problema tp ON c.tipo_problema_id = tp.id
    """

    params = []
    conditions = []

    # Adiciona filtro por usuário (se não for admin)
    if not g.user['is_admin']:
        conditions.append("c.solicitante_email = ?")
        params.append(g.user['email'])

    # Adiciona filtro por status (se selecionado na URL)
    if status_filter_id:
        conditions.append("c.status_id = ?")
        params.append(status_filter_id)

    # Constrói a cláusula WHERE se houver condições
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY c.timestamp DESC"

    todos_chamados = db.execute(query, tuple(params)).fetchall()
    db.close()

    # Passa o filtro de volta para o template para que ele possa manter o dropdown selecionado
    return render_template('meus_chamados.html', chamados=todos_chamados, status_options=status_options,
                           status_filter_id=status_filter_id)


@app.route('/uploads/<path:filename>')
@login_required
def display_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/chamado/update/<int:chamado_id>', methods=['POST'])
@login_required
def update_chamado(chamado_id):
    novo_status_id = request.form.get('status')
    nova_solucao = request.form.get('solucao')
    db = get_db()
    db.execute('UPDATE chamados SET status_id = ?, solucao = ? WHERE id = ?',
               (novo_status_id, nova_solucao, chamado_id))
    db.commit()
    db.close()
    flash(f'Chamado #{chamado_id} atualizado com sucesso!', 'success')
    return redirect(url_for('meus_chamados'))


# --- ROTAS DO PAINEL DE ADMINISTRAÇÃO ---
@app.route('/dashboard')
@login_required
@admin_required
def dashboard():
    db = get_db()
    kpis = {}
    status_list = db.execute('SELECT nome FROM status ORDER BY id').fetchall()
    for status in status_list:
        status_nome = status['nome']
        count = db.execute('SELECT COUNT(c.id) FROM chamados c JOIN status s ON c.status_id = s.id WHERE s.nome = ?',
                           (status_nome,)).fetchone()[0]
        kpis[status_nome] = count
    kpis['Total'] = db.execute('SELECT COUNT(id) FROM chamados').fetchone()[0]
    kpis['Usuários'] = db.execute('SELECT COUNT(id) FROM users').fetchone()[0]
    status_data = db.execute(
        'SELECT s.nome, COUNT(c.id) as count FROM chamados c JOIN status s ON c.status_id = s.id GROUP BY s.nome').fetchall()
    status_labels = [row['nome'] for row in status_data]
    status_values = [row['count'] for row in status_data]
    tipo_data = db.execute(
        'SELECT tp.nome, COUNT(c.id) as count FROM chamados c JOIN tipos_problema tp ON c.tipo_problema_id = tp.id GROUP BY tp.nome ORDER BY count DESC').fetchall()
    tipo_labels = [row['nome'] for row in tipo_data]
    tipo_values = [row['count'] for row in tipo_data]
    ultimos_chamados = db.execute("""
        SELECT c.id, c.timestamp, c.solicitante_email, c.municipio, s.nome as status_nome, tp.nome as tipo_problema_nome
        FROM chamados c
        JOIN status s ON c.status_id = s.id
        JOIN tipos_problema tp ON c.tipo_problema_id = tp.id
        ORDER BY c.timestamp DESC LIMIT 5
    """).fetchall()
    db.close()
    return render_template(
        'dashboard.html', kpis=kpis,
        status_labels=status_labels, status_values=status_values,
        tipo_labels=tipo_labels, tipo_values=tipo_values,
        ultimos_chamados=ultimos_chamados
    )


@app.route('/admin/')
@login_required
@admin_required
def admin_index():
    search_query = request.args.get('search', '')
    db = get_db()
    if search_query:
        search_term = f"%{search_query}%"
        users = db.execute(
            'SELECT * FROM users WHERE responsavel LIKE ? OR email LIKE ? OR municipio LIKE ? ORDER BY responsavel',
            (search_term, search_term, search_term)).fetchall()
    else:
        users = db.execute('SELECT * FROM users ORDER BY responsavel').fetchall()
    db.close()
    return render_template('admin.html', users=users, search_query=search_query)


@app.route('/admin/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    email = request.form['email']
    municipio = request.form['municipio']
    responsavel = request.form['responsavel']
    telefone = request.form['telefone']
    is_admin_val = 1 if request.form.get('is_admin') else 0
    must_reset_val = 1 if request.form.get('must_reset_password') else 0
    if not all([email, municipio, responsavel, telefone]):
        flash('Os campos de texto são obrigatórios.', 'danger')
    else:
        db = get_db()
        try:
            db.execute(
                'INSERT INTO users (email, password, municipio, responsavel, telefone, must_reset_password, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (email, DEFAULT_PASSWORD, municipio, responsavel, telefone, must_reset_val, is_admin_val))
            db.commit()
            flash(f'Usuário {email} adicionado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash(f'O e-mail {email} já está cadastrado.', 'danger')
        finally:
            db.close()
    return redirect(url_for('admin_index'))


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    db.close()
    flash('Usuário removido com sucesso!', 'success')
    return redirect(url_for('admin_index'))


@app.route('/admin/reset_password/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    db = get_db()
    db.execute('UPDATE users SET password = ?, must_reset_password = 1 WHERE id = ?', (DEFAULT_PASSWORD, user_id))
    db.commit()
    db.close()
    flash('Senha do usuário redefinida para o padrão com sucesso!', 'success')
    return redirect(url_for('admin_index'))


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    db = get_db()
    if request.method == 'POST':
        email = request.form['email']
        municipio = request.form['municipio']
        responsavel = request.form['responsavel']
        telefone = request.form['telefone']
        is_admin_val = 1 if request.form.get('is_admin') else 0
        must_reset_val = 1 if request.form.get('must_reset_password') else 0
        try:
            db.execute(
                'UPDATE users SET email = ?, municipio = ?, responsavel = ?, telefone = ?, is_admin = ?, must_reset_password = ? WHERE id = ?',
                (email, municipio, responsavel, telefone, is_admin_val, must_reset_val, user_id))
            db.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('admin_index'))
        except sqlite3.IntegrityError:
            flash(f'O e-mail {email} já está em uso por outro usuário.', 'danger')
    user_to_edit = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    db.close()
    if user_to_edit is None:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('admin_index'))
    return render_template('edit_user.html', user=user_to_edit)


@app.route('/admin/gerenciar')
@login_required
@admin_required
def gerenciar_cadastros():
    db = get_db()
    status_list = db.execute('SELECT * FROM status ORDER BY nome').fetchall()
    tipos_problema_list = db.execute('SELECT * FROM tipos_problema ORDER BY nome').fetchall()
    db.close()
    return render_template('gerenciar_cadastros.html', status_list=status_list, tipos_problema_list=tipos_problema_list)


@app.route('/admin/status/add', methods=['POST'])
@login_required
@admin_required
def add_status():
    nome = request.form.get('nome')
    if nome:
        db = get_db()
        try:
            db.execute('INSERT INTO status (nome) VALUES (?)', (nome,))
            db.commit()
            flash('Novo status adicionado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Este status já existe.', 'danger')
        finally:
            db.close()
    else:
        flash('O nome do status não pode ser vazio.', 'danger')
    return redirect(url_for('gerenciar_cadastros'))


@app.route('/admin/status/delete/<int:status_id>', methods=['POST'])
@login_required
@admin_required
def delete_status(status_id):
    db = get_db()
    chamado_usando = db.execute('SELECT id FROM chamados WHERE status_id = ?', (status_id,)).fetchone()
    if chamado_usando:
        flash('Não é possível remover este status, pois ele está em uso por um ou mais chamados.', 'danger')
    else:
        db.execute('DELETE FROM status WHERE id = ?', (status_id,))
        db.commit()
        flash('Status removido com sucesso!', 'success')
    db.close()
    return redirect(url_for('gerenciar_cadastros'))


@app.route('/admin/tipos_problema/add', methods=['POST'])
@login_required
@admin_required
def add_tipo_problema():
    nome = request.form.get('nome')
    if nome:
        db = get_db()
        try:
            db.execute('INSERT INTO tipos_problema (nome) VALUES (?)', (nome,))
            db.commit()
            flash('Novo tipo de problema adicionado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash('Este tipo de problema já existe.', 'danger')
        finally:
            db.close()
    else:
        flash('O nome do tipo de problema não pode ser vazio.', 'danger')
    return redirect(url_for('gerenciar_cadastros'))


@app.route('/admin/tipos_problema/delete/<int:tipo_id>', methods=['POST'])
@login_required
@admin_required
def delete_tipo_problema(tipo_id):
    db = get_db()
    chamado_usando = db.execute('SELECT id FROM chamados WHERE tipo_problema_id = ?', (tipo_id,)).fetchone()
    if chamado_usando:
        flash('Não é possível remover este tipo, pois ele está em uso por um ou mais chamados.', 'danger')
    else:
        db.execute('DELETE FROM tipos_problema WHERE id = ?', (tipo_id,))
        db.commit()
        flash('Tipo de problema removido com sucesso!', 'success')
    db.close()
    return redirect(url_for('gerenciar_cadastros'))


if __name__ == '__main__':
    app.run(debug=True)