import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# --- Configuração da Aplicação ---
app = Flask(__name__)
app.secret_key = 'sua-chave-secreta-super-aleatoria'
app.instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

DATABASE = os.path.join(app.instance_path, 'chamados.db')
UPLOAD_FOLDER = os.path.join(app.instance_path, 'uploads')
DEFAULT_PASSWORD = '12345'

os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.errorhandler(RequestEntityTooLarge)
def handle_too_large_entity(e):
    flash('O arquivo enviado é muito grande. O tamanho máximo permitido é de 5MB.', 'danger')

    if g.user and g.user['is_admin']:
        municipio = request.form.get('municipio_selecionado', '')
        if municipio:
            return redirect(url_for('abrir_chamado_admin', municipio=municipio))
        return redirect(url_for('abrir_chamado_admin'))

    return redirect(url_for('index'))


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
    kpis = {}
    query_kpis = """
        SELECT s.nome, s.e_final, count(c.id) as count 
        FROM status s 
        LEFT JOIN chamados c ON s.id = c.status_id AND c.solicitante_email = ? 
        GROUP BY s.id
    """
    user_stats = db.execute(query_kpis, (g.user['email'],)).fetchall()

    kpis['abertos'] = sum(row['count'] for row in user_stats if not row['e_final'])
    kpis['finalizados'] = sum(row['count'] for row in user_stats if row['e_final'])

    db.close()
    return render_template('user_dashboard.html', kpis=kpis)


@app.route('/abrir_chamado')
@login_required
def abrir_chamado():
    if g.user['is_admin']:
        return redirect(url_for('abrir_chamado_admin'))

    db = get_db()
    equipamentos = db.execute(
        'SELECT * FROM equipamentos WHERE municipio = ?',
        (g.user['municipio'],)
    ).fetchall()
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
    responsavel_do_municipio = None

    if municipio_selecionado:
        equipamentos = db.execute(
            'SELECT * FROM equipamentos WHERE municipio = ?',
            (municipio_selecionado,)
        ).fetchall()
        responsavel_do_municipio = db.execute("SELECT * FROM users WHERE municipio = ? AND is_admin = 0 LIMIT 1",
                                              (municipio_selecionado,)).fetchone()

    db.close()
    return render_template('chamado.html',
                           equipamentos=equipamentos,
                           tipos_problema=tipos_problema,
                           todos_municipios=todos_municipios,
                           municipio_selecionado=municipio_selecionado,
                           responsavel_do_municipio=responsavel_do_municipio)


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

    db = get_db()
    solicitante_final_email = g.user['email']

    if g.user['is_admin']:
        responsavel_municipio = db.execute(
            "SELECT email FROM users WHERE municipio = ? AND is_admin = 0 LIMIT 1",
            (municipio_chamado,)
        ).fetchone()

        if responsavel_municipio:
            solicitante_final_email = responsavel_municipio['email']
        else:
            flash(
                f"Aviso: Nenhum usuário comum encontrado para o município '{municipio_chamado}'. O chamado foi aberto em nome do administrador.",
                "warning")
            solicitante_final_email = g.user['email']

    foto_filename = None
    if 'foto' in request.files:
        foto_file = request.files['foto']
        if foto_file.filename != '':
            _, extensao = os.path.splitext(foto_file.filename)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            foto_filename = secure_filename(f"{timestamp}{extensao}")
            foto_file.save(os.path.join(UPLOAD_FOLDER, foto_filename))

    status_inicial_row = db.execute('SELECT id FROM status WHERE e_inicial = 1 LIMIT 1').fetchone()
    if not status_inicial_row:
        flash('Erro crítico: Nenhum status inicial configurado no sistema.', 'danger')
        db.close()
        return redirect(url_for('index'))
    status_inicial_id = status_inicial_row['id']

    db.execute(
        'INSERT INTO chamados (solicitante_email, municipio, smartphone_imei, tipo_problema_id, observacoes, status_id, foto) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (solicitante_final_email, municipio_chamado, imei, tipo_problema_id, observacoes, status_inicial_id,
         foto_filename))

    db.commit()
    db.close()

    flash('Chamado registrado com sucesso!', 'success')
    return redirect(url_for('meus_chamados'))


