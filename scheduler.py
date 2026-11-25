"""
Camada entre o banco de dados e o motor da escala 5x2 (escala5x2.py).

A escala atual (6x1 importada) serve de ponto de partida: o estado de cada
funcionario (dias seguidos, domingos trabalhados, turno) e lido do que ja esta
gravado e as proximas semanas sao geradas a partir dele.
"""
import json
import calendar
from datetime import datetime, timedelta

from models import db, Funcionario, Escala, MesEscala, ConfigEscala
import escala5x2 as e5

DIAS_HISTORICO = 56  # 8 semanas de historico bastam para o estado


# ----------------------------------------------------------------------------
# Configuracao
# ----------------------------------------------------------------------------
def obter_config():
    cfg = ConfigEscala.query.first()
    if not cfg:
        cfg = ConfigEscala(abre='06:00', fecha='22:00', etapa=42, intervalo=60)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _minimos_salvos(cfg):
    try:
        dados = json.loads(cfg.minimos) if cfg.minimos else {}
    except ValueError:
        dados = {}
    saida = {}
    for g in ('manha', 'tarde'):
        v = dados.get(g)
        if isinstance(v, list) and len(v) == 7:
            saida[g] = [max(0, int(x)) for x in v]
    return saida


def minimos_padrao(funcs_por_grupo):
    """Sem configuracao: cerca de 5/7 de cada equipe presente em cada dia."""
    saida = {}
    for g in ('manha', 'tarde'):
        n = funcs_por_grupo.get(g, 0)
        saida[g] = [max(1, (n * 5) // 7)] * 7 if n else [0] * 7
    return saida


def montar_contexto(cfg=None):
    cfg = cfg or obter_config()
    turnos = e5.montar_turnos(cfg.abre, cfg.fecha, cfg.etapa or 42, cfg.intervalo or 60)
    return cfg, turnos, _minimos_salvos(cfg)


def salvar_config(abre, fecha, etapa, intervalo, minimos):
    e5.montar_turnos(abre, fecha, etapa, intervalo)  # valida
    cfg = obter_config()
    cfg.abre, cfg.fecha = abre, fecha
    cfg.etapa, cfg.intervalo = int(etapa), int(intervalo)
    cfg.minimos = json.dumps({g: [int(x) for x in minimos[g]] for g in ('manha', 'tarde')})
    db.session.commit()


def horarios_existentes(extra=None):
    """Todos os horarios ja usados (antigos e novos), ordenados, por turno."""
    usados = {h for (h,) in db.session.query(Escala.horario).distinct() if h}
    usados.update(extra or [])
    cfg, turnos, _ = montar_contexto()
    usados.update(t['rotulo'] for t in turnos['todos'])
    ordenados = e5.ordenar_horarios(usados)
    return {
        'manha': [h for h in ordenados if e5.grupo_do_horario(h) == 'manha'],
        'tarde': [h for h in ordenados if e5.grupo_do_horario(h) == 'tarde'],
    }


# ----------------------------------------------------------------------------
# Leitura / escrita
# ----------------------------------------------------------------------------
def _dados_funcs(funcionarios):
    return [{
        'id': f.id, 'nome': f.nome, 'mulher': bool(f.mulher),
        'pref': f.preferencia_turno or 'misto',
        'pode_dom': bool(f.pode_folgar_domingo),
    } for f in funcionarios]


def _linhas_entre(d_ini, d_fim):
    """(func_id, data, horario) dos dias trabalhados, sem duplicar datas repetidas."""
    q = Escala.query.filter(Escala.data >= d_ini, Escala.data <= d_fim)
    vistos, linhas = set(), []
    for e in q.all():
        chave = (e.funcionario_id, e.data)
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append((e.funcionario_id, e.data, e.horario))
    return linhas


def _estado_antes_de(data):
    return e5.calcular_estado(_linhas_entre(data - timedelta(days=DIAS_HISTORICO), data - timedelta(days=1)), data)


def _semana_ja_existe(segunda):
    return Escala.query.filter(Escala.data >= segunda,
                               Escala.data <= segunda + timedelta(days=6)).first() is not None


def _gravar_semana(semana, mes_escala_id, funcs_ids):
    for dia in range(7):
        data = semana['segunda'] + timedelta(days=dia)
        for fid in funcs_ids:
            if dia in semana['folgas'].get(fid, ()):
                continue
            db.session.add(Escala(
                funcionario_id=fid, mes_escala_id=mes_escala_id, dia_semana=dia,
                horario=semana['horario'][fid], data=data, ativa=True))


def _copiar_semana(segunda, mes_escala_id):
    """Semana que atravessa dois meses ja existe: reaproveita (nao muda a escala em vigor)."""
    vistos = set()
    for e in Escala.query.filter(Escala.data >= segunda,
                                 Escala.data <= segunda + timedelta(days=6)).order_by(Escala.id).all():
        chave = (e.funcionario_id, e.data)
        if chave in vistos:
            continue
        vistos.add(chave)
        db.session.add(Escala(
            funcionario_id=e.funcionario_id, mes_escala_id=mes_escala_id,
            dia_semana=e.dia_semana, horario=e.horario, data=e.data,
            ativa=True, caixa=e.caixa))


def _minimos_efetivos(cfg_minimos, funcs, estado, turnos):
    grupos = e5.atribuir_grupos(funcs, estado, turnos, cfg_minimos or {})
    cont = {g: sum(1 for v in grupos.values() if v == g) for g in ('manha', 'tarde')}
    padrao = minimos_padrao(cont)
    return {g: (cfg_minimos or {}).get(g) or padrao[g] for g in ('manha', 'tarde')}


# ----------------------------------------------------------------------------
# Geracao
# ----------------------------------------------------------------------------
def gerar_escala_mensal(mes=None, ano=None):
    """
    Gera o mes com semanas completas (seg a dom), continuando da escala gravada.
    Retorna (mes_escala_id, avisos) ou (None, []) se nao ha funcionarios.
    """
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    if not funcionarios:
        return None, []

    hoje = datetime.now().date()
    if mes is None or ano is None:
        mes, ano = (1, hoje.year + 1) if hoje.month == 12 else (hoje.month + 1, hoje.year)

    cfg, turnos, minimos_cfg = montar_contexto()
    funcs = _dados_funcs(funcionarios)

    primeiro = datetime(ano, mes, 1).date()
    ultimo = datetime(ano, mes, calendar.monthrange(ano, mes)[1]).date()
    segunda = e5.segunda_da_semana(primeiro)
    fim = ultimo + timedelta(days=(6 - ultimo.weekday()))

    mes_escala = MesEscala(mes=mes, ano=ano, ativo=True, regra='5x2')
    db.session.add(mes_escala)
    db.session.flush()

    # Se a escala conhecida termina antes deste mes, preenche as semanas do meio
    # (assim a sequencia de dias seguidos e domingos nao se perde).
    ultima = db.session.query(db.func.max(Escala.data)).filter(
        Escala.data < segunda,
        Escala.data >= segunda - timedelta(days=DIAS_HISTORICO)).scalar()
    if ultima:
        segunda = min(segunda, e5.segunda_da_semana(ultima) + timedelta(days=7))

    # semanas que ja existem (virada do mes) sao copiadas
    atual = segunda
    while atual <= fim and _semana_ja_existe(atual):
        _copiar_semana(atual, mes_escala.id)
        atual += timedelta(days=7)
    db.session.flush()

    if atual <= fim:
        n_sem = ((fim - atual).days + 1) // 7
        estado = _estado_antes_de(atual)
        minimos = _minimos_efetivos(minimos_cfg, funcs, estado, turnos)
        semanas, _ = e5.gerar_semanas(funcs, atual, n_sem, estado, turnos, minimos)
        for s in semanas:
            _gravar_semana(s, mes_escala.id, [f['id'] for f in funcs])

    db.session.commit()
    return mes_escala.id, analisar_mes(mes_escala)


def gerar_escala_semanal():
    """Gera a proxima semana (segunda a domingo). Retorna (ok, avisos)."""
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    if not funcionarios:
        return False, []

    hoje = datetime.now().date()
    segunda = hoje + timedelta(days=(7 - hoje.weekday()) % 7 or 7)

    cfg, turnos, minimos_cfg = montar_contexto()
    funcs = _dados_funcs(funcionarios)
    # refazer a mesma semana substitui a anterior
    Escala.query.filter(Escala.mes_escala_id == None, Escala.data >= segunda,  # noqa
                        Escala.data <= segunda + timedelta(days=6)).delete(synchronize_session=False)
    estado = _estado_antes_de(segunda)
    minimos = _minimos_efetivos(minimos_cfg, funcs, estado, turnos)
    semanas, _ = e5.gerar_semanas(funcs, segunda, 1, estado, turnos, minimos)
    _gravar_semana(semanas[0], None, [f['id'] for f in funcs])
    db.session.commit()

    linhas = _linhas_entre(segunda - timedelta(days=7), segunda + timedelta(days=6))
    mapa = {f['id']: f for f in funcs}
    return True, e5.verificar(linhas, mapa, minimos, segunda, segunda + timedelta(days=6))


# ----------------------------------------------------------------------------
# Analise (alertas mostrados na tela)
# ----------------------------------------------------------------------------
def analisar_mes(mes_escala):
    """Alertas 5x2 do mes. Escalas 6x1 (antigas/importadas) nao sao avaliadas."""
    if not mes_escala or (mes_escala.regra or '6x1') != '5x2':
        return []
    datas = [e.data for e in Escala.query.filter_by(mes_escala_id=mes_escala.id).all() if e.data]
    if not datas:
        return []
    d_ini, d_fim = min(datas), max(datas)
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    funcs = _dados_funcs(funcionarios)
    cfg, turnos, minimos_cfg = montar_contexto()
    estado = _estado_antes_de(d_ini)
    minimos = _minimos_efetivos(minimos_cfg, funcs, estado, turnos)
    linhas = _linhas_entre(d_ini - timedelta(days=7), d_fim)
    mapa = {f['id']: f for f in funcs}
    return e5.verificar(linhas, mapa, minimos, d_ini, d_fim)


def analisar_semana(escala):
    """Alertas da escala semanal; so avalia semanas geradas no formato 5x2 (horario HH:MM-HH:MM)."""
    linhas = [e for e in escala if e.data]
    if not linhas or any(':' not in (e.horario or '') for e in linhas):
        return []
    d_ini, d_fim = min(e.data for e in linhas), max(e.data for e in linhas)
    funcionarios = Funcionario.query.filter_by(ativo=True).all()
    funcs = _dados_funcs(funcionarios)
    cfg, turnos, minimos_cfg = montar_contexto()
    estado = _estado_antes_de(d_ini)
    minimos = _minimos_efetivos(minimos_cfg, funcs, estado, turnos)
    historico = _linhas_entre(d_ini - timedelta(days=7), d_fim)
    return e5.verificar(historico, {f['id']: f for f in funcs}, minimos, d_ini, d_fim)
