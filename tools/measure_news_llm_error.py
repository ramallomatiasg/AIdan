# -*- coding: utf-8 -*-
"""
measure_news_llm_error.py — RETRO read-only. ¿Cuánto se equivoca el LLM de news?

Mide la CALIDAD DEL JUICIO DIRECCIONAL del LLM de news, AISLADA de la capa de trading
(SL/TP/comisión/expiry). El track de news pierde plata (n~34, 12% WR) pero eso mezcla el
error del LLM con la ejecución. Acá medimos la habilidad cruda: dada una alerta CALL/PUT,
¿el precio se movió en esa dirección?, y sobre todo ¿el LLM DISCRIMINA (CALL vs PUT) mejor
que el azar?

Diseñado por workflow (3 diseños + verificación adversarial, 24-jul). Reglas clave:
  - Fuente = tabla `alerts` (no trades) -> la capa de trading nunca entra.
  - Entry = `price_at_alert` (snapshot en t0, NO lookahead). Se usa además para ANCLAR la
    alerta a su vela (el precio cae dentro del rango de la vela) -> resuelve el offset de
    servidor MT5 / DST por fila, sin adivinar timezone.
  - Exit = precio a t0+H (net move), con velas M5 REALES (sin re-simular SL/TP — eso invirtió
    la realidad en el caso bounce). Horizonte pre-registrado H=30min (news es rápido).
  - EL CONFOUND ASESINO = base-rate. En abr-jul el EUR/USD CAYÓ (crash de 160p) -> "PUT gana"
    puede ser SOLO el mercado bajando. Por eso:
      * el titular es la DISCRIMINACIÓN P(subió|CALL) - P(subió|PUT) (Fisher), inmune al drift;
      * el hit por dirección se compara contra el base-rate del PERÍODO (verify_finding con
        baseline = base-rate medido), NUNCA contra 50%. direction='auto' delata ANTI-SKILL.
  - Dedup por título; corte por mes (contaminación de versión del prompt), categoría
    (datos-duros vs tono = test de la hipótesis "el LLM lee tono no impacto"), confianza.

READ-ONLY (solo SELECT). Requiere MT5 para las velas forward (attachea al terminal; correr
como UN proceso, no en paralelo con barridos pesados). Env:
  NEWS_HORIZONS=15,30,60  NEWS_PRIMARY_H=30  NEWS_DEADBAND_PIPS=2  NEWS_DEDUP_MIN=30
  NEWS_TZ_TOL_PIPS=8  NEWS_SINCE=YYYY-MM-DD
"""
import os
import sys
import time
import math
import calendar
import sqlite3
from datetime import datetime, timedelta
from bisect import bisect_right
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.optimizer.significance import verify_finding  # noqa: E402

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
SYMBOL = 'EURUSD'
PIP = 0.0001

HORIZONS = [int(x) for x in os.getenv('NEWS_HORIZONS', '15,30,60').split(',')]
PRIMARY_H = int(os.getenv('NEWS_PRIMARY_H', '30'))
DEADBAND = float(os.getenv('NEWS_DEADBAND_PIPS', '2'))       # pips; move < deadband = flat
DEDUP_MIN = float(os.getenv('NEWS_DEDUP_MIN', '30'))
TZ_TOL = float(os.getenv('NEWS_TZ_TOL_PIPS', '8'))           # max mismatch precio<->vela para anclar
COMMISSION_PIPS = 1.3
FAV_MIN = 5.0
SINCE = os.getenv('NEWS_SINCE', '')
if PRIMARY_H not in HORIZONS:
    HORIZONS.append(PRIMARY_H)
HORIZONS = sorted(set(HORIZONS))

# ── Clasificador de categorías (copiado VERBATIM de AIdan_TodoEnUno.py:59-78 —
#    no importar el monolito: spawnea GUI/threads y rompe el read-only single-process) ──
_NEWS_CATEGORIES = {
    'fed_rate': ['fed ', 'federal reserve', 'fomc', 'interest rate', 'rate decision', 'rate hike', 'rate cut', 'powell', 'tasa de interés'],
    'employment': ['nonfarm', 'non-farm', 'payroll', 'unemployment', 'jobless', 'jobs report', 'employment', 'hiring', 'empleo', 'desempleo'],
    'inflation': ['cpi', 'ppi', 'pce', 'inflation', 'consumer price', 'producer price', 'core price', 'inflación'],
    'gdp_growth': ['gdp', 'gross domestic', 'economic growth', 'pib', 'crecimiento'],
    'central_bank': ['ecb', 'boe', 'boj', 'central bank', 'lagarde', 'banco central', 'monetary policy'],
    'geopolitical': ['war', 'tariff', 'sanction', 'trade war', 'ceasefire', 'conflict', 'guerra', 'arancel'],
    'oil_energy': ['oil', 'crude', 'opec', 'energy', 'petróleo', 'gas natural'],
    'market_sentiment': ['rally', 'crash', 'sell-off', 'selloff', 'risk-on', 'risk-off', 'volatility', 'vix', 'futures'],
}
# Super-grupos para la hipótesis tono!=impacto:
HARD_DATA = {'inflation', 'employment', 'gdp_growth'}   # release con actual-vs-forecast (dato duro)
TONE = {'fed_rate', 'central_bank'}                     # discurso / tono de banquero central


