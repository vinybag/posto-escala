from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Funcionario(db.Model):
    __tablename__ = 'funcionarios'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    ultima_folga = db.Column(db.Date)
    preferencia_turno = db.Column(db.String(20))  # manha, tarde, misto
    pode_folgar_domingo = db.Column(db.Boolean, default=True)
    
    escalas = db.relationship('Escala', backref='funcionario', lazy=True)

class MesEscala(db.Model):
    __tablename__ = 'meses_escala'
    
    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.Integer, nullable=False)  # 1 a 12
    ano = db.Column(db.Integer, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.now)
    ativo = db.Column(db.Boolean, default=True)
    
    escalas = db.relationship('Escala', backref='mes_escala', lazy=True)

class Escala(db.Model):
    __tablename__ = 'escalas'
    
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionarios.id'), nullable=False)
    mes_escala_id = db.Column(db.Integer, db.ForeignKey('meses_escala.id'), nullable=True)
    dia_semana = db.Column(db.Integer)  # 0=segunda, 6=domingo
    horario = db.Column(db.String(20))
    data = db.Column(db.Date)
    ativa = db.Column(db.Boolean, default=True)