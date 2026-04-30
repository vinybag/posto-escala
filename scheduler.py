from models import db, Funcionario, Escala, MesEscala
from datetime import datetime, timedelta
import random
import calendar

HORARIOS_MANHA = ['6-13', '6-14', '7-15']
HORARIOS_TARDE = ['13-21', '14-22', '15-22']


def gerar_escala_mensal(mes=None, ano=None):
    """
    Gera escala para um mes inteiro com semanas completas (seg a dom).
    Inclui dias de meses vizinhos para completar as semanas.
    """
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if not funcionarios:
        return None
    
    # Definir mes e ano
    hoje = datetime.now().date()
    
    if mes is None or ano is None:
        if hoje.month == 12:
            mes = 1
            ano = hoje.year + 1
        else:
            mes = hoje.month + 1
            ano = hoje.year
    
    # Criar registro do mes
    mes_escala = MesEscala(
        mes=mes,
        ano=ano,
        ativo=True
    )
    db.session.add(mes_escala)
    db.session.flush()
    
    # Buscar historico do mes anterior
    historico = _carregar_historico(funcionarios, mes, ano)
    
    # Separar funcionarios por preferencia
    somente_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    somente_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    # Distribuir mistos com rodizio
    turma_manha, turma_tarde = _distribuir_turnos(
        somente_manha, somente_tarde, misto, historico
    )
    
    # Garantir que TODOS os funcionarios ativos estejam incluidos
    todos_ids = {f.id for f in funcionarios}
    alocados_ids = {f.id for f in turma_manha + turma_tarde}
    faltantes = todos_ids - alocados_ids
    
    for func_id in faltantes:
        func = next(f for f in funcionarios if f.id == func_id)
        if len(turma_manha) <= len(turma_tarde):
            turma_manha.append(func)
        else:
            turma_tarde.append(func)
    
    random.shuffle(turma_manha)
    random.shuffle(turma_tarde)
    
    # Alocar horarios - cada funcionario recebe um horario
    alocacao_fixa = {}
    
    for i, func in enumerate(turma_manha):
        horario = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
        alocacao_fixa[func.id] = horario
    
    for i, func in enumerate(turma_tarde):
        horario = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
        alocacao_fixa[func.id] = horario
    
    # Obter primeiro e ultimo dia do mes
    from calendar import monthrange
    primeiro_dia = datetime(ano, mes, 1).date()
    ultimo_dia = datetime(ano, mes, monthrange(ano, mes)[1]).date()
    
    # Encontrar a primeira segunda-feira (pode ser do mes anterior)
    data_atual = primeiro_dia
    while data_atual.weekday() != 0:
        data_atual = data_atual - timedelta(days=1)
    primeira_segunda = data_atual
    
    # Encontrar o ultimo domingo (pode ser do mes seguinte)
    data_atual = ultimo_dia
    while data_atual.weekday() != 6:
        data_atual = data_atual + timedelta(days=1)
    ultimo_domingo = data_atual
    
    # Controlar quem ja folgou domingo no mes
    domingo_no_mes = set()
    
    if historico.get('ultimo_domingo_folgados'):
        domingo_no_mes.update(historico['ultimo_domingo_folgados'])
    
    # Gerar escala da primeira segunda ao ultimo domingo
    data_atual = primeira_segunda
    while data_atual <= ultimo_domingo:
        # Atribuir folgas da semana
        folga_por_funcionario = _atribuir_folgas_semana_mensal(
            alocacao_fixa, historico, domingo_no_mes
        )
        
        # Atualizar quem folgou domingo nesta semana
        for func_id, dia_folga in folga_por_funcionario.items():
            if dia_folga == 6:
                domingo_no_mes.add(func_id)
        
        # Criar escala para cada dia da semana
        for dia in range(7):
            data = data_atual + timedelta(days=dia)
            
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
        
        # Avancar para a proxima segunda-feira
        data_atual = data_atual + timedelta(days=7)
    
    db.session.commit()
    return mes_escala.id