def classify(title):
    if not title:
        return 'other'
    t = title.lower()
    for cat, kws in _NEWS_CATEGORIES.items():
        if any(kw in t for kw in kws):
            return cat
    return 'other'


def supergroup(cat):
    if cat in HARD_DATA:
        return 'HARD_DATA'
    if cat in TONE:
        return 'TONE'
    return 'MACRO_OTHER'


def parse_ar(s):
    """alert_sent_at es AR-naive 'YYYY-MM-DD HH:MM:SS[.ffffff]'."""
    try:
        return datetime.strptime(str(s).split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def wr(n, w):
    return (100.0 * w / n) if n else 0.0


def main():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print('MetaTrader5 no disponible — este diagnóstico REQUIERE velas MT5.'); return
    if not mt5.initialize():
        print(f'No pude attachear a MT5: {mt5.last_error()}'); return
    try:
        tick = mt5.symbol_info_tick(SYMBOL)
        srv_now = round((tick.time - time.time()) / 1800.0) * 1800 if tick else 0

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        q = ("SELECT a.id, a.direction, a.confidence, a.impact_score, a.should_operate, "
             "a.alert_sent_at, a.price_at_alert, a.alert_result AS stored_result, "
             "n.title FROM alerts a LEFT JOIN news n ON a.news_id=n.id "
             "WHERE a.direction IN ('CALL','PUT') AND a.alert_sent_at IS NOT NULL")
        args = []
        if SINCE:
            q += " AND a.alert_sent_at >= ?"; args.append(SINCE)
        q += " ORDER BY a.alert_sent_at ASC"
        raw = conn.execute(q, args).fetchall()

        # ── Dedup por título (direction-agnostic), quedarse con el más viejo del cluster ──
        kept, contradiction = [], 0
        last_by_title = {}   # norm_title -> (dt, direction)
        for r in raw:
            dt = parse_ar(r['alert_sent_at'])
            if dt is None:
                continue
            key = ' '.join((r['title'] or f"__id{r['id']}").lower().split())
            prev = last_by_title.get(key)
            if prev and (dt - prev[0]).total_seconds() <= DEDUP_MIN * 60:
                if prev[1] != r['direction']:
                    contradiction += 1
                continue  # duplicado del mismo título dentro de la ventana
            last_by_title[key] = (dt, r['direction'])
            kept.append((r, dt))

        # ── Pull de velas M5 de TODO el período de una sola vez (1 call pesado, 1 proceso) ──
        t0s_utc = [calendar.timegm((dt + timedelta(hours=3)).timetuple()) for _, dt in kept]
        lo = datetime.utcfromtimestamp(min(t0s_utc) + srv_now) - timedelta(days=2)
        hi = datetime.utcfromtimestamp(max(t0s_utc) + srv_now) + timedelta(minutes=max(HORIZONS)) + timedelta(days=2)
        bars = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, lo, hi)
        if bars is None or len(bars) == 0:
            print('MT5 no devolvió velas para el rango.'); return
        opens = [int(b['time']) for b in bars]   # epoch de OPEN en eje servidor
        n_bars = len(bars)

        # ── Anclaje TZ por fila: elegir el offset (srv_now, ±3600 = ambigüedad DST) cuya vela
        #    en t0 contiene price_at_alert. Resuelve DST/cutover sin adivinar timezone. ──
        OFFS = [srv_now, srv_now - 3600, srv_now + 3600]
        off_votes = defaultdict(int)

        def anchor(t0_utc, price):
            """Devuelve idx de la vela que contiene t0, o None si no reconcilia con el precio."""
            best = None
            for off in OFFS:
                axis = t0_utc + off
                i = bisect_right(opens, axis) - 1
                if i < 0 or i >= n_bars:
                    continue
                b = bars[i]
                if opens[i] <= axis < opens[i] + 300:
                    lo_p, hi_p = b['low'] - TZ_TOL * PIP, b['high'] + TZ_TOL * PIP
                    if lo_p <= price <= hi_p:
                        mism = abs(price - b['open'])
                        if best is None or mism < best[0]:
                            best = (mism, i, off)
            return best

        rows = []   # dicts con métricas por alerta anclada+madura
        drops = defaultdict(int)
        for (r, dt) in kept:
            price = r['price_at_alert'] or 0
            if price <= 0:
                drops['no_price'] += 1
                continue
            t0_utc = calendar.timegm((dt + timedelta(hours=3)).timetuple())
            a = anchor(t0_utc, price)
            if a is None:
                drops['tz_unreconciled'] += 1
                continue
            _, i0, off = a
            off_votes[off] += 1
            axis = t0_utc + off
            direction = r['direction']

            # Net move + excursión por horizonte
            per_h = {}
            matured_primary = False
            for H in HORIZONS:
                j = bisect_right(opens, axis + H * 60) - 1
                if j <= i0 or j >= n_bars - 1:     # exit no existe o es la última vela = no maduro
                    continue
                ph = bars[j]['close']
                mkt = (ph - price) / PIP                      # move direction-agnostic (pips)
                signed = mkt if direction == 'CALL' else -mkt  # en el marco del LLM
                win = bars[i0 + 1:j + 1]                        # excursión estricta post-t0
                if len(win):
                    hh = max(b['high'] for b in win); ll = min(b['low'] for b in win)
                    if direction == 'CALL':
                        fav, adv = (hh - price) / PIP, (price - ll) / PIP
                    else:
                        fav, adv = (price - ll) / PIP, (hh - price) / PIP
                else:
                    fav = adv = 0.0
                per_h[H] = {'mkt': mkt, 'signed': signed, 'fav': fav, 'adv': adv}
                if H == PRIMARY_H:
                    matured_primary = True
            if not matured_primary:
                drops['not_matured'] += 1
                continue

            # Pre-move (¿ya estaba en precio? = LLM describe, no predice). 15min ANTES (solo pasado).
            ip = bisect_right(opens, axis - 15 * 60) - 1
            pre_fav = None
            if 0 <= ip < n_bars:
                ps = bars[ip]['open']
                pre_fav = ((price - ps) if direction == 'CALL' else (ps - price)) / PIP

            rows.append({
                'dir': direction, 'conf': r['confidence'] or 0, 'impact': r['impact_score'] or 0,
                'should_op': r['should_operate'], 'month': dt.strftime('%Y-%m'),
                'cat': classify(r['title']), 'stored': r['stored_result'],
                'per_h': per_h, 'pre_fav': pre_fav,
            })

        # ══════════════ AGREGADO ══════════════
        print('=' * 78)
        print('  NEWS LLM — CALIDAD DEL JUICIO DIRECCIONAL  (measure_news_llm_error.py)')
        print('=' * 78)
        print(f'  Horizonte titular H={PRIMARY_H}min | deadband={DEADBAND}p | dedup={DEDUP_MIN:.0f}min '
              f'| entry=price_at_alert | src=MT5')
        print(f'  srv_off votos (anclaje TZ por fila): '
              + ' '.join(f'{o:+d}s:{c}' for o, c in sorted(off_votes.items())))
        print(f'\n[0] MUESTRA:  raw {len(raw)} -> dedup {len(kept)} (contradicciones intra-cluster {contradiction})'
              f' -> anclado+maduro@H{PRIMARY_H} {len(rows)}')
        print('    drops: ' + ' '.join(f'{k}={v}' for k, v in sorted(drops.items())) or '    drops: 0')

        def cell(subset, H):
            """(n_decisive, hits, ups, downs) para un subset y horizonte."""
            n = h = up = dn = 0
            for x in subset:
                d = x['per_h'].get(H)
                if not d:
                    continue
                s, m = d['signed'], d['mkt']
                if abs(m) < DEADBAND:      # ventana 'flat' -> no decisiva
                    continue
                n += 1
                if m >= DEADBAND:
                    up += 1
                else:
                    dn += 1
                if s >= DEADBAND:
                    h += 1
            return n, h, up, dn

        H = PRIMARY_H
        calls = [x for x in rows if x['dir'] == 'CALL']
        puts = [x for x in rows if x['dir'] == 'PUT']

        # Base-rate ambiente (todas las ventanas direccionales decisivas, pooled)
        n_all, hit_all, up_all, dn_all = cell(rows, H)
        p_up = up_all / n_all if n_all else 0
        p_dn = dn_all / n_all if n_all else 0
        best_const = max(p_up, p_dn)
        print(f'\n[1] BASE-RATE AMBIENTE @H{H} (ventanas decisivas, n={n_all}): '
              f'subió {p_up*100:.0f}% / bajó {p_dn*100:.0f}%  -> "mejor regla constante" = {best_const*100:.0f}%')
        print('    (En este período el mercado tuvo drift; "siempre la dirección dominante" es la vara a batir.)')

        # ── [2] TITULAR: DISCRIMINACIÓN P(subió|CALL) - P(subió|PUT) (inmune al drift) ──
        nc, _, cu, cd = cell(calls, H)
        npu, _, pu, pd = cell(puts, H)
        print(f'\n[2] *** TITULAR — DISCRIMINACIÓN (CALL vs PUT, inmune al drift) @H{H} ***')
        if nc and npu:
            p_up_call = cu / nc
            p_up_put = pu / npu
            edge_pp = (p_up_call - p_up_put) * 100
            fisher_p = None
            try:
                from scipy.stats import fisher_exact
                _, fisher_p = fisher_exact([[cu, cd], [pu, pd]], alternative='two-sided')
            except Exception:
                pass
            print(f'    CALL: n={nc}  P(subió|CALL)={p_up_call*100:.0f}%')
            print(f'    PUT : n={npu}  P(subió|PUT )={p_up_put*100:.0f}%')
            fp = f'{fisher_p:.4f}' if fisher_p is not None else 'n/a'
            verdict = ('SIN SKILL (n<25 por lado)' if min(nc, npu) < 25 else
                       ('SKILL' if (fisher_p is not None and fisher_p < 0.05 and edge_pp > 0) else
                        ('ANTI-SKILL (discrimina AL REVÉS)' if (fisher_p is not None and fisher_p < 0.05 and edge_pp < 0)
                         else 'RUIDO (no distinguible del azar)')))
            print(f'    edge = {edge_pp:+.0f} puntos  (Fisher p={fp})  -> {verdict}')
            print(f'    (Lit.: la diferencia tono-vs-impacto vale ~25pp. edge~0 => el LLM NO discrimina.)')
        else:
            print('    n insuficiente en algún lado.')

        # ── [3] ¿Le gana a la mejor regla constante? (delata ANTI-SKILL vs el drift) ──
        print(f'\n[3] ¿EL LLM LE GANA AL DRIFT? (hit direccional vs base-rate del período) @H{H}')
        if n_all >= 25 and best_const > 0:
            res = verify_finding(n_all, hit_all, baseline_wr=best_const, direction='auto')
            tag = ('LE GANA' if (res.significant and res.direction == 'better') else
                   ('ANTI-SKILL (peor que el drift)' if (res.significant and res.direction == 'worse')
                    else 'no distinguible del drift'))
            print(f'    LLM hit global={wr(n_all, hit_all):.0f}% (n={n_all}) vs mejor-constante {best_const*100:.0f}% '
                  f'-> {res.verdict} => {tag}')
        else:
            print(f'    n={n_all} insuficiente.')

        # ── [4] TONO vs IMPACTO (la hipótesis del checkpoint) ──
        print(f'\n[4] TONO vs DATO-DURO @H{H}  (hipótesis: el LLM lee tono, no impacto)')
        for grp in ('HARD_DATA', 'TONE', 'MACRO_OTHER'):
            sub = [x for x in rows if supergroup(x['cat']) == grp]
            sc = [x for x in sub if x['dir'] == 'CALL']; sp = [x for x in sub if x['dir'] == 'PUT']
            n, h, _, _ = cell(sub, H)
            gnc, _, gcu, _ = cell(sc, H); gnp, _, gpu, _ = cell(sp, H)
            edge = ((gcu / gnc - gpu / gnp) * 100) if (gnc and gnp) else None
            edge_s = f'{edge:+.0f}pp' if edge is not None else 'n/a'
            print(f'    {grp:11} n={n:>3} hit={wr(n, h):>3.0f}%  discriminación(CALLn={gnc},PUTn={gnp})={edge_s}')

        # ── [5] SEGMENTOS ──
        def seg_line(label, sub):
            n, h, up, dn = cell(sub, H)
            if n == 0:
                print(f'    {label:16} n=0'); return
            bc = max(up, dn) / n
            res = verify_finding(n, h, baseline_wr=bc, direction='auto') if n >= 25 else None
            v = res.verdict if res else 'RUIDO (n<25)'
            print(f'    {label:16} n={n:>3} hit={wr(n, h):>3.0f}% (base {bc*100:.0f}%)  {v}')

        print(f'\n[5] SEGMENTOS @H{H}  (cada uno vs SU PROPIO base-rate)')
        print('  -- por mes (contaminación de versión del prompt) --')
        for m in sorted(set(x['month'] for x in rows)):
            seg_line(m, [x for x in rows if x['month'] == m])
        print('  -- por confianza LLM --')
        for lo, hiv, lab in [(0, 59, 'conf<=59'), (59.01, 64, 'conf 60-64'), (64.01, 74, 'conf 65-74'), (74.01, 999, 'conf>=75')]:
            seg_line(lab, [x for x in rows if lo <= x['conf'] <= hiv])
        print('  -- por impact_score --')
        for lo, hiv, lab in [(0, 55, 'impact<=55'), (55.01, 70, 'impact 56-70'), (70.01, 999, 'impact>=71')]:
            seg_line(lab, [x for x in rows if lo <= x['impact'] <= hiv])
        print('  -- should_operate (DIAGNÓSTICO: es el gate de ejecución, no el juicio) --')
        seg_line('should_op=1', [x for x in rows if x['should_op']])
        seg_line('should_op=0', [x for x in rows if not x['should_op']])

        # ── [6] ¿YA ESTABA EN PRECIO? (tone-follow) ──
        right = [x for x in rows if (x['per_h'].get(H) and x['per_h'][H]['signed'] >= DEADBAND and x['pre_fav'] is not None)]
        if right:
            already = sum(1 for x in right if x['pre_fav'] >= DEADBAND)
            print(f'\n[6] YA-EN-PRECIO: de las alertas que ACERTARON la dirección, {wr(len(right), already):.0f}% '
                  f'({already}/{len(right)}) ya venían moviéndose a favor ANTES de la alerta')
            print('    (alto = el LLM describe un movimiento que ya pasó, no lo predice = tono no impacto).')

        # ── [APÉNDICE-T] Tradeabilidad (capa de trading, NO es la respuesta al juicio) ──
        pr = [x['per_h'][H] for x in rows if x['per_h'].get(H)]
        if pr:
            afav = sum(d['fav'] for d in pr) / len(pr)
            aadv = sum(d['adv'] for d in pr) / len(pr)
            anet = sum(d['signed'] for d in pr) / len(pr)
            meds = sorted(d['signed'] for d in pr)
            mednet = meds[len(meds) // 2]
            print(f'\n[APÉNDICE-T] TRADEABILIDAD @H{H} (capa de trading, indicativo — NO es el veredicto de juicio):')
            print(f'    avg_fav={afav:.1f}p  avg_adv={aadv:.1f}p  ratio={afav/aadv:.2f}  '
                  f'avg_net={anet:+.1f}p  median_net={mednet:+.1f}p  net-comisión={anet-COMMISSION_PIPS:+.1f}p')

        # ── Diagnóstico: acuerdo con la eval legacy (horizonte descontrolado, NO es verdad) ──
        both = [x for x in rows if x['stored'] in ('win', 'loss') and x['per_h'].get(H)]
        if both:
            agree = sum(1 for x in both if (x['stored'] == 'win') == (x['per_h'][H]['signed'] >= DEADBAND))
            print(f'\n[DIAG] acuerdo con la eval legacy (alert_result): {wr(len(both), agree):.0f}% (n={len(both)}) '
                  '— la legacy tiene horizonte descontrolado, es solo referencia.')

        # ── CAVEATS ──
        print('\n[CAVEATS]')
        for c in [
            'El veredicto de SKILL es la DISCRIMINACIÓN (CALL vs PUT), NO el hit crudo: en mercado que cae, "siempre PUT" ya acierta mucho.',
            'Todo es CONDICIONAL a que el LLM se comprometió (no-NEUTRAL) y AIdan estaba prendido; releases con el exe apagado no están (sesgo de selección).',
            f'Deadband fijo {DEADBAND}p (no ATR-relativo); confianza cuantizada (~7 valores); no se corrige por comparaciones múltiples -> los sub-cortes son exploratorios.',
            'La excursión (fav/adv) ignora el orden del camino (MFE/MAE) -> por eso tradeabilidad es apéndice, no P&L.',
            'TZ del servidor inferido por fila anclando price_at_alert a su vela; filas que no reconcilian se descartan (ver drops tz_unreconciled).',
            'NO dice si el track news ganaría plata (saca la capa de trading a propósito), ni POR QUÉ se equivoca (eso necesita una muestra etiquetada aparte).',
        ]:
            print(f'    - {c}')
        conn.close()
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
