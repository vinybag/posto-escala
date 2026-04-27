import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Usuario, Funcionario, Escala
from auth import auth_bp
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-secreta-muito-segura-2024')

# FORÇAR SQLite no diretório persistente do Railway
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
    db.create_all()
    # Criar admin padrão se não existir
    if not Usuario.query.filter_by(username='admin').first():
        admin = Usuario(username='admin', password='admin123', is_admin=True)
        db.session.add(admin)
        db.session.commit()

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
    gerar_escala_semanal()
    
    flash('Nova escala gerada com sucesso!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/escala')
@login_required
def ver_escala():
    escala = Escala.query.filter_by(ativa=True).order_by(Escala.dia_semana, Escala.horario).all()
    return render_template('escala.html', escala=escala)

if __name__ == '__main__':
    app.run(debug=True)