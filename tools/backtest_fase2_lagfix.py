"""
backtest_fase2_lagfix.py — FASE 2b: ¿el "peor que el azar" era la IDEA o un BUG de cálculo?

READ-ONLY. Mismo arnés que tools/backtest_fase2.py (se importa, no se copia), con UNA diferencia:
en la variante `lagfix` el detector se carga desde el fuente de src/analyzer/technical.py con 4
índices corridos una posición (ver LAGFIX_EDITS). Producción no se toca: la transformación vive en
memoria y cada reemplazo tiene que matchear EXACTAMENTE una vez o aborta (si alguien cambia
technical.py, esto falla fuerte en vez de medir otra cosa).

Criterio de lectura declarado ANTES de correr: docs/fase2b_lagfix_criterio.md (c668b8c).

El bug: el detector asume que candles[-1] es la vela EN FORMACIÓN (prev1=candles[-2] = "última
cerrada"), pero desde v3.6.0 price_feed descarta la vela en formación ⇒ prev1 es la PENÚLTIMA
cerrada ⇒ exige 2 cierres y dispara una vela tarde.

Uso:
    python tools/backtest_fase2_lagfix.py --smoke                 # verifica el corrimiento (EURUSD)
    python tools/backtest_fase2_lagfix.py --variant repro --symbols EURUSD --sessions london
    python tools/backtest_fase2_lagfix.py --variant lagfix --workers 18 --low-priority
Cualquier otro argumento pasa tal cual a backtest_fase2.main().
"""
import argparse
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import tools.backtest_fase2 as f2  # noqa: E402

TECH_PATH = os.path.join(ROOT, 'src', 'analyzer', 'technical.py')

LAGFIX_EDITS = [
    ("        prev1 = candles[-2] if len(candles) >= 2 else None\n",
     "        prev1 = candles[-1] if len(candles) >= 1 else None\n"),
    ("        prev2 = candles[-3] if len(candles) >= 3 else None\n",
     "        prev2 = candles[-2] if len(candles) >= 2 else None\n"),
    ("        recent_candles = candles[-6:-1]",
     "        recent_candles = candles[-5:]"),
    ("            consol_candles = candles[-8:-2]\n",
     "            consol_candles = candles[-7:-1]\n"),
]

# Checkpoints separados: nunca mezclar con los v1 del 18-ago.
LOGIC_BY_VARIANT = {'lagfix': 'lagfix1', 'repro': 'repro1'}
ENV_KEY = 'AIDAN_F2B_VARIANT'


def build_lagfix_source(src):
    for old, new in LAGFIX_EDITS:
        n = src.count(old)
        if n != 1:
            raise RuntimeError(f"LAGFIX: el reemplazo matchea {n} veces (tiene que ser 1): {old.strip()!r}"
                               " — technical.py cambió; revisar antes de medir")
        src = src.replace(old, new)
    return src


def load_lagfix_module():
    """Devuelve un módulo con el technical.py corregido, SIN registrarlo."""
    with open(TECH_PATH, encoding='utf-8') as fh:
        src = build_lagfix_source(fh.read())
    mod = types.ModuleType('src.analyzer.technical')
    mod.__file__ = TECH_PATH
    mod.__package__ = 'src.analyzer'
    exec(compile(src, TECH_PATH + '[lagfix]', 'exec'), mod.__dict__)
    return mod


def install_lagfix():
    """Registra el módulo corregido como src.analyzer.technical (solo en ESTE proceso)."""
    import src.analyzer as _pkg
    mod = load_lagfix_module()
    sys.modules['src.analyzer.technical'] = mod
    setattr(_pkg, 'technical', mod)
    return mod


def run_job_variant(job):
    """Wrapper para los workers (spawn en Windows: re-importan todo, por eso el env var)."""
    variant = os.environ.get(ENV_KEY, 'repro')
    f2.LOGIC_VERSION = LOGIC_BY_VARIANT[variant]
    if variant == 'lagfix' and not getattr(sys.modules.get('src.analyzer.technical'), '_F2B_LAGFIX', False):
        install_lagfix()._F2B_LAGFIX = True
    return f2.run_job(job)


def smoke(n_candles=20000):
    """Corre original y lagfix sobre las mismas velas EURUSD M15 y compara cuándo disparan.

    Esperado si el diagnóstico es correcto: la mayoría de las rupturas que dispara el original en
    la vela i, el lagfix las dispara en la vela i-1 (sobre el mismo nivel y dirección).
    """
    import logging
    from copy import deepcopy
    from unittest.mock import patch
    import src.analyzer.technical as orig_mod
    lag_mod = load_lagfix_module()
    cache_dir = os.path.join(ROOT, '.cache_fase2', 'M15_500000')
    candles, spec = f2.load_symbol('EURUSD', cache_dir)
    candles = candles[-n_candles:]
    params, _ = f2.load_live_params(logging.getLogger('x'))
    fixed = dict(f2.SESSIONS['london'])

    def scan(mod):
        logging.disable(logging.CRITICAL)
        import src.common.db as dbm
        snap = dbm.get_setup_win_rates()

        class _T:
            def __init__(self, *a, **k): pass
            def get_params(self): return dict(params)
        an = mod.TechnicalAnalyzer(logging.getLogger('s'))
        an._cache_ttl = 0
        an._dedup_window_sec = f2.DEDUP_SEC['M15']
        out = {}
        with patch('src.common.db.get_setup_win_rates', lambda: snap), \
             patch('src.optimizer.auto_tuner.AutoTuner', _T), \
             patch.object(mod.TechnicalAnalyzer, 'get_session_info', staticmethod(lambda: dict(fixed))):
            for i in range(f2.WARMUP, len(candles) - 1):
                w = candles[i - f2.WARMUP + 1:i + 1]
                an._fetch_candles = lambda s=w: deepcopy(s)
                an._cache.clear()
                with patch.object(mod.time, 'time', return_value=candles[i]['time_unix']):
                    for s in an.detect_structure_signals(min_confidence=60):
                        out.setdefault(s['setup_type'], []).append((i, round(s['key_level'], 4), s['direction']))
        return out

    o, l = scan(orig_mod), scan(lag_mod)
    print(f"SMOKE EURUSD M15, {len(candles)} velas, sesión london")
    print(f"{'setup':28} {'orig':>6} {'lagfix':>6}   ruptura del original ya disparada 1 vela antes por lagfix")
    for st in sorted(set(o) | set(l)):
        a, b = o.get(st, []), l.get(st, [])
        extra = ''
        if 'break' in st and a:
            lb = {(k, d): [] for _, k, d in b}
            for i, k, d in b:
                lb[(k, d)].append(i)
            early = sum(1 for i, k, d in a if (i - 1) in lb.get((k, d), []))
            extra = f"{early}/{len(a)}"
        print(f"{st:28} {len(a):>6} {len(b):>6}   {extra}")


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--variant', choices=list(LOGIC_BY_VARIANT), default='lagfix')
    ap.add_argument('--smoke', action='store_true')
    a, rest = ap.parse_known_args()
    if a.smoke:
        smoke()
        return
    os.environ[ENV_KEY] = a.variant
    f2.LOGIC_VERSION = LOGIC_BY_VARIANT[a.variant]
    f2.run_job = run_job_variant
    if not any(x.startswith('--out') for x in rest):
        rest += ['--out', os.path.join(ROOT, 'docs', f'fase2b_{a.variant}_resultado')]
    sys.argv = [sys.argv[0]] + rest
    f2.main()


if __name__ == '__main__':
    main()
