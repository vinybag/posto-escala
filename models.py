from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Funcionario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    ultima_folga = db.Column(db.Date)
    preferencia_turno = db.Column(db.String(20))  # manha, tarde, misto

class Escala(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False)
    dia_semana = db.Column(db.Integer)  # 0=segunda, 6=domingo
    horario = db.Column(db.String(20))  # "6-13", "6-14", etc
    data = db.Column(db.Date)
    ativa = db.Column(db.Boolean, default=True)
    
    funcionario = db.relationship('Funcionario', backref='escalas')