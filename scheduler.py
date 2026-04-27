from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

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
    
    # Definir 1 dia de folga para cada funcionário
    folgas = {}
    for func in funcionarios:
        dia_folga = random.randint(0, 6)
        folgas[func.id] = dia_folga
    
    # Para cada dia da semana (0=segunda a 6=domingo)
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        # Funcionários que trabalham neste dia (não estão de folga)
        funcionarios_do_dia = [f for f in funcionarios if folgas[f.id] != dia]
        
        # Misturar para distribuir turnos aleatoriamente
        random.shuffle(funcionarios_do_dia)
        
        # Dividir em manhã e tarde
        total = len(funcionarios_do_dia)
        metade = total // 2
        
        funcionarios_manha = funcionarios_do_dia[:metade]
        funcionarios_tarde = funcionarios_do_dia[metade:]
        
        # Alocar turno da manhã (6-13, 6-14, 7-15)
        alocar_turno(funcionarios_manha, ['6-13', '6-14', '7-15'], data, dia)
        
        # Alocar turno da tarde (13-21, 14-22, 15-22)
        alocar_turno(funcionarios_tarde, ['13-21', '14-22', '15-22'], data, dia)
    
    db.session.commit()
    return True

def alocar_turno(funcionarios, horarios, data, dia_semana):
    """
    Aloca cada funcionário em UM ÚNICO horário por dia
    """
    # Se não há funcionários, não faz nada
    if not funcionarios:
        return
    
    # Distribuir funcionários nos horários disponíveis
    for i, funcionario in enumerate(funcionarios):
        # Cada funcionário pega um horário
        indice_horario = i % len(horarios)
        horario = horarios[indice_horario]
        
        # Criar ÚNICO registro de escala para este funcionário neste dia
        escala = Escala(
            funcionario_id=funcionario.id,
            dia_semana=dia_semana,
            horario=horario,
            data=data,
            ativa=True
        )
        db.session.add(escala)