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
    
    if nome:
        funcionario = Funcionario(
            nome=nome,
            preferencia_turno=preferencia
        )
        db.session.add(funcionario)
        db.session.commit()
        flash('Funcionário cadastrado com sucesso!', 'success')
    return redirect(url_for('listar_funcionarios'))

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
    # Buscar a escala do mes atual
    hoje = datetime.now().date()
    mes_atual = hoje.month
    ano_atual = hoje.year
    
    mes_escala = MesEscala.query.filter_by(mes=mes_atual, ano=ano_atual).first()
    
    # Se nao tem do mes atual, pega a mais recente
    if not mes_escala:
        mes_escala = MesEscala.query.order_by(MesEscala.id.desc()).first()
    
    if mes_escala:
        return redirect(url_for('ver_escala_mensal', mes_id=mes_escala.id))
    else:
        flash('Nenhuma escala encontrada. Gere uma escala mensal!', 'warning')
        return redirect(url_for('gerar_escala_mensal'))

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
    
    return render_template('escala_mensal.html', 
                         escala=escala, 
                         mes_escala=mes_escala,
                         todos_funcionarios=todos_funcionarios,
                         meses_disponiveis=meses_disponiveis)

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