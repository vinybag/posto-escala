from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

# Estrutura fixa de horários
HORARIOS_FIXOS = {
    'manha': {
        '6-13': 2,
        '6-14': 4,
        '7-15': 2,
    },
    'tarde': {
        '13-21': 2,
        '14-22': 4,
        '15-22': 2,
    }
}

def gerar_escala_semanal():
    # Limpar escala anterior
    Escala.query.filter_by(ativa=True).update({Escala.ativa: False})
    
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if len(funcionarios) < 16:
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
    
    # Embaralhar
    random.shuffle(misto)
    random.shuffle(somente_manha)
    random.shuffle(somente_tarde)
    
    # Distribuir os mistos entre manhã e tarde
    metade_mistos = len(misto) // 2
    mistos_manha = misto[:metade_mistos]
    mistos_tarde = misto[metade_mistos:]
    
    # Juntar turmas
    turma_manha = somente_manha + mistos_manha
    turma_tarde = somente_tarde + mistos_tarde
    
    # Completar vagas restantes
    vagas_manha = 8  # total de vagas na manhã
    vagas_tarde = 8  # total de vagas na tarde
    
    # Se ainda faltar, pegar do misto que sobrou
    if len(turma_manha) < vagas_manha:
        faltam = vagas_manha - len(turma_manha)
        extras = mistos_tarde[:faltam]
        turma_manha.extend(extras)
        turma_tarde = [f for f in turma_tarde if f not in extras]
    
    if len(turma_tarde) < vagas_tarde:
        faltam = vagas_tarde - len(turma_tarde)
        extras = mistos_manha[:faltam]
        turma_tarde.extend(extras)
        turma_manha = [f for f in turma_manha if f not in extras]
    
    # Limitar a 8 por turno
    turma_manha = turma_manha[:8]
    turma_tarde = turma_tarde[:8]
    
    # Alocar horários fixos para cada turma
    alocacao_fixa = {}
    
    # Manhã
    idx = 0
    for horario, qtd in HORARIOS_FIXOS['manha'].items():
        for _ in range(qtd):
            if idx < len(turma_manha):
                func = turma_manha[idx]
                alocacao_fixa[func.id] = horario
                idx += 1
    
    # Tarde
    idx = 0
    for horario, qtd in HORARIOS_FIXOS['tarde'].items():
        for _ in range(qtd):
            if idx < len(turma_tarde):
                func = turma_tarde[idx]
                alocacao_fixa[func.id] = horario
                idx += 1
    
    # Para cada dia da semana
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        # DOMINGO: 4 folgas | Outros dias: 2 folgas
        num_folgas = 4 if dia == 6 else 2
        
        func_ids = list(alocacao_fixa.keys())
        random.shuffle(func_ids)
        folgados = func_ids[:num_folgas]
        
        for func_id in func_ids:
            if func_id not in folgados:
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