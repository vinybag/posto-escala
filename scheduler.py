from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

HORARIOS = {
    'manha': ['6-13', '6-14', '7-15'],
    'tarde': ['13-21', '14-22', '15-22']
}

def gerar_escala_semanal():
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if not funcionarios:
        return False
    
    # Data da próxima segunda-feira
    hoje = datetime.now().date()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    if dias_ate_segunda == 0:
        dias_ate_segunda = 7
    segunda = hoje + timedelta(days=dias_ate_segunda)
    
    # Controlar folgas da semana
    folgas_semana = {f.id: 0 for f in funcionarios}
    
    # Para cada dia da semana
    for dia in range(7):  # 0=segunda a 6=domingo
        data = segunda + timedelta(days=dia)
        
        # Misturar funcionários para distribuir aleatoriamente
        func_disponiveis = funcionarios.copy()
        random.shuffle(func_disponiveis)
        
        # Alocar horários da manhã
        alocar_turno(func_disponiveis, 'manha', data, dia, folgas_semana)
        
        # Alocar horários da tarde
        alocar_turno(func_disponiveis, 'tarde', data, dia, folgas_semana)
    
    db.session.commit()
    return True

def alocar_turno(funcionarios, turno, data, dia_semana, folgas_semana):
    horarios = HORARIOS[turno]
    random.shuffle(horarios)
    
    for horario in horarios:
        alocado = False
        for func in funcionarios:
            # Verificar se já trabalhou nesse dia
            ja_trabalha = Escala.query.filter_by(
                funcionario_id=func.id,
                data=data
            ).first()
            
            if ja_trabalha:
                continue
            
            # Verificar se não excedeu folgas (6x1 = 1 folga por semana)
            if folgas_semana[func.id] > 1:
                continue
            
            # Criar escala
            escala = Escala(
                funcionario_id=func.id,
                dia_semana=dia_semana,
                horario=horario,
                data=data,
                ativa=True
            )
            db.session.add(escala)
            alocado = True
            break
        
        # Se não alocou, o funcionário terá folga nesse horário
        if not alocado and funcionarios:
            func = funcionarios[0]
            if folgas_semana[func.id] < 1:
                folgas_semana[func.id] += 1
                # Registrar folga
                func.ultima_folga = data