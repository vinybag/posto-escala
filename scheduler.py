from models import db, Funcionario, Escala, MesEscala
from datetime import datetime, timedelta
import random
import calendar

HORARIOS_MANHA = ['6-13', '6-14', '7-15']
HORARIOS_TARDE = ['13-21', '14-22', '15-22']

def gerar_escala_mensal(mes=None, ano=None):
    """
    Gera escala para um mês inteiro.
    Se mes/ano não informados, usa o próximo mês.
    """
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if not funcionarios:
        return None
    
    # Definir mês e ano
    hoje = datetime.now().date()
    
    if mes is None or ano is None:
        # Próximo mês
        if hoje.month == 12:
            mes = 1
            ano = hoje.year + 1
        else:
            mes = hoje.month + 1
            ano = hoje.year
    
    # Criar registro do mês
    mes_escala = MesEscala(
        mes=mes,
        ano=ano,
        ativo=True
    )
    db.session.add(mes_escala)
    db.session.flush()  # Para obter o ID
    
    # Buscar histórico do mês anterior para regras
    historico = _carregar_historico(funcionarios, mes, ano)
    
    # Separar funcionários por preferência
    somente_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    somente_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    # Distribuir mistos com rodízio
    turma_manha, turma_tarde = _distribuir_turnos(
        somente_manha, somente_tarde, misto, historico
    )
    
    # Alocar horários fixos
    alocacao_fixa = {}
    
    for i, func in enumerate(turma_manha):
        horario = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
        alocacao_fixa[func.id] = horario
    
    for i, func in enumerate(turma_tarde):
        horario = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
        alocacao_fixa[func.id] = horario
    
    # Obter todas as segundas-feiras do mês
    segundas = _obter_segundas_do_mes(mes, ano)
    
    # Controlar quem já folgou domingo NO MÊS ATUAL
    domingo_no_mes = set()
    func_ids = list(alocacao_fixa.keys())
    
    # Para cada semana do mês
    for num_semana, segunda in enumerate(segundas):
        # Atribuir folgas da semana com controle mensal de domingo
        folga_por_funcionario = _atribuir_folgas_semana_mensal(
            alocacao_fixa, historico, domingo_no_mes
        )
        
        # Atualizar quem folgou domingo nesta semana
        for func_id, dia_folga in folga_por_funcionario.items():
            if dia_folga == 6:
                domingo_no_mes.add(func_id)
        
        # Criar escala para cada dia da semana
        for dia in range(7):
            data = segunda + timedelta(days=dia)
            
            # Verificar se a data pertence ao mês
            if data.month != mes:
                continue
            
            for func_id in alocacao_fixa:
                if folga_por_funcionario.get(func_id) == dia:
                    continue  # Folga
                
                horario = alocacao_fixa[func_id]
                escala = Escala(
                    funcionario_id=func_id,
                    mes_escala_id=mes_escala.id,
                    dia_semana=dia,
                    horario=horario,
                    data=data,
                    ativa=True
                )
                db.session.add(escala)
    
    db.session.commit()
    return mes_escala.id

def _carregar_historico(funcionarios, mes, ano):
    """Carrega histórico do mês anterior"""
    historico = {
        'domingo': set(),
        'turnos': {},
        'ultimas_folgas': {}
    }
    
    # Buscar mês anterior
    if mes == 1:
        mes_ant = 12
        ano_ant = ano - 1
    else:
        mes_ant = mes - 1
        ano_ant = ano
    
    mes_anterior = MesEscala.query.filter_by(mes=mes_ant, ano=ano_ant).first()
    
    if mes_anterior:
        escalas_anteriores = Escala.query.filter_by(mes_escala_id=mes_anterior.id).all()
        
        for func in funcionarios:
            semanas_manha = 0
            semanas_tarde = 0
            
            for e in escalas_anteriores:
                if e.funcionario_id == func.id:
                    # Domingo
                    if e.dia_semana == 6:
                        historico['domingo'].add(func.id)
                    
                    # Turnos
                    if e.horario in HORARIOS_MANHA:
                        semanas_manha += 1
                    elif e.horario in HORARIOS_TARDE:
                        semanas_tarde += 1
            
            historico['turnos'][func.id] = {
                'manha': semanas_manha,
                'tarde': semanas_tarde
            }
    
    return historico


def _distribuir_turnos(somente_manha, somente_tarde, misto, historico):
    """Distribui funcionários mistos entre turnos com rodízio"""
    turma_manha = list(somente_manha)
    turma_tarde = list(somente_tarde)
    
    random.shuffle(misto)
    
    for func in misto:
        hist = historico['turnos'].get(func.id, {'manha': 0, 'tarde': 0})
        
        # Priorizar o turno que o funcionário menos fez
        if hist['manha'] > hist['tarde']:
            turma_tarde.append(func)
        elif hist['tarde'] > hist['manha']:
            turma_manha.append(func)
        else:
            # Aleatório se equilibrado
            if random.random() < 0.5:
                turma_manha.append(func)
            else:
                turma_tarde.append(func)
    
    return turma_manha, turma_tarde