def _carregar_historico(funcionarios, mes, ano):
    """Carrega historico do mes anterior"""
    historico = {
        'domingo': set(),
        'turnos': {},
        'ultimas_folgas': {},
        'ultimo_domingo_folgados': set()
    }
    
    if mes == 1:
        mes_ant = 12
        ano_ant = ano - 1
    else:
        mes_ant = mes - 1
        ano_ant = ano
    
    mes_anterior = MesEscala.query.filter_by(mes=mes_ant, ano=ano_ant).first()
    
    if mes_anterior:
        escalas_anteriores = Escala.query.filter_by(mes_escala_id=mes_anterior.id).all()
        
        # Encontrar o ultimo domingo do mes anterior
        from calendar import monthrange
        ultimo_dia = monthrange(ano_ant, mes_ant)[1]
        data_ultimo_domingo = datetime(ano_ant, mes_ant, ultimo_dia).date()
        while data_ultimo_domingo.weekday() != 6:
            data_ultimo_domingo = data_ultimo_domingo - timedelta(days=1)
        
        # Quem folgou no ultimo domingo
        for func in funcionarios:
            trabalhou_ultimo_domingo = any(
                e.funcionario_id == func.id and e.data == data_ultimo_domingo and e.dia_semana == 6
                for e in escalas_anteriores
            )
            
            if not trabalhou_ultimo_domingo:
                houve_escala = any(e.data == data_ultimo_domingo for e in escalas_anteriores)
                if houve_escala:
                    historico['ultimo_domingo_folgados'].add(func.id)
        
        for func in funcionarios:
            semanas_manha = 0
            semanas_tarde = 0
            
            for e in escalas_anteriores:
                if e.funcionario_id == func.id:
                    if e.dia_semana == 6:
                        historico['domingo'].add(func.id)
                    
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
    """Distribui funcionarios mistos entre turnos com rodizio"""
    turma_manha = list(somente_manha)
    turma_tarde = list(somente_tarde)
    
    random.shuffle(misto)
    
    for func in misto:
        hist = historico['turnos'].get(func.id, {'manha': 0, 'tarde': 0})
        
        if hist['manha'] > hist['tarde']:
            turma_tarde.append(func)
        elif hist['tarde'] > hist['manha']:
            turma_manha.append(func)
        else:
            if random.random() < 0.5:
                turma_manha.append(func)
            else:
                turma_tarde.append(func)
    
    return turma_manha, turma_tarde


def _atribuir_folgas_semana(alocacao_fixa, historico, num_semana):
    """Atribui folgas para uma semana - 4 DOM, resto aleatorio SEG-SAB"""
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    total_func = len(func_ids)
    num_domingo = min(4, total_func)
    
    # Separar quem NAO pode folgar domingo
    nao_pode_domingo = []
    for func_id in func_ids:
        funcionario = Funcionario.query.get(func_id)
        if funcionario and not funcionario.pode_folgar_domingo:
            nao_pode_domingo.append(func_id)
    
    # Candidatos a domingo (quem pode folgar)
    candidatos_domingo = []
    for func_id in func_ids:
        if func_id in nao_pode_domingo:
            continue  # Pula quem nao pode
        
        if func_id not in historico['domingo']:
            candidatos_domingo.append((func_id, 0))
        else:
            candidatos_domingo.append((func_id, 1))
    
    candidatos_domingo.sort(key=lambda x: x[1])
    folgados_domingo = set(c[0] for c in candidatos_domingo[:num_domingo])
    
    folgam_outros = [f for f in func_ids if f not in folgados_domingo]
    random.shuffle(folgam_outros)
    
    folgas_por_dia = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}
    
    # Garantir 1 por dia
    idx = 0
    for dia in range(6):
        if idx < len(folgam_outros):
            folgas_por_dia[dia].append(folgam_outros[idx])
            idx += 1
    
    # Restante aleatorio
    while idx < len(folgam_outros):
        dia_escolhido = random.randint(0, 5)
        folgas_por_dia[dia_escolhido].append(folgam_outros[idx])
        idx += 1
    
    folga_por_funcionario = {}
    
    for func_id in func_ids:
        if func_id in folgados_domingo:
            folga_por_funcionario[func_id] = 6
        else:
            for dia, lista in folgas_por_dia.items():
                if func_id in lista:
                    folga_por_funcionario[func_id] = dia
                    break
    
    return folga_por_funcionario


