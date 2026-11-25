"""
Regras da escala 5x2 (sem acesso a banco de dados).

Baseado na "Calculadora de Escalas 5x2" enviada pelo escritorio de contabilidade:
  - 2 folgas por semana (segunda a domingo);
  - no maximo 5 dias seguidos de trabalho;
  - domingo de folga a cada 3 semanas (CLT art. 67; Lei 10.101/2000 art. 6);
  - mulheres: domingos alternados (CLT art. 386);
  - jornada de 8h24 (etapa 42h) ou 8h (etapa 40h), mais o intervalo;
  - quem muda de turno precisa de 11h de descanso (CLT art. 66).

Este modulo so trabalha com dados simples (dicts, datas) para poder ser testado
sem Flask e sem banco.
"""
import math
import random
import re
from collections import defaultdict
from datetime import timedelta

DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
DIAS_LONGO = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
JORNADA_MIN = {42: 504, 40: 480}        # 8h24 e 8h, em minutos
MAX_SEGUIDOS = 5
DESCANSO_MINIMO = 11 * 60               # minutos
NOMES_GRUPO = {'manha': 'Manha', 'tarde': 'Tarde'}

HORARIOS_ANTIGOS = ['6-13', '6-14', '7-15', '13-21', '14-22', '15-22']


# ----------------------------------------------------------------------------
# Horarios
# ----------------------------------------------------------------------------
def minutos(txt):
    """'06:30' -> 390 ; '6' -> 360."""
    m = re.match(r'^\s*(\d{1,2})(?::(\d{2}))?\s*$', str(txt))
    if not m:
        raise ValueError('Horario invalido: %r' % (txt,))
    return int(m.group(1)) * 60 + int(m.group(2) or 0)


