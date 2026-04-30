from models import db, Funcionario, Escala, MesEscala
from datetime import datetime, timedelta
import random
import calendar

HORARIOS_MANHA = ['6-13', '6-14', '7-15']
HORARIOS_TARDE = ['13-21', '14-22', '15-22']


def gerar_escala_mensal(mes=None, ano=None):
    """
    Gera escala para um mes inteiro com semanas completas (seg a dom).
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
    mes_escala = MesEscala(mes=mes, ano=ano, ativo=True)
    db.session.add(mes_escala)
    db.session.flush()
    
    # Buscar historico do mes anterior
    historico = _carregar_historico(funcionarios, mes, ano)
    
    # ============================================
    # DISTRIBUICAO SIMPLES E GARANTIDA
    # ============================================
    
    # Separar por preferencia
    turma_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    turma_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    # Distribuir mistos alternadamente entre manha e tarde
    random.shuffle(misto)
    for i, func in enumerate(misto):
        if i % 2 == 0:
            turma_manha.append(func)
        else:
            turma_tarde.append(func)
    
    # ============================================
    # VERIFICACAO FINAL: TODOS DEVEM ESTAR ALOCADOS
    # ============================================
    todos_ids = {f.id for f in funcionarios}
    alocados = turma_manha + turma_tarde
    alocados_ids = {f.id for f in alocados}
    
    if todos_ids != alocados_ids:
        faltantes = todos_ids - alocados_ids
        for func_id in faltantes:
            func = next(f for f in funcionarios if f.id == func_id)
            if len(turma_manha) <= len(turma_tarde):
                turma_manha.append(func)
            else:
                turma_tarde.append(func)
    
    # Embaralhar
    random.shuffle(turma_manha)
    random.shuffle(turma_tarde)
    
    # Alocar horarios
    alocacao_fixa = {}
    for i, func in enumerate(turma_manha):
        alocacao_fixa[func.id] = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
    for i, func in enumerate(turma_tarde):
        alocacao_fixa[func.id] = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
    
    # Obter primeiro e ultimo dia do mes
    from calendar import monthrange
    primeiro_dia = datetime(ano, mes, 1).date()
    ultimo_dia = datetime(ano, mes, monthrange(ano, mes)[1]).date()
    
    # Encontrar a primeira segunda e ultimo domingo
    data_atual = primeiro_dia
    while data_atual.weekday() != 0:
        data_atual = data_atual - timedelta(days=1)
    primeira_segunda = data_atual
    
    data_atual = ultimo_dia
    while data_atual.weekday() != 6:
        data_atual = data_atual + timedelta(days=1)
    ultimo_domingo = data_atual
    
    # Controlar folgas de domingo
    domingo_no_mes = set()
    if historico.get('ultimo_domingo_folgados'):
        domingo_no_mes.update(historico['ultimo_domingo_folgados'])
    
    # Gerar escala
    data_atual = primeira_segunda
    while data_atual <= ultimo_domingo:
        folga_por_funcionario = _atribuir_folgas_semana_mensal(
            alocacao_fixa, historico, domingo_no_mes
        )
        
        for func_id, dia_folga in folga_por_funcionario.items():
            if dia_folga == 6:
                domingo_no_mes.add(func_id)
        
        for dia in range(7):
            data = data_atual + timedelta(days=dia)
            
            for func_id in alocacao_fixa:
                if folga_por_funcionario.get(func_id) == dia:
                    continue
                
                escala = Escala(
                    funcionario_id=func_id,
                    mes_escala_id=mes_escala.id,
                    dia_semana=dia,
                    horario=alocacao_fixa[func_id],
                    data=data,
                    ativa=True
                )
                db.session.add(escala)
        
        data_atual = data_atual + timedelta(days=7)
    
    db.session.commit()
    return mes_escala.id


def _carregar_historico(funcionarios, mes, ano):
    historico = {
        'domingo': set(),
        'turnos': {},
        'ultimas_folgas': {},
        'ultimo_domingo_folgados': set()
    }
    
    if mes == 1:
        mes_ant, ano_ant = 12, ano - 1
    else:
        mes_ant, ano_ant = mes - 1, ano
    
    mes_anterior = MesEscala.query.filter_by(mes=mes_ant, ano=ano_ant).first()
    
    if mes_anterior:
        escalas_anteriores = Escala.query.filter_by(mes_escala_id=mes_anterior.id).all()
        
        from calendar import monthrange
        ultimo_dia = monthrange(ano_ant, mes_ant)[1]
        data_ultimo_domingo = datetime(ano_ant, mes_ant, ultimo_dia).date()
        while data_ultimo_domingo.weekday() != 6:
            data_ultimo_domingo = data_ultimo_domingo - timedelta(days=1)
        
        for func in funcionarios:
            trabalhou = any(e.funcionario_id == func.id and e.data == data_ultimo_domingo and e.dia_semana == 6 for e in escalas_anteriores)
            if not trabalhou:
                houve = any(e.data == data_ultimo_domingo for e in escalas_anteriores)
                if houve:
                    historico['ultimo_domingo_folgados'].add(func.id)
        
        for func in funcionarios:
            manha = 0
            tarde = 0
            for e in escalas_anteriores:
                if e.funcionario_id == func.id:
                    if e.dia_semana == 6:
                        historico['domingo'].add(func.id)
                    if e.horario in HORARIOS_MANHA:
                        manha += 1
                    elif e.horario in HORARIOS_TARDE:
                        tarde += 1
            historico['turnos'][func.id] = {'manha': manha, 'tarde': tarde}
    
    return historico


def _atribuir_folgas_semana_mensal(alocacao_fixa, historico, domingo_no_mes):
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    total_func = len(func_ids)
    num_domingo = min(4, total_func)
    
    nao_pode_domingo = []
    for func_id in func_ids:
        funcionario = Funcionario.query.get(func_id)
        if funcionario and not funcionario.pode_folgar_domingo:
            nao_pode_domingo.append(func_id)
    
    nunca_folgou = [f for f in func_ids if f not in domingo_no_mes and f not in nao_pode_domingo]
    ja_folgou = [f for f in func_ids if f in domingo_no_mes and f not in nao_pode_domingo]
    
    random.shuffle(nunca_folgou)
    random.shuffle(ja_folgou)
    
    candidatos = nunca_folgou + ja_folgou
    folgados_domingo = set(candidatos[:num_domingo])
    
    folgam_outros = [f for f in func_ids if f not in folgados_domingo]
    random.shuffle(folgam_outros)
    
    folgas_por_dia = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}
    
    idx = 0
    for dia in range(6):
        if idx < len(folgam_outros):
            folgas_por_dia[dia].append(folgam_outros[idx])
            idx += 1
    
    while idx < len(folgam_outros):
        dia = random.randint(0, 5)
        folgas_por_dia[dia].append(folgam_outros[idx])
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


def gerar_escala_semanal():
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    if not funcionarios:
        return False
    
    hoje = datetime.now().date()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    if dias_ate_segunda == 0:
        dias_ate_segunda = 7
    segunda = hoje + timedelta(days=dias_ate_segunda)
    
    mes, ano = segunda.month, segunda.year
    
    mes_escala = MesEscala.query.filter_by(mes=mes, ano=ano).first()
    if not mes_escala:
        mes_escala = MesEscala(mes=mes, ano=ano, ativo=True)
        db.session.add(mes_escala)
        db.session.flush()
    
    historico = _carregar_historico(funcionarios, mes, ano)
    
    turma_manha = [f for f in funcionarios if f.preferencia_turno == 'manha']
    turma_tarde = [f for f in funcionarios if f.preferencia_turno == 'tarde']
    misto = [f for f in funcionarios if f.preferencia_turno == 'misto']
    
    random.shuffle(misto)
    for i, func in enumerate(misto):
        if i % 2 == 0:
            turma_manha.append(func)
        else:
            turma_tarde.append(func)
    
    todos_ids = {f.id for f in funcionarios}
    alocados_ids = {f.id for f in turma_manha + turma_tarde}
    faltantes = todos_ids - alocados_ids
    for func_id in faltantes:
        func = next(f for f in funcionarios if f.id == func_id)
        if len(turma_manha) <= len(turma_tarde):
            turma_manha.append(func)
        else:
            turma_tarde.append(func)
    
    alocacao_fixa = {}
    for i, func in enumerate(turma_manha):
        alocacao_fixa[func.id] = HORARIOS_MANHA[i % len(HORARIOS_MANHA)]
    for i, func in enumerate(turma_tarde):
        alocacao_fixa[func.id] = HORARIOS_TARDE[i % len(HORARIOS_TARDE)]
    
    folga_por_funcionario = _atribuir_folgas_semana(alocacao_fixa, historico)
    
    for dia in range(7):
        data = segunda + timedelta(days=dia)
        for func_id in alocacao_fixa:
            if folga_por_funcionario.get(func_id) == dia:
                continue
            escala = Escala(
                funcionario_id=func_id,
                mes_escala_id=mes_escala.id,
                dia_semana=dia,
                horario=alocacao_fixa[func_id],
                data=data,
                ativa=True
            )
            db.session.add(escala)
    
    db.session.commit()
    return True


def _atribuir_folgas_semana(alocacao_fixa, historico):
    func_ids = list(alocacao_fixa.keys())
    random.shuffle(func_ids)
    
    total_func = len(func_ids)
    num_domingo = min(4, total_func)
    
    nao_pode = []
    for func_id in func_ids:
        func = Funcionario.query.get(func_id)
        if func and not func.pode_folgar_domingo:
            nao_pode.append(func_id)
    
    candidatos = []
    for func_id in func_ids:
        if func_id in nao_pode:
            continue
        if func_id not in historico['domingo']:
            candidatos.append((func_id, 0))
        else:
            candidatos.append((func_id, 1))
    
    candidatos.sort(key=lambda x: x[1])
    folgados_domingo = set(c[0] for c in candidatos[:num_domingo])
    
    folgam_outros = [f for f in func_ids if f not in folgados_domingo]
    random.shuffle(folgam_outros)
    
    folgas_por_dia = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}
    
    idx = 0
    for dia in range(6):
        if idx < len(folgam_outros):
            folgas_por_dia[dia].append(folgam_outros[idx])
            idx += 1
    
    while idx < len(folgam_outros):
        dia = random.randint(0, 5)
        folgas_por_dia[dia].append(folgam_outros[idx])
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