@app.route('/meus_chamados')
@login_required
def meus_chamados():
    erro_chamado_id = request.args.get('erro_chamado_id', type=int)
    db = get_db()

    config_rows = db.execute("SELECT chave, valor FROM configuracoes").fetchall()
    configs = {row['chave']: row['valor'] for row in config_rows}
    prazo_reabrir = int(configs.get('prazo_reabrir', 3))
    status_expirado_id = configs.get('status_expirado_id')

    if status_expirado_id:
        db.execute("""
            UPDATE chamados 
            SET status_id = :id_expirado
            WHERE status_id IN (SELECT id FROM status WHERE permite_reabertura = 1) 
            AND resolvido_em IS NOT NULL
            AND date(resolvido_em, '+' || :prazo || ' days') <= date('now')
        """, {"id_expirado": status_expirado_id, "prazo": prazo_reabrir})
        db.commit()

    status_options = db.execute('SELECT * FROM status ORDER BY nome').fetchall()
    tipos_problema_options = db.execute('SELECT * FROM tipos_problema ORDER BY nome').fetchall()

    status_filter_id = request.args.get('status', default=None, type=int)
    municipio_filter = request.args.get('municipio', default=None, type=str)
    tipo_problema_filter_id = request.args.get('tipo_problema', default=None, type=int)
    status_group_filter = request.args.get('status_group', default=None, type=str)

    municipios_options = db.execute('SELECT DISTINCT municipio FROM chamados ORDER BY municipio').fetchall()

    base_query = """
        SELECT c.id, c.timestamp, c.municipio, c.solicitante_email, c.smartphone_imei, 
               c.observacoes, c.foto, c.solucao, c.status_id, c.tipo_problema_id, c.admin_responsavel_id,
               c.resolvido_em,
               s.nome as status_nome,
               s.e_inicial as status_e_inicial, 
               s.e_final as status_e_final,
               s.permite_reabertura as status_permite_reabertura,
               tp.nome as tipo_problema_nome,
               u.responsavel as admin_responsavel_nome,
               e.marca as equipamento_marca,
               e.modelo as equipamento_modelo,
               e.patrimonio as equipamento_patrimonio,
               e.numeroDeSerie as equipamento_ns,
               e.localdeUso as equipamento_local,
               e.situacao as equipamento_situacao
        FROM chamados c
        JOIN status s ON c.status_id = s.id
        JOIN tipos_problema tp ON c.tipo_problema_id = tp.id
        LEFT JOIN users u ON c.admin_responsavel_id = u.id
        LEFT JOIN equipamentos e ON c.smartphone_imei = e.imei1
    """

    prazo_vermelho = int(configs.get('prazo_vermelho', 10))
    prazo_amarelo = int(configs.get('prazo_amarelo', 5))

    def processar_chamados(chamados_raw):
        chamados_processados = []
        for chamado in chamados_raw:
            chamado_dict = dict(chamado)

            try:
                data_obj = datetime.strptime(chamado_dict['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S')
                chamado_dict['timestamp'] = data_obj.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                chamado_dict['timestamp'] = 'Data inválida'

            chamado_dict['cor_borda'] = 'success'
            if not chamado_dict['status_e_final']:
                try:
                    data_abertura = datetime.strptime(chamado_dict['timestamp'], '%d/%m/%Y')
                    dias_aberto = (datetime.now() - data_abertura).days
                    if dias_aberto > prazo_vermelho:
                        chamado_dict['cor_borda'] = 'danger'
                    elif dias_aberto > prazo_amarelo:
                        chamado_dict['cor_borda'] = 'warning'
                except (ValueError, TypeError):
                    chamado_dict['cor_borda'] = 'secondary'

            chamado_dict['reabertura_disponivel'] = False
            if chamado_dict['status_permite_reabertura'] and chamado_dict['resolvido_em']:
                try:
                    data_resolvido = datetime.strptime(chamado_dict['resolvido_em'], '%Y-%m-%d %H:%M:%S.%f')
                    data_expiracao = data_resolvido + timedelta(days=prazo_reabrir)
                    if datetime.now() < data_expiracao:
                        chamado_dict['reabertura_disponivel'] = True
                        chamado_dict['expira_em'] = data_expiracao.strftime('%d/%m/%Y às %H:%M')
                except (ValueError, TypeError):
                    pass

            chamados_processados.append(chamado_dict)
        return chamados_processados

    def get_query_conditions_and_params(base_params, base_conditions_str=""):
        params = list(base_params)
        conditions = base_conditions_str
        if status_filter_id:
            conditions += " AND c.status_id = ?"
            params.append(status_filter_id)
        if municipio_filter:
            conditions += " AND c.municipio = ?"
            params.append(municipio_filter)
        if tipo_problema_filter_id:
            conditions += " AND c.tipo_problema_id = ?"
            params.append(tipo_problema_filter_id)
        if status_group_filter == 'finalizados':
            conditions += " AND s.e_final = 1"
        return conditions, params

    if g.user['is_admin']:
        atribuidos_conditions, atribuidos_params = get_query_conditions_and_params(
            (g.user['id'],), " WHERE c.admin_responsavel_id = ?"
        )
        query_atribuidos = base_query + atribuidos_conditions + " ORDER BY c.timestamp DESC"
        chamados_atribuidos_raw = db.execute(query_atribuidos, atribuidos_params).fetchall()

        outros_conditions, outros_params = get_query_conditions_and_params(
            (g.user['id'],), " WHERE (c.admin_responsavel_id IS NULL OR c.admin_responsavel_id != ?)"
        )
        query_outros = base_query + outros_conditions + " ORDER BY c.timestamp DESC"
        outros_chamados_raw = db.execute(query_outros, outros_params).fetchall()

        db.close()
        return render_template('meus_chamados.html',
                               chamados_atribuidos=processar_chamados(chamados_atribuidos_raw),
                               outros_chamados=processar_chamados(outros_chamados_raw),
                               status_options=status_options,
                               tipos_problema_options=tipos_problema_options,
                               status_filter_id=status_filter_id,
                               municipios_options=municipios_options,
                               municipio_filter=municipio_filter,
                               erro_chamado_id=erro_chamado_id)
    else:
        user_conditions, user_params = get_query_conditions_and_params(
            (g.user['email'],), " WHERE c.solicitante_email = ?"
        )
        query = base_query + user_conditions + " ORDER BY c.timestamp DESC"
        todos_chamados_raw = db.execute(query, user_params).fetchall()

        db.close()
        return render_template('meus_chamados.html',
                               chamados=processar_chamados(todos_chamados_raw),
                               status_options=status_options,
                               tipos_problema_options=tipos_problema_options,
                               status_filter_id=status_filter_id,
                               municipios_options=municipios_options,
                               municipio_filter=municipio_filter,
                               erro_chamado_id=erro_chamado_id)


@app.route('/uploads/<path:filename>')
@login_required
def display_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/chamado/update/<int:chamado_id>', methods=['POST'])
@login_required
@admin_required
def update_chamado(chamado_id):
    db = get_db()

    if not g.user['is_admin']:
        flash('Você não tem permissão para alterar este chamado.', 'danger')
        db.close()
        return redirect(url_for('meus_chamados'))

    chamado_info = db.execute("SELECT solucao, status_id FROM chamados WHERE id = ?", (chamado_id,)).fetchone()
    if not chamado_info:
        flash('Chamado não encontrado.', 'danger')
        db.close()
        return redirect(url_for('meus_chamados'))

    novo_status_id = request.form.get('status')
    nova_adicao_solucao = request.form.get('nova_solucao', '').strip()
    original_status_id = chamado_info['status_id']

    if str(original_status_id) != novo_status_id and not nova_adicao_solucao:
        flash('Ao alterar o status de um chamado, é obrigatório adicionar uma nota no campo "Adicionar Nova Solução".',
              'danger')
        db.close()
        return redirect(url_for('meus_chamados', erro_chamado_id=chamado_id))

    solucao_final = chamado_info['solucao'] or ''
    if nova_adicao_solucao:
        timestamp_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        autor = g.user['responsavel']
        nova_entrada = f"[{timestamp_atual} - {autor}]:\n{nova_adicao_solucao}\n"
        separador = "-" * 50 + "\n"
        solucao_final = nova_entrada + separador + solucao_final

    novo_status_info = db.execute("SELECT e_inicial, permite_reabertura FROM status WHERE id = ?",
                                  (novo_status_id,)).fetchone()

    timestamp_resolvido = None
    if novo_status_info and novo_status_info['permite_reabertura']:
        timestamp_resolvido = datetime.now()

    if novo_status_info and novo_status_info['e_inicial']:
        db.execute(
            'UPDATE chamados SET status_id = ?, solucao = ?, resolvido_em = NULL, admin_responsavel_id = NULL WHERE id = ?',
            (novo_status_id, solucao_final, chamado_id)
        )
        flash(f'Chamado #{chamado_id} foi reaberto e devolvido para a fila de captura.', 'info')
    else:
        db.execute(
            'UPDATE chamados SET status_id = ?, solucao = ?, resolvido_em = ? WHERE id = ?',
            (novo_status_id, solucao_final, timestamp_resolvido, chamado_id)
        )
        flash(f'Chamado #{chamado_id} atualizado com sucesso!', 'success')

    db.commit()
    db.close()
    return redirect(url_for('meus_chamados'))


@app.route('/chamado/reabrir/<int:chamado_id>', methods=['POST'])
@login_required
def reabrir_chamado(chamado_id):
    db = get_db()
    chamado = db.execute(
        "SELECT c.*, s.permite_reabertura FROM chamados c JOIN status s ON c.status_id = s.id WHERE c.id = ?",
        (chamado_id,)).fetchone()

    if not chamado or chamado['solicitante_email'] != g.user['email']:
        flash("Você não tem permissão para reabrir este chamado.", "danger")
        db.close()
        return redirect(url_for('meus_chamados'))

    if not chamado['permite_reabertura']:
        flash("Este chamado não pode ser reaberto a partir do seu status atual.", "warning")
        db.close()
        return redirect(url_for('meus_chamados'))

    configs = {row['chave']: row['valor'] for row in db.execute("SELECT chave, valor FROM configuracoes").fetchall()}
    prazo_reabrir = int(configs.get('prazo_reabrir', 3))
    status_expirado_id = configs.get('status_expirado_id')
    status_inicial_id = db.execute("SELECT id FROM status WHERE e_inicial = 1 LIMIT 1").fetchone()['id']

    data_resolvido = datetime.strptime(chamado['resolvido_em'], '%Y-%m-%d %H:%M:%S.%f')
    data_expiracao = data_resolvido + timedelta(days=prazo_reabrir)

    if datetime.now() > data_expiracao:
        flash("O prazo para reabertura deste chamado já expirou.", "danger")
        if status_expirado_id:
            db.execute("UPDATE chamados SET status_id = ? WHERE id = ?", (status_expirado_id, chamado_id))
            db.commit()
    else:
        solucao_antiga = chamado['solucao'] or ''
        timestamp_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        autor = g.user['responsavel']
        nova_entrada = f"[{timestamp_atual} - {autor} (SOLICITANTE)]:\nCHAMADO REABERTO PELO USUÁRIO.\n"
        separador = "-" * 50 + "\n"
        solucao_final = nova_entrada + separador + solucao_antiga

        db.execute(
            "UPDATE chamados SET status_id = ?, resolvido_em = NULL, solucao = ?, admin_responsavel_id = NULL WHERE id = ?",
            (status_inicial_id, solucao_final, chamado_id)
        )
        db.commit()
        flash(f"Chamado #{chamado_id} foi reaberto com sucesso!", "success")

    db.close()
    return redirect(url_for('meus_chamados'))


@app.route('/chamado/capturar/<int:chamado_id>', methods=['POST'])
@login_required
@admin_required
def capturar_chamado(chamado_id):
    db = get_db()
    chamado_atual = db.execute(
        "SELECT c.id FROM chamados c JOIN status s ON c.status_id = s.id WHERE c.id = ? AND s.e_inicial = 1",
        (chamado_id,)).fetchone()
    if not chamado_atual:
        flash('Este chamado não está mais no status inicial e não pode ser capturado.', 'danger')
        db.close()
        return redirect(url_for('meus_chamados'))

    configs = {row['chave']: row['valor'] for row in db.execute("SELECT chave, valor FROM configuracoes").fetchall()}
    status_capturado_id = configs.get('status_capturado_id')

    if not status_capturado_id:
        flash('Erro crítico: Nenhum status de "capturado" configurado no sistema.', 'danger')
        db.close()
        return redirect(url_for('meus_chamados'))

    db.execute(
        'UPDATE chamados SET admin_responsavel_id = ?, status_id = ? WHERE id = ?',
        (g.user['id'], status_capturado_id, chamado_id)
    )
    db.commit()
    db.close()
    flash(f'Chamado #{chamado_id} capturado com sucesso!', 'success')
    return redirect(url_for('meus_chamados'))


# --- ROTAS DO PAINEL DE ADMINISTRAÇÃO ---
@app.route('/dashboard')
@login_required
@admin_required
def dashboard():
    db = get_db()
    kpis = {}

    all_status_counts = db.execute(
        'SELECT s.nome, s.e_inicial, s.e_em_atendimento, s.e_final, COUNT(c.id) as count FROM status s LEFT JOIN chamados c ON s.id = c.status_id GROUP BY s.id'
    ).fetchall()

    kpis['Total'] = db.execute('SELECT COUNT(id) FROM chamados').fetchone()[0]

    kpis['Aberto'] = sum(r['count'] for r in all_status_counts if r['e_inicial'])
    kpis['Em Atendimento'] = sum(r['count'] for r in all_status_counts if r['e_em_atendimento'])
    kpis['Finalizado'] = sum(r['count'] for r in all_status_counts if r['e_final'])
    kpis['Outros'] = kpis['Total'] - (kpis['Aberto'] + kpis['Em Atendimento'] + kpis['Finalizado'])

    status_data_query = """
        SELECT
            CASE WHEN s.e_final = 1 THEN 'finalizados' ELSE s.id END as status_id_agrupado,
            CASE WHEN s.e_final = 1 THEN 'Finalizados' ELSE s.nome END as status_nome_agrupado,
            COUNT(c.id) as total_count
        FROM status s
        LEFT JOIN chamados c ON s.id = c.status_id
        GROUP BY status_id_agrupado, status_nome_agrupado
        HAVING COUNT(c.id) > 0
        ORDER BY status_nome_agrupado;
    """
    status_data = db.execute(status_data_query).fetchall()

    status_ids = [row['status_id_agrupado'] for row in status_data]
    status_labels = [row['status_nome_agrupado'] for row in status_data]
    status_values = [row['total_count'] for row in status_data]

    tipo_data = db.execute(
        'SELECT tp.id, tp.nome, COUNT(c.id) as count FROM chamados c JOIN tipos_problema tp ON c.tipo_problema_id = tp.id GROUP BY tp.id, tp.nome ORDER BY count DESC'
    ).fetchall()
    tipo_ids = [row['id'] for row in tipo_data]
    tipo_labels = [row['nome'] for row in tipo_data]
    tipo_values = [row['count'] for row in tipo_data]

    ultimos_chamados_raw = db.execute("""
        SELECT c.id, c.timestamp, c.solicitante_email, c.municipio, s.nome as status_nome, tp.nome as tipo_problema_nome
        FROM chamados c
        JOIN status s ON c.status_id = s.id
        JOIN tipos_problema tp ON c.tipo_problema_id = tp.id
        ORDER BY c.timestamp DESC LIMIT 5
    """).fetchall()

    ultimos_chamados_formatados = []
    for chamado in ultimos_chamados_raw:
        chamado_dict = dict(chamado)
        data_obj = datetime.strptime(chamado_dict['timestamp'].split('.')[0], '%Y-%m-%d %H:%M:%S')
        chamado_dict['timestamp'] = data_obj.strftime('%d/%m/%Y')
        ultimos_chamados_formatados.append(chamado_dict)

    db.close()

    return render_template(
        'dashboard.html', kpis=kpis,
        status_ids=status_ids, status_labels=status_labels, status_values=status_values,
        tipo_ids=tipo_ids, tipo_labels=tipo_labels, tipo_values=tipo_values,
        ultimos_chamados=ultimos_chamados_formatados
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


@app.route('/admin/configuracoes', methods=['GET', 'POST'])
@login_required
@admin_required
def gerenciar_configuracoes():
    db = get_db()
    if request.method == 'POST':
        prazo_vermelho = request.form.get('prazo_vermelho')
        prazo_amarelo = request.form.get('prazo_amarelo')
        prazo_reabrir = request.form.get('prazo_reabrir')
        status_capturado_id = request.form.get('status_capturado_id')
        status_expirado_id = request.form.get('status_expirado_id')

        if not all(p and p.isdigit() for p in [prazo_vermelho, prazo_amarelo, prazo_reabrir]):
            flash('Os prazos devem ser números inteiros positivos.', 'danger')
        elif int(prazo_vermelho) <= int(prazo_amarelo):
            flash('O prazo para a cor vermelha deve ser maior que o prazo para a cor amarela.', 'danger')
        else:
            db.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                       ('prazo_vermelho', prazo_vermelho))
            db.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                       ('prazo_amarelo', prazo_amarelo))
            db.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                       ('prazo_reabrir', prazo_reabrir))
            db.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                       ('status_capturado_id', status_capturado_id))
            db.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                       ('status_expirado_id', status_expirado_id))
            db.commit()
            flash('Configurações salvas com sucesso!', 'success')

        db.close()
        return redirect(url_for('gerenciar_configuracoes'))

    config_rows = db.execute('SELECT chave, valor FROM configuracoes').fetchall()
    configs = {row['chave']: row['valor'] for row in config_rows}

    status_atendimento_options = db.execute(
        'SELECT id, nome FROM status WHERE e_em_atendimento = 1 ORDER BY nome').fetchall()
    status_finais_options = db.execute(
        'SELECT id, nome FROM status WHERE e_final = 1 AND permite_reabertura = 0 ORDER BY nome').fetchall()

    db.close()

    return render_template('configuracoes.html', configs=configs,
                           status_atendimento_options=status_atendimento_options,
                           status_finais_options=status_finais_options)


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
            flash('Novo status adicionado! Configure seus comportamentos abaixo.', 'success')
        except sqlite3.IntegrityError:
            flash('Este status já existe.', 'danger')
        finally:
            db.close()
    else:
        flash('O nome do status não pode ser vazio.', 'danger')
    return redirect(url_for('gerenciar_cadastros'))


