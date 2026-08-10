"""Auditoria automatica de los patrones de bug que YA hicieron dano en AIdan.

READ-ONLY. No toca codigo, no toca la DB, no usa MT5. Solo lee y reporta.

POR QUE ESTE SCRIPT: los 5 bugs del 8-10 ago (v3.52.0 a v3.53.2) fueron todos de la misma
familia — codigo que falla en silencio o umbrales atados a valores inalcanzables — y
NINGUNO necesito muestra estadistica para encontrarse. Se encuentran leyendo. Esa clase de
mejora SI se puede automatizar; los cambios de estrategia no (necesitan n, y AIdan hace
~7 trades/dia).

DISENO CLAVE — BASELINE. Un detector sin baseline es inutil: mi primer intento de detectar
"variable de otro scope" tiraba cientos de falsos positivos y lo descarte. Aca cada chequeo
tiene una lista de hallazgos YA CONOCIDOS (con su explicacion), y el script reporta
SOLO LO NUEVO. Si no hay nada nuevo, dice una linea y termina.

Chequeos, cada uno atado a un bug real:
  1. undefined names (pyflakes)     <- v3.50.4 (SMC muerto), v3.33.0 (M15 muerto 2 semanas)
  2. except que tragan              <- v3.49.0 (loop de aprendizaje roto meses)
  3. ramas mudas de order_send      <- v3.53.0 (close_all_positions fallaba invisible)
  4. codigo inalcanzable            <- news_analyzer keywords huerfano
  5. umbrales relativos a un %      <- v3.52.0 (BE de h1 atado a un TP inalcanzable)
  6. DELETE/UPDATE sin guard        <- v3.53.1 (cap-delete borraba posiciones vivas)
  7. incoherencias de estado en DB  <- deteccion de carreras que dejaron rastro

Correr: python tools/audit_code_patterns.py
Exit code 0 = nada nuevo. 1 = hay hallazgos nuevos para revisar.
"""
import ast
import os
import re
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')

# ── Path de plata: donde un fallo silencioso cuesta dinero ───────────────────
PATH_DE_PLATA = [
    'src/broker/mt5_executor.py',
    'src/broker/position_manager.py',
    'src/common/db.py',
    'AIdan_TodoEnUno.py',
]

# ── BASELINE: hallazgos conocidos y su razon. Solo se reporta lo que NO esta aca ──
CONOCIDOS_UNDEFINED = {
    # wizard de Ollama en la GUI: 3 NameErrors reales pero CERO callers (v3.50.2)
    'OLLAMA_API', 'OLLAMA_URL', 'OLLAMA_MODEL',
    # bloque keywords de news_analyzer: codigo tras un `return None` incondicional,
    # huerfano desde v3.21 cuando el LLM paso a ser obligatorio
    'score',
}

CONOCIDOS_INALCANZABLE = {
    # (archivo, nombre de funcion): razon
    ('src/analyzer/news_analyzer.py', 'analyze_news'):
        'bloque keywords deshabilitado en v3.21, tras `return None` incondicional',
}

# DELETEs sin guard ya evaluados: (archivo, linea aproximada) -> razon para no reportarlos
CONOCIDOS_SQL = {
    'cleanup_old_data':
        'DELETE FROM auto_strategies WHERE created_at < ? — mismo patron que el bug '
        'v3.53.1 (no mira mt5_ticket) PERO la funcion NO tiene callers en produccion, '
        'solo en tests/test_db.py. Deuda latente: si algun dia se la enchufa, filtrar '
        'por mt5_ticket/mt5_status primero.',
}


def _rel(p):
    return os.path.relpath(p, ROOT).replace('\\', '/')


def _fuentes():
    out = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'src')):
        if '__pycache__' in base:
            continue
        out += [os.path.join(base, f) for f in files if f.endswith('.py')]
    out.append(os.path.join(ROOT, 'AIdan_TodoEnUno.py'))
    return out


