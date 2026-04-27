from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

# Estrutura fixa de horários
HORARIOS_FIXOS = {
    'manha': {
        '6-13': 2,   # 2 funcionários
        '6-14': 4,   # 4 funcionários
        '7-15': 2,   # 2 funcionários
    },
    'tarde': {
        '13-21': 2,  # 2 funcionários
        '14-22': 4,  # 4 funcionários
        '15-22': 2,  # 2 funcionários
    }
}

def gerar_escala_semanal():
    # Limpar escala anterior
    Escala.query.filter_by(ativa=True).update({Escala.ativa: False})
    
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if len(funcionarios) < 16:
        return False  # Precisa de pelo menos 16 funcionários
    
    # Data da próxima segunda-feira
    hoje = datetime.now().date()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    if dias_ate_segunda == 0:
        dias_ate_segunda = 7
    segunda = hoje + timedelta(days=dias_ate_segunda)
    
    # Embaralhar funcionários para distribuição aleatória
    random.shuffle(funcionarios)
    
    # Atribuir horários fixos aos funcionários
    alocacao_fixa = {}
    
    # Alocar manhã
    idx = 0
    for horario, qtd in HORARIOS_FIXOS['manha'].items():
        for _ in range(qtd):
            if idx < len(funcionarios):
                alocacao_fixa[funcionarios[idx].id] = horario
                idx += 1
    
    # Alocar tarde
    for horario, qtd in HORARIOS_FIXOS['tarde'].items():
        for _ in range(qtd):
            if idx < len(funcionarios):
                alocacao_fixa[funcionarios[idx].id] = horario
                idx += 1
    
    # Para cada dia da semana (0=SEG a 6=DOM)
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        # Definir folgas do dia
        if dia == 6:  # DOMINGO: 4 folgas
            num_folgas = 4
        else:  # Outros dias: 2 folgas (para 16 func = escala 6x1)
            num_folgas = 2
        
        # Escolher aleatoriamente quem folga neste dia
        func_ids = list(alocacao_fixa.keys())
        
        # Garantir que ninguém folgue 2 vezes
        random.shuffle(func_ids)
        folgados = func_ids[:num_folgas]
        
        # Alocar quem trabalha
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