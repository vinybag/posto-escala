from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

HORARIOS_MANHA = ['6-13', '6-14', '7-15']
HORARIOS_TARDE = ['13-21', '14-22', '15-22']

def gerar_escala_semanal():
    # Limpar escala anterior
    Escala.query.filter_by(ativa=True).update({Escala.ativa: False})
    
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if not funcionarios:
        return False
    
    # Data da próxima segunda-feira
    hoje = datetime.now().date()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    if dias_ate_segunda == 0:
        dias_ate_segunda = 7
    segunda = hoje + timedelta(days=dias_ate_segunda)
    
    # Para cada funcionário, escolher 1 dia de folga aleatório
    dia_folga_por_func = {}
    for func in funcionarios:
        dia_folga_por_func[func.id] = random.randint(0, 6)
    
    # Para cada dia da semana (0=SEG a 6=DOM)
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        # Quem trabalha neste dia
        trabalhadores = [f for f in funcionarios if dia_folga_por_func[f.id] != dia]
        
        # Misturar
        random.shuffle(trabalhadores)
        
        # Dividir manhã e tarde
        metade = len(trabalhadores) // 2
        manha = trabalhadores[:metade]
        tarde = trabalhadores[metade:]
        
        # Alocar manhã (cada um em UM horário)
        for i, func in enumerate(manha):
            horario = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
            escala = Escala(
                funcionario_id=func.id,
                dia_semana=dia,
                horario=horario,
                data=data,
                ativa=True
            )
            db.session.add(escala)
        
        # Alocar tarde (cada um em UM horário)
        for i, func in enumerate(tarde):
            horario = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
            escala = Escala(
                funcionario_id=func.id,
                dia_semana=dia,
                horario=horario,
                data=data,
                ativa=True
            )
            db.session.add(escala)
    
    db.session.commit()
    return True