@app.route('/admin/status/update', methods=['POST'])
@login_required
@admin_required
def update_status():
    db = get_db()
    status_inicial_id = request.form.get('e_inicial')

    all_status_ids = [row['id'] for row in db.execute("SELECT id FROM status").fetchall()]

    for status_id in all_status_ids:
        novo_nome = request.form.get(f'nome_{status_id}')
        e_inicial = 1 if str(status_id) == status_inicial_id else 0
        e_em_atendimento = 1 if request.form.get(f'e_em_atendimento_{status_id}') else 0
        permite_reabertura = 1 if request.form.get(f'permite_reabertura_{status_id}') else 0
        e_final = 1 if request.form.get(f'e_final_{status_id}') else 0

        db.execute("""
            UPDATE status 
            SET nome = ?, e_inicial = ?, e_em_atendimento = ?, permite_reabertura = ?, e_final = ? 
            WHERE id = ?
        """, (novo_nome, e_inicial, e_em_atendimento, permite_reabertura, e_final, status_id))

    db.commit()
    db.close()
    flash('Status atualizados com sucesso!', 'success')
    return redirect(url_for('gerenciar_cadastros'))


@app.route('/admin/status/delete/<int:status_id>', methods=['POST'])
@login_required
@admin_required
def delete_status(status_id):
    db = get_db()

    chamado_usando = db.execute('SELECT id FROM chamados WHERE status_id = ?', (status_id,)).fetchone()
    if chamado_usando:
        flash('Não é possível remover este status, pois ele está em uso por um ou mais chamados.', 'danger')
        db.close()
        return redirect(url_for('gerenciar_cadastros'))

    configs_usando = db.execute(
        'SELECT chave FROM configuracoes WHERE (chave = "status_capturado_id" OR chave = "status_expirado_id") AND valor = ?',
        (str(status_id),)
    ).fetchall()

    if configs_usando:
        nomes_config = [c['chave'].replace('_id', '').replace('_', ' ').title() for c in configs_usando]
        flash(
            f'Não é possível remover. Este status está configurado como um status chave em: {", ".join(nomes_config)}.',
            'danger')
        db.close()
        return redirect(url_for('gerenciar_cadastros'))

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


@app.route('/admin/tipos_problema/update', methods=['POST'])
@login_required
@admin_required
def update_tipos_problema():
    db = get_db()
    all_tipo_ids = [row['id'] for row in db.execute("SELECT id FROM tipos_problema").fetchall()]

    for tipo_id in all_tipo_ids:
        novo_nome = request.form.get(f'nome_{tipo_id}')
        if novo_nome:
            try:
                db.execute("UPDATE tipos_problema SET nome = ? WHERE id = ?", (novo_nome, tipo_id))
            except sqlite3.IntegrityError:
                flash(f'O nome "{novo_nome}" já existe. Os nomes dos tipos de problema devem ser únicos.', 'danger')
                db.close()
                return redirect(url_for('gerenciar_cadastros'))

    db.commit()
    db.close()
    flash('Tipos de problema atualizados com sucesso!', 'success')
    return redirect(url_for('gerenciar_cadastros'))


if __name__ == '__main__':
    app.run(debug=True)