def _atribuir_folgas_semana(alocacao_fixa, historico, num_semana):
    """Atribui folgas para uma semana do mês"""
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    # 4 para domingo (com rodízio)
    candidatos_domingo = []
    for func_id in func_ids:
        if func_id not in historico['domingo']:
            candidatos_domingo.append((func_id, 0))
        else:
            candidatos_domingo.append((func_id, 1))
    
    candidatos_domingo.sort(key=lambda x: x[1])
    folgados_domingo = set(c[0] for c in candidatos_domingo[:4])
    
    folga_por_funcionario = {}
    
    for func_id in func_ids:
        if func_id in folgados_domingo:
            folga_por_funcionario[func_id] = 6
        else:
            dia = random.randint(0, 5)  # SEG a SAB
            folga_por_funcionario[func_id] = dia
    
    return folga_por_funcionario


def _obter_segundas_do_mes(mes, ano):
    """Retorna lista de segundas-feiras do mês"""
    cal = calendar.Calendar()
    segundas = []
    
    for semana in cal.monthdatescalendar(ano, mes):
        segunda = semana[0]  # 0 = segunda-feira
        if segunda.month == mes:
            segundas.append(segunda)
    
    return segundas

def gerar_escala_semanal():
    """
    Gera escala para a próxima semana (mantido para compatibilidade)
    """
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if not funcionarios:
        return False
    
    hoje = datetime.now().date()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    if dias_ate_segunda == 0:
        dias_ate_segunda = 7
    segunda = hoje + timedelta(days=dias_ate_segunda)
    
    # Usar o mês atual
    mes = segunda.month
    ano = segunda.year
    
    # Criar registro do mês se não existir
    mes_escala = MesEscala.query.filter_by(mes=mes, ano=ano).first()
    if not mes_escala:
        mes_escala = MesEscala(mes=mes, ano=ano, ativo=True)
        db.session.add(mes_escala)
        db.session.flush()
    
    # Buscar histórico
    historico = _carregar_historico(funcionarios, mes, ano)
    
    # Separar funcionários
    somente_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    somente_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    turma_manha, turma_tarde = _distribuir_turnos(somente_manha, somente_tarde, misto, historico)
    
    alocacao_fixa = {}
    
    for i, func in enumerate(turma_manha):
        horario = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
        alocacao_fixa[func.id] = horario
    
    for i, func in enumerate(turma_tarde):
        horario = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
        alocacao_fixa[func.id] = horario
    
    # Atribuir folgas
    folga_por_funcionario = _atribuir_folgas_semana(alocacao_fixa, historico, 0)
    
    # Criar escala para cada dia
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        
        for func_id in alocacao_fixa:
            if folga_por_funcionario.get(func_id) == dia:
                continue
            
            horario = alocacao_fixa[func_id]
            escala = Escala(
                funcionario_id=func_id,
                mes_escala_id=mes_escala.id,
                dia_semana=dia,
                horario=horario,
                data=data,
                ativa=True
            )
            db.session.add(escala)
    
    db.session.commit()
    return True

def _atribuir_folgas_semana_mensal(alocacao_fixa, historico, domingo_no_mes):
    """
    Atribui folgas para uma semana do mes com controle mensal de domingo.
    Garante que todos folguem domingo pelo menos 1x antes de repetir.
    """
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    # Separar quem nunca folgou domingo no mes
    nunca_folgou_domingo = [f for f in func_ids if f not in domingo_no_mes]
    ja_folgou_domingo = [f for f in func_ids if f in domingo_no_mes]
    
    # 4 para domingo (prioridade: quem nunca folgou)
    random.shuffle(nunca_folgou_domingo)
    random.shuffle(ja_folgou_domingo)
    
    candidatos_domingo = nunca_folgou_domingo + ja_folgou_domingo
    folgados_domingo = set(candidatos_domingo[:4])
    
    folga_por_funcionario = {}
    
    for func_id in func_ids:
        if func_id in folgados_domingo:
            folga_por_funcionario[func_id] = 6
        else:
            # Evitar mesmo dia da semana passada
            dia_proibido = historico.get('ultimas_folgas', {}).get(func_id, -1)
            dias_disponiveis = [d for d in range(6) if d != dia_proibido]
            
            if not dias_disponiveis:
                dias_disponiveis = list(range(6))
            
            dia_escolhido = random.choice(dias_disponiveis)
            folga_por_funcionario[func_id] = dia_escolhido
    
    return folga_por_funcionario