# ── 1. undefined names ───────────────────────────────────────────────────────
def check_undefined():
    nuevos = []
    try:
        r = subprocess.run([sys.executable, '-m', 'pyflakes'] + _fuentes(),
                           capture_output=True, text=True, timeout=180)
        for line in (r.stdout or '').splitlines():
            m = re.search(r"^(.*?):(\d+):\d+: undefined name '(.+?)'$", line)
            if m and m.group(3) not in CONOCIDOS_UNDEFINED:
                nuevos.append(f"{_rel(m.group(1))}:{m.group(2)} -> '{m.group(3)}'")
    except FileNotFoundError:
        return None, 'pyflakes no instalado (pip install pyflakes)'
    except Exception as e:
        return None, f'no se pudo correr pyflakes: {e}'
    return nuevos, None


# ── 2. except que tragan, en el path de plata ────────────────────────────────
def check_except_mudos():
    hallazgos = []
    for rel in PATH_DE_PLATA:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        try:
            tree = ast.parse(open(p, encoding='utf-8').read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            cuerpo = node.body
            solo_pass = len(cuerpo) == 1 and isinstance(cuerpo[0], ast.Pass)
            solo_debug = (
                len(cuerpo) == 1 and isinstance(cuerpo[0], ast.Expr)
                and isinstance(cuerpo[0].value, ast.Call)
                and isinstance(cuerpo[0].value.func, ast.Attribute)
                and cuerpo[0].value.func.attr == 'debug')
            if solo_pass or solo_debug:
                # cuantas lineas protege: un try ancho que traga es mucho peor
                span = (node.end_lineno or node.lineno) - node.lineno
                hallazgos.append((rel, node.lineno,
                                  'pass' if solo_pass else 'solo logger.debug', span))
    return hallazgos


# ── 3. ramas mudas alrededor de order_send ───────────────────────────────────
def check_ramas_mudas():
    """Un `if result and retcode == DONE:` sin else = un fallo de orden invisible."""
    p = os.path.join(ROOT, 'src/broker/mt5_executor.py')
    if not os.path.exists(p):
        return []
    src = open(p, encoding='utf-8').read()
    tree = ast.parse(src)
    lineas = src.splitlines()
    hallazgos = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or node.orelse:
            continue
        # OJO: hay que mirar el TEST del if, no su cuerpo. Mirando el cuerpo, un `if`
        # externo que CONTIENE un order_send mas abajo daba falso positivo (me paso con
        # el orphan detector, mt5_executor.py:717).
        try:
            test = ast.unparse(node.test)
        except Exception:
            continue
        if 'retcode' in test and 'DONE' in test:
            hallazgos.append(('src/broker/mt5_executor.py', node.lineno,
                              f'sin else: if {test[:60]}'))
    return hallazgos


# ── 4. codigo inalcanzable tras return/raise ─────────────────────────────────
def check_inalcanzable():
    hallazgos = []
    for p in _fuentes():
        rel = _rel(p)
        try:
            tree = ast.parse(open(p, encoding='utf-8').read())
        except Exception:
            continue
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for bloque in (fn.body,):
                for i, st in enumerate(bloque[:-1]):
                    if isinstance(st, (ast.Return, ast.Raise)):
                        sig = bloque[i + 1]
                        if isinstance(sig, ast.Expr) and isinstance(sig.value, ast.Constant):
                            continue    # docstring suelto, ignorar
                        if (rel, fn.name) in CONOCIDOS_INALCANZABLE:
                            continue
                        hallazgos.append((rel, sig.lineno, f'en {fn.name}()'))
                        break
    return hallazgos


# ── 5. umbrales atados a un % de otro valor ──────────────────────────────────
def check_umbrales_relativos():
    """El bug de v3.52.0: BE/trailing/profit-lock atados a un % del TP, y el TP de h1
    era inalcanzable => los tres mecanismos nunca armaron en 67 trades. Esto NO decide
    nada solo: lista los umbrales para que un humano confirme que su rango es alcanzable."""
    # bidireccional a proposito: el codigo real escribe `be_threshold = tp_distance *
    # BE_TRIGGER` (base primero), y mi primera version solo matcheaba `X = f * tp_distance`
    # => daba 0 sitios cuando habia varios. Falso negativo, peor que un falso positivo.
    base = r'(?:tp_distance|tp_pips|sl_distance|sl_pips|ctx\.tp_distance)'
    pats = [re.compile(rf'(\w+)\s*=\s*[\w.]+\s*\*\s*{base}'),
            re.compile(rf'(\w+)\s*=\s*{base}\s*\*\s*[\w.]+'),
            # comparaciones, no solo asignaciones: el profit-lock del PM es
            # `if ctx.hwm >= self.profit_lock_arm * ctx.tp_distance` — justo el umbral
            # que en h1 armaba a 32p con un HWM maximo de 26,3p.
            re.compile(rf'[<>]=?\s*[\w.]+\s*\*\s*{base}')]
    hallazgos = []
    for p in _fuentes():
        for i, ln in enumerate(open(p, encoding='utf-8').read().splitlines(), 1):
            if ln.strip().startswith('#'):
                continue
            for pat in pats:
                m = pat.search(ln)
                if m:
                    hallazgos.append((_rel(p), i, m.group(0).strip()[:70]))
                    break
    return hallazgos


# ── 6. DELETE/UPDATE sin guard de seguridad en db.py ─────────────────────────
def check_sql_sin_guard():
    p = os.path.join(ROOT, 'src/common/db.py')
    if not os.path.exists(p):
        return []
    src = open(p, encoding='utf-8').read()
    tree = ast.parse(src)
    # mapa linea -> funcion, para poder aplicar el baseline por nombre de funcion
    dueno = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for ln in range(fn.lineno, (fn.end_lineno or fn.lineno) + 1):
            dueno[ln] = fn.name
    hallazgos = []
    for m in re.finditer(r'DELETE FROM (\w+)([^"\']*?)(?:"""|\'\'\'|")', src, re.S):
        tabla, resto = m.group(1), m.group(2)
        linea = src[:m.start()].count('\n') + 1
        fn = dueno.get(linea, '?')
        if fn in CONOCIDOS_SQL:
            continue
        if 'WHERE' not in resto.upper():
            hallazgos.append(('src/common/db.py', linea, f'DELETE sin WHERE en {tabla} [{fn}]'))
        elif tabla == 'auto_strategies' and 'mt5_ticket' not in resto:
            # el filtro puede venir de una variable interpolada (patron `{_deletable}`);
            # si el SQL es una f-string, buscar el guard en el cuerpo de la funcion.
            cuerpo_fn = ''
            for f in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                      and n.name == fn]:
                cuerpo_fn = '\n'.join(
                    src.splitlines()[f.lineno - 1:(f.end_lineno or f.lineno)])
            if 'mt5_ticket' in cuerpo_fn and '{' in resto:
                continue    # el guard esta en la variable interpolada (v3.53.1)
            hallazgos.append(('src/common/db.py', linea,
                              f'DELETE en {tabla} sin chequear mt5_ticket [{fn}] (bug v3.53.1)'))
    return hallazgos


