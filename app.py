import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Usuario, Funcionario, Escala, MesEscala
from auth import auth_bp
from datetime import datetime, timedelta
from sqlalchemy import inspect, text
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-secreta-muito-segura-2024')

# Garantir que o diretório /data existe
if not os.path.exists('/data'):
    os.makedirs('/data', exist_ok=True)

# SQLite no diretório persistente
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/posto.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar banco de dados
db.init_app(app)

# Configurar login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Registrar blueprint de autenticação
app.register_blueprint(auth_bp)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Criar tabelas e admin padrão
with app.app_context():
    try:
        db.create_all()
        
        # Verificar se a coluna mes_escala_id existe na tabela escalas
        inspector = inspect(db.engine)
        colunas = [c['name'] for c in inspector.get_columns('escalas')]
        
        if 'mes_escala_id' not in colunas:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE escalas ADD COLUMN mes_escala_id INTEGER REFERENCES meses_escala(id)'))
                conn.commit()
            print("Coluna mes_escala_id adicionada com sucesso!")
        
        # Verificar se a coluna pode_folgar_domingo existe na tabela funcionarios
        colunas_func = [c['name'] for c in inspector.get_columns('funcionarios')]
        
        if 'pode_folgar_domingo' not in colunas_func:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE funcionarios ADD COLUMN pode_folgar_domingo BOOLEAN DEFAULT 1'))
                conn.commit()
            print("Coluna pode_folgar_domingo adicionada com sucesso!")
        
        # Criar admin padrão se não existir
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(username='admin', password='admin123', is_admin=True)
            db.session.add(admin)
            db.session.commit()
            print("Admin padrão criado!")
    except Exception as e:
        print(f"Erro ao criar banco: {e}")

# ============================================
# ROTAS PRINCIPAIS
# ============================================

@app.route('/')
@login_required
def dashboard():
    funcionarios = Funcionario.query.all()
    escala_atual = Escala.query.filter_by(ativa=True).first()
    return render_template('dashboard.html', funcionarios=funcionarios, escala=escala_atual)

@app.route('/funcionarios')
@login_required
def listar_funcionarios():
    funcionarios = Funcionario.query.all()
    return render_template('funcionarios.html', funcionarios=funcionarios)

@app.route('/funcionarios/novo', methods=['POST'])
@login_required
def novo_funcionario():
    nome = request.form.get('nome')
    preferencia = request.form.get('preferencia', 'misto')
    pode_folgar_domingo = request.form.get('pode_folgar_domingo') == 'sim'
    
    if nome:
        funcionario = Funcionario(
            nome=nome,
            preferencia_turno=preferencia,
            pode_folgar_domingo=pode_folgar_domingo
        )
        db.session.add(funcionario)
        db.session.commit()
        flash('Funcionario cadastrado com sucesso!', 'success')
    return redirect(url_for('listar_funcionarios'))

