from models import db, Funcionario, Escala
from datetime import datetime, timedelta
import random

HORARIOS_MANHA = ['6-13', '6-14', '7-15']
HORARIOS_TARDE = ['13-21', '14-22', '15-22']

def gerar_escala_semanal():
    # Limpar escala atual
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
    
    # Buscar histórico para rodízio de domingo e turnos
    todas_escalas = Escala.query.order_by(Escala.data.desc()).all()
    
    # ============================================
    # RODÍZIO DE DOMINGO (já existente)
    # ============================================
    
    historico_domingo = set()
    for func in funcionarios:
        for e in todas_escalas:
            if e.funcionario_id == func.id and e.dia_semana == 6:
                historico_domingo.add(func.id)
                break
    
    ultima_semana_folgas = {}
    if todas_escalas:
        data_ref = todas_escalas[0].data
        inicio_ultima_semana = data_ref - timedelta(days=data_ref.weekday())
        fim_ultima_semana = inicio_ultima_semana + timedelta(days=6)
        
        for dia in range(7):
            data = inicio_ultima_semana + timedelta(days=dia)
            funcs_trabalharam = set()
            for e in todas_escalas:
                if e.data == data:
                    funcs_trabalharam.add(e.funcionario_id)
            for func in funcionarios:
                if func.id not in funcs_trabalharam:
                    ultima_semana_folgas[func.id] = dia
    
    # ============================================
    # RODÍZIO DE TURNO PARA MISTOS (NOVO!)
    # ============================================
    
    # Verificar quantas semanas cada misto ficou em cada turno
    historico_turnos = {}
    for func in funcionarios:
        if func.preferencia_turno == 'misto':
            semanas_manha = 0
            semanas_tarde = 0
            semana_atual = None
            turno_atual = None
            
            for e in todas_escalas:
                if e.funcionario_id == func.id:
                    num_semana = e.data.isocalendar()[1]  # Número da semana
                    
                    if semana_atual != num_semana:
                        if turno_atual == 'manha':
                            semanas_manha += 1
                        elif turno_atual == 'tarde':
                            semanas_tarde += 1
                        semana_atual = num_semana
                    
                    if e.horario in HORARIOS_MANHA:
                        turno_atual = 'manha'
                    elif e.horario in HORARIOS_TARDE:
                        turno_atual = 'tarde'
            
            # Último turno
            if turno_atual == 'manha':
                semanas_manha += 1
            elif turno_atual == 'tarde':
                semanas_tarde += 1
            
            historico_turnos[func.id] = {
                'manha': semanas_manha,
                'tarde': semanas_tarde,
                'ultimo_turno': turno_atual
            }
    
    # Separar funcionários por preferência
    somente_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    somente_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    # Distribuir mistos com RODÍZIO
    # Prioridade: quem está há mais tempo sem mudar de turno
    misto_prioridade = []
    for func in misto:
        if func.id in historico_turnos:
            hist = historico_turnos[func.id]
            # Se ficou muito tempo no mesmo turno, prioridade para mudar
            if hist['ultimo_turno'] == 'manha':
                prioridade = hist['manha']  # Quanto maior, mais precisa ir pra tarde
            elif hist['ultimo_turno'] == 'tarde':
                prioridade = -hist['tarde']  # Quanto menor (negativo), mais precisa ir pra manhã
            else:
                prioridade = 0
        else:
            prioridade = 0  # Novo funcionário, sem histórico
        
        misto_prioridade.append((func, prioridade))
    
    # Ordenar por prioridade (quem precisa mudar primeiro)
    random.shuffle(misto_prioridade)
    
    # Distribuir entre manhã e tarde
    turma_manha = list(somente_manha)
    turma_tarde = list(somente_tarde)
    
    # Calcular quantos mistos vão para cada turno
    # Tentar equilibrar os turnos
    total_manha = len(somente_manha)
    total_tarde = len(somente_tarde)
    
    for func, prioridade in misto_prioridade:
        # Se já está equilibrado, sortear
        if abs(total_manha - total_tarde) <= 1:
            if random.random() < 0.5:
                turma_manha.append(func)
                total_manha += 1
            else:
                turma_tarde.append(func)
                total_tarde += 1
        # Se manhã tem menos, manda pra manhã
        elif total_manha < total_tarde:
            turma_manha.append(func)
            total_manha += 1
        # Se tarde tem menos, manda pra tarde
        else:
            turma_tarde.append(func)
            total_tarde += 1
    
    random.shuffle(turma_manha)
    random.shuffle(turma_tarde)
    
    # Alocar horários
    alocacao_fixa = {}
    
    for i, func in enumerate(turma_manha):
        horario = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
        alocacao_fixa[func.id] = horario
    
    for i, func in enumerate(turma_tarde):
        horario = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
        alocacao_fixa[func.id] = horario
    
    # ============================================
    # ATRIBUIR FOLGAS (com rodízio de domingo)
    # ============================================
    
    total_funcionarios = len(alocacao_fixa)
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    # 4 para domingo
    candidatos_domingo = []
    for func_id in func_ids:
        if func_id not in historico_domingo:
            candidatos_domingo.append((func_id, 0))
        else:
            candidatos_domingo.append((func_id, 1))
    
    candidatos_domingo.sort(key=lambda x: x[1])
    folgados_domingo = [c[0] for c in candidatos_domingo[:4]]
    
    if len(folgados_domingo) < 4:
        folgados_domingo = func_ids[:4]
    
    folga_por_funcionario = {}
    
    for func_id in func_ids:
        if func_id in folgados_domingo:
            folga_por_funcionario[func_id] = 6
        else:
            dia_proibido = ultima_semana_folgas.get(func_id, -1)
            dias_disponiveis = [d for d in range(6) if d != dia_proibido]
            
            if not dias_disponiveis:
                dias_disponiveis = list(range(6))
            
            dia_escolhido = random.choice(dias_disponiveis)
            
            count_dia = sum(1 for d in folga_por_funcionario.values() if d == dia_escolhido)
            if count_dia >= 2:
                for dia_tentativa in range(6):
                    count = sum(1 for d in folga_por_funcionario.values() if d == dia_tentativa)
                    if count < 2 and dia_tentativa != dia_proibido:
                        dia_escolhido = dia_tentativa
                        break
            
            folga_por_funcionario[func_id] = dia_escolhido
    
    # Criar escala
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        for func_id in func_ids:
            if folga_por_funcionario[func_id] == dia:
                continue
            
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