import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Usuario, Funcionario, Escala
from auth import auth_bp
from datetime import datetime, timedelta
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
        # Criar admin padrão se não existir
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(username='admin', password='admin123', is_admin=True)
            db.session.add(admin)
            db.session.commit()
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
        flash('Nova escala gerada com sucesso!', 'success')
    else:
        flash('Erro: Não há funcionários cadastrados!', 'error')
    
    return redirect(url_for('ver_escala'))

@app.route('/escala')
@login_required
def ver_escala():
    escala = Escala.query.filter_by(ativa=True).order_by(Escala.horario, Escala.funcionario_id, Escala.dia_semana).all()
    return render_template('escala.html', escala=escala)

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/trocar-escala/<int:func1_id>/<int:func2_id>/<int:dia>')
@login_required
def trocar_escala(func1_id, func2_id, dia):
    # Buscar as escalas ativas dos dois funcionários no dia específico
    escala_func1 = Escala.query.filter_by(
        funcionario_id=func1_id,
        dia_semana=dia,
        ativa=True
    ).first()
    
    escala_func2 = Escala.query.filter_by(
        funcionario_id=func2_id,
        dia_semana=dia,
        ativa=True
    ).first()
    
    if escala_func1 and escala_func2:
        # Trocar os horários
        horario_temp = escala_func1.horario
        escala_func1.horario = escala_func2.horario
        escala_func2.horario = horario_temp
        db.session.commit()
        flash('Troca realizada com sucesso!', 'success')
    elif escala_func1 and not escala_func2:
        # Func1 trabalha, Func2 folga -> Func1 folga, Func2 trabalha
        funcionario = Funcionario.query.get(func2_id)
        # Descobrir qual horário o func2 deveria ter
        # Buscar outros dias do func2 para saber o horário dele
        outra_escala = Escala.query.filter_by(
            funcionario_id=func2_id,
            ativa=True
        ).first()
        
        if outra_escala:
            # Criar escala para func2 no lugar do func1
            nova_escala = Escala(
                funcionario_id=func2_id,
                dia_semana=dia,
                horario=escala_func1.horario,
                data=escala_func1.data,
                ativa=True
            )
            db.session.add(nova_escala)
            db.session.delete(escala_func1)
            db.session.commit()
            flash('Troca com folga realizada!', 'success')
    
    return redirect(url_for('ver_escala'))    