@app.route('/funcionarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_funcionario(id):
    funcionario = Funcionario.query.get_or_404(id)
    
    if request.method == 'POST':
        funcionario.nome = request.form.get('nome')
        funcionario.preferencia_turno = request.form.get('preferencia')
        funcionario.pode_folgar_domingo = request.form.get('pode_folgar_domingo') == 'sim'
        
        db.session.commit()
        flash(f'Funcionario {funcionario.nome} atualizado com sucesso!', 'success')
        return redirect(url_for('listar_funcionarios'))
    
    return render_template('editar_funcionario.html', funcionario=funcionario)

@app.route('/funcionarios/excluir/<int:id>')
@login_required
def excluir_funcionario(id):
    funcionario = Funcionario.query.get_or_404(id)
    db.session.delete(funcionario)
    db.session.commit()
    flash('Funcionário excluído!', 'success')
    return redirect(url_for('listar_funcionarios'))

@app.route('/gerar-escala')
@login_required
def gerar_escala():
    from scheduler import gerar_escala_semanal
    
    # Desativar escala anterior
    Escala.query.filter_by(ativa=True).update({Escala.ativa: False})
    
    # Gerar nova escala
    resultado = gerar_escala_semanal()
    
    if resultado:
        flash('Nova escala semanal gerada com sucesso!', 'success')
    else:
        flash('Erro: Não há funcionários cadastrados!', 'error')
    
    return redirect(url_for('ver_escala'))

@app.route('/escala')
@login_required
def ver_escala():
    # Mostrar a escala semanal ativa
    escala = Escala.query.filter_by(ativa=True).order_by(Escala.horario, Escala.funcionario_id, Escala.dia_semana).all()
    todos_funcionarios = Funcionario.query.filter_by(ativo=True).all()
    todos_horarios = ['6-13', '6-14', '7-15', '13-21', '14-22', '15-22']
    
    return render_template('escala.html', escala=escala, todos_funcionarios=todos_funcionarios, todos_horarios=todos_horarios)

@app.route('/gerar-escala-mensal', methods=['GET', 'POST'])
@login_required
def gerar_escala_mensal():
    from scheduler import gerar_escala_mensal as gerar_mensal
    
    if request.method == 'POST':
        mes = int(request.form.get('mes'))
        ano = int(request.form.get('ano'))
        resultado = gerar_mensal(mes=mes, ano=ano)
        
        if resultado:
            flash(f'Escala de {mes:02d}/{ano} gerada com sucesso!', 'success')
            return redirect(url_for('ver_escala_mensal', mes_id=resultado))
        else:
            flash('Erro ao gerar escala!', 'error')
            return redirect(url_for('gerar_escala_mensal'))
    
    # GET: mostrar formulário
    meses_disponiveis = _obter_meses_disponiveis()
    return render_template('gerar_mensal.html', meses=meses_disponiveis)

@app.route('/escala-mensal/<int:mes_id>')
@login_required
def ver_escala_mensal(mes_id):
    mes_escala = MesEscala.query.get_or_404(mes_id)
    escala = Escala.query.filter_by(mes_escala_id=mes_id, ativa=True)\
        .order_by(Escala.data, Escala.horario, Escala.funcionario_id).all()
    
    todos_funcionarios = Funcionario.query.filter_by(ativo=True).all()
    meses_disponiveis = MesEscala.query.order_by(MesEscala.ano.desc(), MesEscala.mes.desc()).all()
    todos_horarios = ['6-13', '6-14', '7-15', '13-21', '14-22', '15-22']
    
    # Agrupar escalas por data
    from collections import defaultdict
    
    # Pegar todas as datas unicas da escala
    datas_escala = sorted(set(e.data for e in escala))
    
    if not datas_escala:
        flash('Nenhum dado encontrado para este mes!', 'warning')
        return redirect(url_for('listar_escalas'))
    
    # Agrupar por semana (segunda a domingo)
    semanas = []
    semana_atual = []
    
    for data in datas_escala:
        # Se for segunda-feira (0) e ja tem dias na semana, comeca nova semana
        if data.weekday() == 0 and semana_atual:
            semanas.append(semana_atual)
            semana_atual = []
        
        # Filtrar escalas deste dia
        escalas_do_dia = [e for e in escala if e.data == data]
        
        # Agrupar funcionarios por horario
        funcionarios_por_horario = defaultdict(list)
        for e in escalas_do_dia:
            if e.funcionario not in funcionarios_por_horario[e.horario]:
                funcionarios_por_horario[e.horario].append(e.funcionario)
        
        semana_atual.append({
            'data': data,
            'dia_semana': data.weekday(),
            'escalas': escalas_do_dia,
            'funcionarios_por_horario': dict(funcionarios_por_horario)
        })
    
    # Adicionar ultima semana
    if semana_atual:
        semanas.append(semana_atual)
    
    # Montar estrutura para o template
    semanas_dados = []
    for num, semana in enumerate(semanas):
        dias = []
        escalas_por_dia = {}
        
        # Mapear todas as escalas da semana por (func_id, dia_semana)
        for dia_info in semana:
            for e in dia_info['escalas']:
                escalas_por_dia[(e.funcionario_id, e.dia_semana)] = e
        
        dias = [{'data': d['data'], 'dia_semana': d['dia_semana']} for d in semana]
        
        # Agrupar funcionarios por horario para a semana inteira
        funcionarios_por_horario = defaultdict(list)
        for dia_info in semana:
            for horario, funcs in dia_info['funcionarios_por_horario'].items():
                for f in funcs:
                    if f not in funcionarios_por_horario[horario]:
                        funcionarios_por_horario[horario].append(f)
        
        semanas_dados.append({
            'data_inicio': dias[0]['data'],
            'data_fim': dias[-1]['data'],
            'dias': dias,
            'escalas_por_dia': escalas_por_dia,
            'funcionarios_por_horario': dict(funcionarios_por_horario)
        })
    
    return render_template('escala_mensal.html', 
                         escala=escala, 
                         mes_escala=mes_escala,
                         todos_funcionarios=todos_funcionarios,
                         meses_disponiveis=meses_disponiveis,
                         semanas_dados=semanas_dados,
                         todos_horarios=todos_horarios)

@app.route('/trocar-escala')
@login_required
def trocar_escala():
    func1_id = request.args.get('func1', type=int)
    func2_id = request.args.get('func2', type=int)
    dia = request.args.get('dia', -1, type=int)
    
    # Buscar todas as escalas ativas dos dois funcionários
    escalas_func1 = Escala.query.filter_by(funcionario_id=func1_id, ativa=True).all()
    escalas_func2 = Escala.query.filter_by(funcionario_id=func2_id, ativa=True).all()
    
    if dia == -1:
        # Troca completa entre os dois funcionários
        for escala in escalas_func1:
            escala.funcionario_id = func2_id
        
        for escala in escalas_func2:
            escala.funcionario_id = func1_id
        
        db.session.commit()
        
        func1 = Funcionario.query.get(func1_id)
        func2 = Funcionario.query.get(func2_id)
        flash(f'Troca completa: {func1.nome} ⇄ {func2.nome}', 'success')
    else:
        # Troca apenas em um dia específico
        escala_func1 = Escala.query.filter_by(funcionario_id=func1_id, dia_semana=dia, ativa=True).first()
        escala_func2 = Escala.query.filter_by(funcionario_id=func2_id, dia_semana=dia, ativa=True).first()
        
        if escala_func1 and escala_func2:
            horario_temp = escala_func1.horario
            escala_func1.horario = escala_func2.horario
            escala_func2.horario = horario_temp
            db.session.commit()
            flash(f'Troca realizada no dia!', 'success')
    
    return redirect(url_for('ver_escala'))

@app.route('/escalas')
@login_required
def listar_escalas():
    """Lista todas as escalas geradas"""
    from datetime import datetime
    from sqlalchemy import func
    
    hoje = datetime.now().date()
    
    escalas_mensais = MesEscala.query.order_by(MesEscala.ano.desc(), MesEscala.mes.desc()).all()
    
    # Contar registros da escala semanal
    escala_semanal_count = Escala.query.filter_by(ativa=True, mes_escala_id=None).count()
    
    # Contar semanas por mes
    escalas_mensais_semanas = {}
    for mes in escalas_mensais:
        datas_unicas = db.session.query(Escala.data).filter_by(mes_escala_id=mes.id).distinct().count()
        escalas_mensais_semanas[mes.id] = max(1, datas_unicas // 7)
    
    return render_template('listar_escalas.html', 
                         escalas_mensais=escalas_mensais,
                         escala_semanal_count=escala_semanal_count,
                         escalas_mensais_semanas=escalas_mensais_semanas,
                         current_month=hoje.month,
                         current_year=hoje.year)

@app.route('/excluir-escala-semanal')
@login_required
def excluir_escala_semanal():
    """Exclui a escala semanal atual"""
    count = Escala.query.filter_by(ativa=True).delete()
    db.session.commit()
    flash(f'Escala semanal excluída! ({count} registros removidos)', 'success')
    return redirect(url_for('dashboard'))


@app.route('/excluir-escala-mensal/<int:mes_id>')
@login_required
def excluir_escala_mensal(mes_id):
    """Exclui uma escala mensal completa"""
    mes_escala = MesEscala.query.get_or_404(mes_id)
    
    # Excluir todas as escalas deste mês
    count = Escala.query.filter_by(mes_escala_id=mes_id).delete()
    
    # Excluir o registro do mês
    db.session.delete(mes_escala)
    db.session.commit()
    
    flash(f'Escala de {mes_escala.mes:02d}/{mes_escala.ano} excluída! ({count} registros)', 'success')
    return redirect(url_for('listar_escalas'))

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def _obter_meses_disponiveis():
    """Retorna lista de meses para o dropdown"""
    hoje = datetime.now()
    meses = []
    for i in range(12):
        if hoje.month + i > 12:
            mes = hoje.month + i - 12
            ano = hoje.year + 1
        else:
            mes = hoje.month + i
            ano = hoje.year
        meses.append((mes, ano))
    return meses

@app.context_processor
def utility_processor():
    return dict(timedelta=timedelta)

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/importar-escala', methods=['GET', 'POST'])
@login_required
def importar_escala():
    if request.method == 'POST':
        data_inicio = request.form.get('data_inicio')
        
        try:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        except:
            flash('Data invalida! Use o formato AAAA-MM-DD', 'error')
            return redirect(url_for('importar_escala'))
        
        # Ajustar para segunda-feira
        while data_inicio.weekday() != 0:
            data_inicio = data_inicio - timedelta(days=1)
        
        # Criar mes_escala para essa semana
        mes_escala = MesEscala(
            mes=data_inicio.month,
            ano=data_inicio.year,
            ativo=True
        )
        db.session.add(mes_escala)
        db.session.flush()
        
        # Processar cada linha do formulario
        for i in range(20):
            func_id = request.form.get(f'funcionario_{i}')
            horario = request.form.get(f'horario_{i}')
            
            if not func_id or not horario:
                continue
            
            func_id = int(func_id)
            
            # Processar cada dia da semana
            for dia_offset in range(7):
                data = data_inicio + timedelta(days=dia_offset)
                dia_semana = data.weekday()
                
                status = request.form.get(f'status_{i}_{dia_offset}', '')
                
                if status == 'trabalho':
                    escala = Escala(
                        funcionario_id=func_id,
                        mes_escala_id=mes_escala.id,
                        dia_semana=dia_semana,
                        horario=horario,
                        data=data,
                        ativa=True
                    )
                    db.session.add(escala)
        
        db.session.commit()
        flash('Escala importada com sucesso!', 'success')
        return redirect(url_for('ver_escala_mensal', mes_id=mes_escala.id))
    
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    dias_semana = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM']
    todos_horarios = ['6-13', '6-14', '7-15', '13-21', '14-22', '15-22']
    
    return render_template('importar_escala.html', 
                         funcionarios=funcionarios,
                         dias_semana=dias_semana,
                         todos_horarios=todos_horarios)

@app.route('/trocar-horario/<int:func_id>/<string:horario_antigo>/<string:horario_novo>/<int:mes_id>')
@login_required
def trocar_horario(func_id, horario_antigo, horario_novo, mes_id):
    if mes_id > 0:
        # Escala mensal
        escalas = Escala.query.filter_by(
            funcionario_id=func_id,
            horario=horario_antigo,
            mes_escala_id=mes_id,
            ativa=True
        ).all()
    else:
        # Escala semanal
        escalas = Escala.query.filter_by(
            funcionario_id=func_id,
            horario=horario_antigo,
            ativa=True
        ).all()
    
    for escala in escalas:
        escala.horario = horario_novo
    
    db.session.commit()
    
    func = Funcionario.query.get(func_id)
    flash(f'Horario de {func.nome} alterado para {horario_novo.replace("-", " as ")}!', 'success')
    
    if mes_id > 0:
        return redirect(url_for('ver_escala_mensal', mes_id=mes_id))
    else:
        return redirect(url_for('ver_escala'))
    
@app.route('/trocar-status/<int:func_id>/<int:dia>/<string:horario>/<string:novo_status>/<int:mes_id>')
@login_required
def trocar_status(func_id, dia, horario, novo_status, mes_id):
    if mes_id > 0:
        escala = Escala.query.filter_by(
            funcionario_id=func_id,
            dia_semana=dia,
            mes_escala_id=mes_id,
            ativa=True
        ).first()
    else:
        escala = Escala.query.filter_by(
            funcionario_id=func_id,
            dia_semana=dia,
            ativa=True
        ).first()
    
    if novo_status == 'folga' and escala:
        db.session.delete(escala)
        flash('Status alterado para FOLGA!', 'success')
    elif novo_status == 'trabalho' and not escala:
        if mes_id > 0:
            mes_escala = MesEscala.query.get(mes_id)
            data = mes_escala.data_criacao.date() if mes_escala else datetime.now().date()
        else:
            data = datetime.now().date()
        
        nova_escala = Escala(
            funcionario_id=func_id,
            dia_semana=dia,
            horario=horario,
            data=data,
            ativa=True,
            mes_escala_id=mes_id if mes_id > 0 else None
        )
        db.session.add(nova_escala)
        flash('Status alterado para TRABALHO!', 'success')
    
    db.session.commit()
    
    if mes_id > 0:
        return redirect(url_for('ver_escala_mensal', mes_id=mes_id))
    else:
        return redirect(url_for('ver_escala'))


@app.route('/trocar-horario/<int:func_id>/<string:horario_antigo>/<string:horario_novo>/<int:mes_id>')
@login_required
def trocar_horario(func_id, horario_antigo, horario_novo, mes_id):
    if mes_id > 0:
        escalas = Escala.query.filter_by(
            funcionario_id=func_id,
            horario=horario_antigo,
            mes_escala_id=mes_id,
            ativa=True
        ).all()
    else:
        escalas = Escala.query.filter_by(
            funcionario_id=func_id,
            horario=horario_antigo,
            ativa=True
        ).all()
    
    for escala in escalas:
        escala.horario = horario_novo
    
    db.session.commit()
    
    func = Funcionario.query.get(func_id)
    flash(f'Horario de {func.nome} alterado para {horario_novo.replace("-", " as ")}!', 'success')
    
    if mes_id > 0:
        return redirect(url_for('ver_escala_mensal', mes_id=mes_id))
    else:
        return redirect(url_for('ver_escala'))


@app.route('/importar-escala', methods=['GET', 'POST'])
@login_required
def importar_escala():
    if request.method == 'POST':
        data_inicio = request.form.get('data_inicio')
        
        try:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        except:
            flash('Data invalida! Use o formato AAAA-MM-DD', 'error')
            return redirect(url_for('importar_escala'))
        
        while data_inicio.weekday() != 0:
            data_inicio = data_inicio - timedelta(days=1)
        
        mes_escala = MesEscala(
            mes=data_inicio.month,
            ano=data_inicio.year,
            ativo=True
        )
        db.session.add(mes_escala)
        db.session.flush()
        
        for i in range(20):
            func_id = request.form.get(f'funcionario_{i}')
            horario = request.form.get(f'horario_{i}')
            
            if not func_id or not horario:
                continue
            
            func_id = int(func_id)
            
            for dia_offset in range(7):
                data = data_inicio + timedelta(days=dia_offset)
                dia_semana = data.weekday()
                status = request.form.get(f'status_{i}_{dia_offset}', '')
                
                if status == 'trabalho':
                    escala = Escala(
                        funcionario_id=func_id,
                        mes_escala_id=mes_escala.id,
                        dia_semana=dia_semana,
                        horario=horario,
                        data=data,
                        ativa=True
                    )
                    db.session.add(escala)
        
        db.session.commit()
        flash('Escala importada com sucesso!', 'success')
        return redirect(url_for('ver_escala_mensal', mes_id=mes_escala.id))
    
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    dias_semana = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM']
    todos_horarios = ['6-13', '6-14', '7-15', '13-21', '14-22', '15-22']
    
    return render_template('importar_escala.html', 
                         funcionarios=funcionarios,
                         dias_semana=dias_semana,
                         todos_horarios=todos_horarios)


# ============================================
# ROTA DE VERIFICACAO
# ============================================
@app.route('/verificar-funcionarios')
@login_required
def verificar_funcionarios():
    funcs = Funcionario.query.filter_by(ativo=True).all()
    escala = Escala.query.filter_by(ativa=True).all()
    funcs_na_escala = set(e.funcionario_id for e in escala)
    faltantes = set(f.id for f in funcs) - funcs_na_escala
    
    resultado = f"<h2>Total ativos: {len(funcs)}</h2>"
    resultado += f"<h2>Na escala: {len(funcs_na_escala)}</h2>"
    resultado += f"<h2>Faltantes: {len(faltantes)}</h2><ul>"
    for fid in faltantes:
        f = Funcionario.query.get(fid)
        resultado += f"<li>FALTANDO: {f.nome} (pref: {f.preferencia_turno})</li>"
    resultado += "</ul>"
    return resultado


# ============================================
# FUNCOES AUXILIARES
# ============================================
def _obter_meses_disponiveis():
    """Retorna lista de meses para o dropdown"""
    hoje = datetime.now()
    meses = []
    for i in range(12):
        if hoje.month + i > 12:
            mes = hoje.month + i - 12
            ano = hoje.year + 1
        else:
            mes = hoje.month + i
            ano = hoje.year
        meses.append((mes, ano))
    return meses


@app.context_processor
def utility_processor():
    return dict(timedelta=timedelta)


if __name__ == '__main__':
    app.run(debug=True)