# ── 7. incoherencias de estado en la DB ──────────────────────────────────────
def check_db_estado():
    if not os.path.exists(DB):
        return None
    c = sqlite3.connect(DB)
    out = []
    pruebas = [
        ('tickets duplicados en 2 strategy_id',
         "SELECT COUNT(*) FROM (SELECT mt5_ticket FROM auto_strategies "
         "WHERE mt5_ticket IS NOT NULL GROUP BY mt5_ticket HAVING COUNT(DISTINCT id)>1)"),
        ("filled sin ticket",
         "SELECT COUNT(*) FROM auto_strategies WHERE mt5_status='filled' AND mt5_ticket IS NULL"),
        ('be_triggered=1 con trailing_step=0',
         "SELECT COUNT(*) FROM auto_strategies WHERE be_triggered=1 "
         "AND COALESCE(mt5_trailing_step,0)=0"),
        ('archivados duplicados',
         "SELECT COUNT(*) FROM (SELECT strategy_id FROM trade_archive "
         "GROUP BY strategy_id HAVING COUNT(*)>1)"),
        ('archivo con result=win pero mt5_pnl<0',
         "SELECT COUNT(*) FROM trade_archive WHERE result='win' AND mt5_pnl < 0"),
        ('archivo con result=loss pero mt5_pnl>0',
         "SELECT COUNT(*) FROM trade_archive WHERE result='loss' AND mt5_pnl > 0"),
        ('archivados SIN P&L real (P&L fantasma, guard v3.51.1)',
         "SELECT COUNT(*) FROM trade_archive WHERE mt5_pnl IS NULL"),
    ]
    for nombre, q in pruebas:
        try:
            out.append((nombre, c.execute(q).fetchone()[0]))
        except Exception as e:
            out.append((nombre, f'ERR {e}'))
    c.close()
    return out


