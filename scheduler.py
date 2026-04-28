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
    
    # Buscar TODAS as escalas passadas para controle de domingo
    todas_escalas = Escala.query.all()
    
    # Descobrir quem já folgou domingo (em qualquer semana)
    funcionarios_que_folgaram_domingo = set()
    for escala in todas_escalas:
        if escala.dia_semana == 6:  # 6 = domingo
            # Se o funcionário NÃO trabalhou domingo = folgou
            pass
    
    # Pegar a última escala ativa anterior para descobrir as folgas
    escalas_ultima_semana = Escala.query.filter(
        Escala.data < segunda
    ).order_by(Escala.data.desc()).all()
    
    # Mapear folgas da última semana
    ultima_semana_folgas = {}
    if escalas_ultima_semana:
        # Encontrar a segunda-feira mais recente
        data_ref = escalas_ultima_semana[0].data
        dias_ate_segunda_ref = data_ref.weekday()
        inicio_ultima_semana = data_ref - timedelta(days=dias_ate_segunda_ref)
        fim_ultima_semana = inicio_ultima_semana + timedelta(days=6)
        
        # Descobrir quem folgou cada dia
        for dia in range(7):
            data = inicio_ultima_semana + timedelta(days=dia)
            funcs_trabalharam = set()
            for e in escalas_ultima_semana:
                if e.data == data:
                    funcs_trabalharam.add(e.funcionario_id)
            
            for func in funcionarios:
                if func.id not in funcs_trabalharam:
                    ultima_semana_folgas[func.id] = dia
    
    # HISTÓRICO: Quem já folgou domingo (últimas 4 semanas)
    # Buscar quem folgou domingo nas últimas 4 semanas
    historico_domingo = set()
    for func in funcionarios:
        # Verificar se folgou domingo nas últimas semanas
        for semana_atras in range(1, 5):
            data_domingo = segunda - timedelta(days=semana_atras * 7 - (6 - segunda.weekday()))
            if data_domingo < hoje:
                trabalhou = any(
                    e.funcionario_id == func.id and e.data == data_domingo and e.dia_semana == 6
                    for e in todas_escalas
                )
                if not trabalhou and data_domingo >= (hoje - timedelta(days=28)):
                    historico_domingo.add(func.id)
                    break
    
    # Separar funcionários por preferência
    somente_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    somente_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    # Distribuir mistos
    metade = len(misto) // 2
    mistos_manha = misto[:metade]
    mistos_tarde = misto[metade:]
    
    turma_manha = somente_manha + mistos_manha
    turma_tarde = somente_tarde + mistos_tarde
    
    if len(misto) % 2 != 0:
        if len(turma_manha) <= len(turma_tarde):
            turma_manha.append(misto[-1])
        else:
            turma_tarde.append(misto[-1])
    
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
    # LÓGICA DAS FOLGAS COM RODÍZIO DE DOMINGO
    # ============================================
    
    total_funcionarios = len(alocacao_fixa)
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    # Definir 4 pessoas para folgar domingo
    # PRIORIDADE: Quem NUNCA folgou domingo
    # DEPOIS: Quem folgou há mais tempo
    
    candidatos_domingo = []
    
    for func_id in func_ids:
        if func_id not in historico_domingo:
            # Nunca folgou domingo = alta prioridade
            candidatos_domingo.append((func_id, 0))
        else:
            # Já folgou = baixa prioridade
            candidatos_domingo.append((func_id, 1))
    
    # Ordenar: quem nunca folgou primeiro
    candidatos_domingo.sort(key=lambda x: x[1])
    
    # Pegar os 4 primeiros para folgar domingo
    folgados_domingo = [c[0] for c in candidatos_domingo[:4]]
    
    # Se todo mundo já folgou domingo, pegar os 4 primeiros da lista
    if len(folgados_domingo) < 4:
        folgados_domingo = func_ids[:4]
    
    # Atribuir folgas para os outros dias (exceto domingo para os 4)
    folga_por_funcionario = {}
    
    for func_id in func_ids:
        if func_id in folgados_domingo:
            folga_por_funcionario[func_id] = 6  # Domingo
        else:
            # Escolher um dia que NÃO seja o mesmo da semana passada
            dia_proibido = ultima_semana_folgas.get(func_id, -1)
            dias_disponiveis = [d for d in range(6) if d != dia_proibido]  # 0-5 = SEG a SAB
            
            if not dias_disponiveis:
                dias_disponiveis = list(range(6))
            
            dia_escolhido = random.choice(dias_disponiveis)
            
            # Garantir distribuição uniforme (máximo 2 folgas por dia SEG-SAB)
            count_dia = sum(1 for d in folga_por_funcionario.values() if d == dia_escolhido)
            if count_dia >= 2:
                # Tentar outro dia
                for dia_tentativa in range(6):
                    count = sum(1 for d in folga_por_funcionario.values() if d == dia_tentativa)
                    if count < 2 and dia_tentativa != dia_proibido:
                        dia_escolhido = dia_tentativa
                        break
            
            folga_por_funcionario[func_id] = dia_escolhido
    
    # Criar escala para cada dia
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        for func_id in func_ids:
            if folga_por_funcionario[func_id] == dia:
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