def hhmm(m):
    return '%02d:%02d' % (m // 60, m % 60)


def rotulo(ini, fim):
    return '%s-%s' % (hhmm(ini), hhmm(fim))


def parse_horario(label):
    """'6-13' ou '06:00-15:24' -> (inicio, fim) em minutos."""
    a, b = str(label).split('-', 1)
    return minutos(a), minutos(b)


def inicio_do_horario(label):
    try:
        return parse_horario(label)[0]
    except (ValueError, AttributeError):
        return 0


def grupo_do_horario(label):
    """Turno que comeca antes do meio-dia e 'manha'; os demais sao 'tarde'."""
    return 'manha' if inicio_do_horario(label) < 12 * 60 else 'tarde'


def ordenar_horarios(horarios):
    return sorted(set(horarios), key=lambda h: (inicio_do_horario(h), str(h)))


def montar_turnos(abre, fecha, etapa=42, intervalo=60):
    """
    Mesmo calculo do HTML do contador (moldeTurno/montarTurnos): a jornada
    diaria mais o intervalo forma o turno; se o posto abre mais tempo que um
    turno, entram duas (ou mais) "ondas".  'manha' e a primeira onda e 'tarde'
    a ultima.  Retorna dict com 'manha', 'tarde' (ou None), 'todos', 'pausa'.
    """
    ini0, fim0 = minutos(abre), minutos(fecha)
    dia = fim0 - ini0
    if dia <= 0:
        raise ValueError('O fechamento precisa ser depois da abertura.')
    jornada = JORNADA_MIN.get(int(etapa), JORNADA_MIN[42])
    intervalo = int(intervalo)
    if dia <= 240:
        duracao, pausa = dia, 0
    elif dia <= 375:
        duracao, pausa = dia, 15
    else:
        duracao, pausa = min(dia, jornada + intervalo), intervalo
    ondas = max(1, math.ceil(dia / duracao - 1e-9))
    if ondas == 1:
        inicios = [0]
    else:
        inicios = [(dia - duracao) * o // (ondas - 1) for o in range(ondas)]
    todos = [{'ini': ini0 + i, 'fim': ini0 + i + duracao,
              'rotulo': rotulo(ini0 + i, ini0 + i + duracao)} for i in inicios]
    return {
        'manha': todos[0],
        'tarde': todos[-1] if ondas > 1 else None,
        'todos': todos,
        'pausa': pausa,
        'duracao': duracao,
        'jornada': jornada,
    }


def minimo_domingo(q, mulheres):
    """Menor equipe que deixa q pessoas no domingo (mulheres a cada 2, demais a cada 3)."""
    n = max(q, 0)
    while n - math.ceil(min(mulheres, n) / 2) - math.ceil(max(0, n - mulheres) / 3) < q:
        n += 1
    return n


def pessoas_necessarias(minimos_grupo, mulheres=0):
    """Equipe minima de um turno para cumprir 2 folgas/semana e domingos."""
    if not minimos_grupo or max(minimos_grupo) <= 0:
        return 0
    por_semana = math.ceil(sum(minimos_grupo) / 5 - 1e-9)
    return max(por_semana, max(minimos_grupo), minimo_domingo(minimos_grupo[6], mulheres))


# ----------------------------------------------------------------------------
# Estado (continuidade a partir da escala anterior)
# ----------------------------------------------------------------------------
def segunda_da_semana(d):
    return d - timedelta(days=d.weekday())


def calcular_estado(linhas, antes_de):
    """
    linhas: iteravel de (func_id, data, horario) = dias TRABALHADOS ja conhecidos.
    Para cada funcionario devolve:
       run   : dias seguidos trabalhados ate a vespera de `antes_de`
       dom   : domingos seguidos trabalhados (do mais recente para tras)
       grupo : 'manha'/'tarde' do ultimo horario conhecido (ou None)
       horario: ultimo horario conhecido
    Dias sem nenhum registro (de ninguem) sao tratados como "desconhecidos".
    """
    trab = defaultdict(dict)
    cobertas = set()
    for f, d, h in linhas:
        if d < antes_de:
            trab[f][d] = h
            cobertas.add(d)
    um_dia = timedelta(days=1)
    estado = {}
    domingo_recente = antes_de - timedelta(days=((antes_de.weekday() + 1) % 7) or 7)
    for f, dias in trab.items():
        run, d = 0, antes_de - um_dia
        while d in dias:
            run += 1
            d -= um_dia
        dom, s = 0, domingo_recente
        while s in cobertas and s in dias:
            dom += 1
            s -= timedelta(days=7)
        ultimo = max(dias)
        estado[f] = {'run': run, 'dom': dom, 'horario': dias[ultimo],
                     'grupo': grupo_do_horario(dias[ultimo])}
    return estado


def estado_de(estado, f):
    return dict(estado.get(f) or {'run': 0, 'dom': 0, 'horario': None, 'grupo': None})


# ----------------------------------------------------------------------------
# Distribuicao em turnos (manha / tarde)
# ----------------------------------------------------------------------------
def atribuir_grupos(funcs, estado, turnos, minimos):
    """
    funcs: lista de dict(id, nome, mulher, pref, pode_dom).
    Quem tem preferencia fixa respeita; os "mistos" mantem o turno em que ja
    estavam; os novos entram onde falta gente.
    Retorna dict func_id -> 'manha'/'tarde'.
    """
    tem_tarde = turnos.get('tarde') is not None
    grupos, pendentes = {}, []
    for f in funcs:
        pref = f.get('pref')
        if pref == 'tarde' and tem_tarde:
            grupos[f['id']] = 'tarde'
        elif pref in ('manha', 'tarde'):
            grupos[f['id']] = 'manha'
        else:
            ant = (estado.get(f['id']) or {}).get('grupo')
            if ant == 'manha' or (ant == 'tarde' and tem_tarde):
                grupos[f['id']] = ant
            elif ant == 'tarde':
                grupos[f['id']] = 'manha'
            else:
                pendentes.append(f)
    if pendentes:
        nec = {g: pessoas_necessarias(minimos.get(g, [0] * 7)) for g in ('manha', 'tarde')}
        cont = {g: sum(1 for v in grupos.values() if v == g) for g in ('manha', 'tarde')}
        for f in sorted(pendentes, key=lambda x: x['id']):
            opcoes = ['manha', 'tarde'] if tem_tarde else ['manha']
            g = max(opcoes, key=lambda x: (nec[x] - cont[x], x == 'manha'))
            grupos[f['id']] = g
            cont[g] += 1
    return grupos


# ----------------------------------------------------------------------------
# Geracao semanal
# ----------------------------------------------------------------------------
def _pesar(x):
    return 0 if x <= 0 else (20 if x == 1 else 1000)


def _limite_domingos(f):
    return 1 if f.get('mulher') else 2


def _planejar_semana(membros, minimo, st, rng):
    """
    Define as folgas (0=segunda ... 6=domingo) de um turno em uma semana.
    st: func_id -> {'run','dom'} (alterado no lugar).
    Retorna (folgas {func_id: set}, falta_cobertura, violacoes).
    """
    n = len(membros)
    cap = [n - minimo[d] for d in range(7)]
    folga = {m['id']: set() for m in membros}
    violacoes = 0

    # Domingo: obrigatorio quando ja trabalhou o maximo de domingos seguidos.
    obrig = [m for m in membros if m.get('pode_dom', True) and st[m['id']]['dom'] >= _limite_domingos(m)]
    obrig.sort(key=lambda m: (-st[m['id']]['dom'], rng.random()))
    for m in obrig:
        folga[m['id']].add(6)
        cap[6] -= 1
    # Sobrando vaga no domingo, adianta a folga de quem ja trabalhou domingo.
    if cap[6] > 0:
        extras = [m for m in membros if m.get('pode_dom', True) and 6 not in folga[m['id']]
                  and st[m['id']]['dom'] >= 1]
        extras.sort(key=lambda m: (-st[m['id']]['dom'], rng.random()))
        for m in extras:
            if cap[6] <= 0:
                break
            folga[m['id']].add(6)
            cap[6] -= 1

    # Folgas na semana: quem esta mais perto de estourar 5 dias escolhe primeiro.
    ordem = sorted(membros, key=lambda m: (-st[m['id']]['run'], rng.random()))
    for m in ordem:
        f = m['id']
        k = 2 - len(folga[f])
        if k > 0:
            melhor, melhor_nota = None, -1e18
            cand = [d for d in range(6) if d not in folga[f]]
            combos = [[d] for d in cand] if k == 1 else \
                [[a, b] for i, a in enumerate(cand) for b in cand[i + 1:]]
            for c in combos:
                off = folga[f] | set(c)
                run, exc = st[f]['run'], 0
                for d in range(7):
                    run = 0 if d in off else run + 1
                    exc += _pesar(run - MAX_SEGUIDOS) - _pesar(run - MAX_SEGUIDOS - 1)
                nota = -exc - 0.8 * run
                for d in c:
                    nota += cap[d] if cap[d] > 0 else -60
                    if (d > 0 and (d - 1) in off) or (d < 6 and (d + 1) in off):
                        nota += 1.5
                nota += rng.random() * 0.01
                if nota > melhor_nota:
                    melhor_nota, melhor = nota, c
            for d in melhor or []:
                folga[f].add(d)
                cap[d] -= 1
        # atualiza o estado do funcionario com a semana fechada
        run = st[f]['run']
        for d in range(7):
            run = 0 if d in folga[f] else run + 1
            if run > MAX_SEGUIDOS:
                violacoes += 1
        st[f]['run'] = run
        if 6 in folga[f]:
            st[f]['dom'] = 0
        else:
            st[f]['dom'] += 1
            if st[f]['dom'] > _limite_domingos(m):
                violacoes += 1

    falta = sum(max(0, minimo[d] - (n - sum(1 for f in folga if d in folga[f]))) for d in range(7))
    return folga, falta, violacoes


def gerar_semanas(funcs, segunda, n_semanas, estado, turnos, minimos,
                  tentativas=40, semente=None):
    """
    Gera n_semanas a partir de `segunda`.
    Retorna lista de semanas: {'segunda': date, 'folgas': {func_id:{dias}},
                               'horario': {func_id: rotulo}, 'grupo': {func_id: g}}
    """
    grupos = atribuir_grupos(funcs, estado, turnos, minimos)
    rotulos = {g: (turnos[g]['rotulo'] if turnos.get(g) else None) for g in ('manha', 'tarde')}
    por_grupo = {g: [f for f in funcs if grupos[f['id']] == g] for g in ('manha', 'tarde')}
    base = semente if semente is not None else random.randrange(1 << 30)

    melhor, melhor_pena = None, None
    for t in range(max(1, tentativas)):
        rng = random.Random(base + t)
        st = {f['id']: estado_de(estado, f['id']) for f in funcs}
        semanas, pena = [], 0
        for s in range(n_semanas):
            folgas = {}
            for g in ('manha', 'tarde'):
                membros = por_grupo[g]
                if not membros:
                    continue
                fg, falta, viol = _planejar_semana(membros, minimos.get(g, [0] * 7), st, rng)
                folgas.update(fg)
                pena += falta * 10 + viol * 100
            semanas.append({
                'segunda': segunda + timedelta(days=7 * s),
                'folgas': folgas,
                'grupo': dict(grupos),
                'horario': {f['id']: rotulos[grupos[f['id']]] for f in funcs},
            })
        if melhor_pena is None or pena < melhor_pena:
            melhor, melhor_pena = semanas, pena
        if pena == 0:
            break
    return melhor, melhor_pena


# ----------------------------------------------------------------------------
# Verificacao
# ----------------------------------------------------------------------------
def verificar(linhas, funcs, minimos, d_ini, d_fim):
    """
    linhas: (func_id, data, horario) dos dias trabalhados (inclui o historico
            recente, para que dias seguidos atravessem a virada do mes).
    funcs : dict func_id -> {'nome','mulher'}
    Retorna lista de dict(tipo, texto).
    """
    trab = defaultdict(dict)
    cobertas = set()
    for f, d, h in linhas:
        trab[f][d] = h
        cobertas.add(d)
    avisos = []
    um = timedelta(days=1)
    datas = [d_ini + timedelta(days=i) for i in range((d_fim - d_ini).days + 1)]

    # cobertura minima por turno
    falt = []
    for d in datas:
        for g in ('manha', 'tarde'):
            req = (minimos.get(g) or [0] * 7)[d.weekday()]
            if req <= 0:
                continue
            tem = sum(1 for f in trab if d in trab[f] and grupo_do_horario(trab[f][d]) == g)
            if tem < req:
                falt.append('%s %s (%s): %d de %d' % (DIAS[d.weekday()], d.strftime('%d/%m'),
                                                      NOMES_GRUPO[g].lower(), tem, req))
    if falt:
        resto = ' e mais %d' % (len(falt) - 6) if len(falt) > 6 else ''
        avisos.append({'tipo': 'Cobertura',
                       'texto': 'abaixo do minimo em ' + '; '.join(falt[:6]) + resto + '.'})

    ativos = [f for f in funcs if any(d_ini <= x <= d_fim for x in trab.get(f, {}))]
    nome = lambda f: funcs[f]['nome']

    # 2 folgas por semana
    sem_folga = []
    for f in ativos:
        d = d_ini
        while d <= d_fim:
            dias_trab = sum(1 for i in range(7) if (d + timedelta(days=i)) in trab[f])
            if 7 - dias_trab < 2:
                sem_folga.append('%s na semana de %s' % (nome(f), d.strftime('%d/%m')))
            d += timedelta(days=7)
    if sem_folga:
        resto = ' e mais %d' % (len(sem_folga) - 5) if len(sem_folga) > 5 else ''
        avisos.append({'tipo': 'Folgas', 'texto': 'menos de 2 folgas: ' + '; '.join(sem_folga[:5]) + resto + '.'})

    # dias seguidos e domingos
    seguidos, doms = [], []
    for f in ativos:
        run, maior, fim_run = 0, 0, None
        d = d_ini - timedelta(days=14)
        while d <= d_fim:
            if d in trab[f]:
                run += 1
                if d >= d_ini and run > maior:
                    maior, fim_run = run, d
            else:
                run = 0
            d += um
        if maior > MAX_SEGUIDOS:
            seguidos.append('%s trabalha %d dias seguidos (ate %s)' % (nome(f), maior, fim_run.strftime('%d/%m')))
        lim = _limite_domingos(funcs[f])
        seq = 0
        s = segunda_da_semana(d_ini) - timedelta(days=14) + timedelta(days=6)
        while s <= d_fim:
            if s in cobertas:
                if s in trab[f]:
                    seq += 1
                    if seq > lim and s >= d_ini:
                        doms.append('%s trabalha %d domingos seguidos (ate %s)' % (nome(f), seq, s.strftime('%d/%m')))
                        break
                else:
                    seq = 0
            s += timedelta(days=7)
    if seguidos:
        avisos.append({'tipo': 'Dias seguidos', 'texto': '; '.join(seguidos[:5]) + '.'})
    if doms:
        avisos.append({'tipo': 'Domingo', 'texto': '; '.join(doms[:5]) + '.'})

    # descanso de 11 horas entre jornadas
    curtos = []
    for f in ativos:
        for d in datas:
            a, b = trab[f].get(d), trab[f].get(d + um)
            if a and b:
                try:
                    folga_min = 24 * 60 - parse_horario(a)[1] + parse_horario(b)[0]
                except ValueError:
                    continue
                if folga_min < DESCANSO_MINIMO:
                    curtos.append('%s em %s (%s para %s)' % (nome(f), d.strftime('%d/%m'),
                                                              a.replace('-', ' as '), b.replace('-', ' as ')))
    if curtos:
        resto = ' e mais %d' % (len(curtos) - 5) if len(curtos) > 5 else ''
        avisos.append({'tipo': 'Descanso de 11h', 'texto': '; '.join(curtos[:5]) + resto + '.'})
    return avisos
