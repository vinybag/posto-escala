from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

# Estrutura flexível de horários
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
    
    # Separar funcionários por preferência
    somente_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    somente_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    # Distribuir os mistos igualmente entre manhã e tarde
    metade = len(misto) // 2
    mistos_manha = misto[:metade]
    mistos_tarde = misto[metade:]
    
    # Juntar turmas
    turma_manha = somente_manha + mistos_manha
    turma_tarde = somente_tarde + mistos_tarde
    
    # Se sobrar ímpar, coloca na turma que tiver menos
    if len(misto) % 2 != 0:
        if len(turma_manha) <= len(turma_tarde):
            turma_manha.append(misto[-1])
        else:
            turma_tarde.append(misto[-1])
    
    # Embaralhar para distribuir horários aleatoriamente
    random.shuffle(turma_manha)
    random.shuffle(turma_tarde)
    
    # Alocar horários para cada funcionário
    alocacao_fixa = {}
    
    # Manhã
    for i, func in enumerate(turma_manha):
        horario = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
        alocacao_fixa[func.id] = horario
    
    # Tarde
    for i, func in enumerate(turma_tarde):
        horario = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
        alocacao_fixa[func.id] = horario
    
    # Total de funcionários
    total_funcionarios = len(alocacao_fixa)
    
    # Calcular folgas: cada funcionário folga 1 dia
    # Distribuir as folgas ao longo da semana
    folgas_por_dia = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    
    # Distribuir folgas igualmente
    for i in range(total_funcionarios):
        # Domingo (dia 6) deve ter mais folgas se possível
        if i < total_funcionarios // 7 + (1 if total_funcionarios % 7 > 6 else 0):
            dia = 6  # Domingo
        else:
            dia = i % 7
        
        folgas_por_dia[dia] += 1
    
    # Criar lista de folgas para cada funcionário
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    folga_por_funcionario = {}
    idx = 0
    for dia, qtd in folgas_por_dia.items():
        for _ in range(qtd):
            if idx < len(func_ids):
                folga_por_funcionario[func_ids[idx]] = dia
                idx += 1
    
    # Para cada dia da semana, criar escala
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        for func_id in func_ids:
            if func_id in folga_por_funcionario and folga_por_funcionario[func_id] == dia:
                continue  # Folga neste dia
            
            horario = alocacao_fixa[func_id]
            escala = Escala(
                funcionario_id=func_id,
                dia_semana=dia,
                horario=horario,
                data=data,
                ativa=True
            )
            db.session.add(escala)
    
    db.session.commit()
    return True