def _atribuir_folgas_semana_mensal(alocacao_fixa, historico, domingo_no_mes):
    """
    Atribui folgas para uma semana com controle mensal de domingo.
    Domingo: 4 folgas fixas (respeita quem nao pode folgar domingo).
    SEG a SAB: pelo menos 1 folga por dia, restante distribuido aleatoriamente.
    """
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    total_func = len(func_ids)
    num_domingo = min(4, total_func)
    
    # Separar quem NAO pode folgar domingo
    nao_pode_domingo = []
    for func_id in func_ids:
        funcionario = Funcionario.query.get(func_id)
        if funcionario and not funcionario.pode_folgar_domingo:
            nao_pode_domingo.append(func_id)
    
    # Quem nunca folgou domingo (e pode folgar)
    nunca_folgou_domingo = [f for f in func_ids if f not in domingo_no_mes and f not in nao_pode_domingo]
    # Quem ja folgou domingo (e pode folgar)
    ja_folgou_domingo = [f for f in func_ids if f in domingo_no_mes and f not in nao_pode_domingo]
    
    random.shuffle(nunca_folgou_domingo)
    random.shuffle(ja_folgou_domingo)
    
    # Prioridade: quem nunca folgou primeiro
    candidatos_domingo = nunca_folgou_domingo + ja_folgou_domingo
    folgados_domingo = set(candidatos_domingo[:num_domingo])
    
    # Quem nao folga domingo (incluindo quem nao pode + quem nao foi sorteado)
    folgam_outros = [f for f in func_ids if f not in folgados_domingo]
    random.shuffle(folgam_outros)
    
    # Distribuir aleatoriamente, mas garantindo pelo menos 1 por dia
    folgas_por_dia = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}
    
    # Primeiro: garantir 1 folga em cada dia (SEG a SAB)
    dias_disponiveis = list(range(6))
    random.shuffle(dias_disponiveis)
    
    idx = 0
    for dia in dias_disponiveis:
        if idx < len(folgam_outros):
            folgas_por_dia[dia].append(folgam_outros[idx])
            idx += 1
    
    # Depois: distribuir o restante de forma ALEATORIA
    while idx < len(folgam_outros):
        dia_escolhido = random.randint(0, 5)  # SEG a SAB aleatorio
        folgas_por_dia[dia_escolhido].append(folgam_outros[idx])
        idx += 1
    
    # Montar resultado
    folga_por_funcionario = {}
    
    for func_id in func_ids:
        if func_id in folgados_domingo:
            folga_por_funcionario[func_id] = 6  # domingo
        else:
            for dia, lista in folgas_por_dia.items():
                if func_id in lista:
                    folga_por_funcionario[func_id] = dia
                    break
    
    return folga_por_funcionario


def _obter_segundas_do_mes(mes, ano):
    """Retorna lista de segundas-feiras do mes"""
    cal = calendar.Calendar()
    segundas = []
    
    for semana in cal.monthdatescalendar(ano, mes):
        segunda = semana[0]
        if segunda.month == mes:
            segundas.append(segunda)
    
    return segundas


def gerar_escala_semanal():
    """Gera escala para a proxima semana"""
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    
    if not funcionarios:
        return False
    
    hoje = datetime.now().date()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    if dias_ate_segunda == 0:
        dias_ate_segunda = 7
    segunda = hoje + timedelta(days=dias_ate_segunda)
    
    mes = segunda.month
    ano = segunda.year
    
    mes_escala = MesEscala.query.filter_by(mes=mes, ano=ano).first()
    if not mes_escala:
        mes_escala = MesEscala(mes=mes, ano=ano, ativo=True)
        db.session.add(mes_escala)
        db.session.flush()
    
    historico = _carregar_historico(funcionarios, mes, ano)
    
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
    
    folga_por_funcionario = _atribuir_folgas_semana(alocacao_fixa, historico, 0)
    
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