def main():
    print("=" * 70)
    print("AUDITORIA DE PATRONES — AIdan")
    print("=" * 70)
    nuevo = 0

    und, err = check_undefined()
    print(f"\n[1] undefined names (bug clase v3.50.4 / v3.33.0)")
    if err:
        print(f"    SKIP: {err}")
    elif und:
        nuevo += len(und)
        print(f"    *** {len(und)} NUEVOS ***")
        for h in und:
            print(f"      {h}")
    else:
        print(f"    OK — nada nuevo ({len(CONOCIDOS_UNDEFINED)} conocidos en baseline)")

    ex = check_except_mudos()
    anchos = [h for h in ex if h[3] >= 20]
    print(f"\n[2] except que tragan en el path de plata (bug clase v3.49.0)")
    print(f"    total: {len(ex)} | los que tapan >=20 lineas (los peligrosos): {len(anchos)}")
    for rel, ln, tipo, span in sorted(anchos, key=lambda x: -x[3])[:8]:
        print(f"      {rel}:{ln} ({tipo}, tapa {span} lineas)")
    if anchos:
        nuevo += 0   # informativo: hay muchos historicos, no cuenta como hallazgo nuevo

    rm = check_ramas_mudas()
    print(f"\n[3] ramas mudas de order_send (bug v3.53.0)")
    if rm:
        nuevo += len(rm)
        print(f"    *** {len(rm)} sin else ***")
        for rel, ln, q in rm:
            print(f"      {rel}:{ln} {q}")
    else:
        print("    OK — todos los retcode tienen su else")

    ina = check_inalcanzable()
    print(f"\n[4] codigo inalcanzable tras return/raise")
    if ina:
        nuevo += len(ina)
        print(f"    *** {len(ina)} NUEVOS ***")
        for rel, ln, q in ina[:8]:
            print(f"      {rel}:{ln} {q}")
    else:
        print(f"    OK — nada nuevo ({len(CONOCIDOS_INALCANZABLE)} conocidos en baseline)")

    ur = check_umbrales_relativos()
    print(f"\n[5] umbrales atados a un % del TP/SL (bug v3.52.0) — REVISION MANUAL")
    print(f"    {len(ur)} sitios. Para cada uno: el rango resultante es ALCANZABLE en")
    print(f"    todos los tracks? (h1 tenia el BE a 27p con un HWM maximo de 26,3p)")
    for rel, ln, q in ur[:10]:
        print(f"      {rel}:{ln} {q}")

    sq = check_sql_sin_guard()
    print(f"\n[6] DELETE sin guard en db.py (bug v3.53.1)")
    if sq:
        nuevo += len(sq)
        print(f"    *** {len(sq)} ***")
        for rel, ln, q in sq:
            print(f"      {rel}:{ln} {q}")
    else:
        print("    OK")

    db = check_db_estado()
    print(f"\n[7] incoherencias de estado en la DB")
    if db is None:
        print("    SKIP: no se encontro la DB")
    else:
        for nombre, v in db:
            flag = '' if v == 0 else '   <== REVISAR'
            print(f"    {nombre:52} {v}{flag}")
            if isinstance(v, int) and v > 0:
                nuevo += 1

    print("\n" + "=" * 70)
    if nuevo:
        print(f"RESULTADO: {nuevo} hallazgo(s) para revisar. Ver arriba.")
    else:
        print("RESULTADO: nada nuevo. El codigo esta como la ultima vez.")
    print("=" * 70)
    return 1 if nuevo else 0


if __name__ == '__main__':
    sys.exit(main())
