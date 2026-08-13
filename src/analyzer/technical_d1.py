"""
Technical analyzer D1 (track D, SHADOW) — swing diario.

Hereda de TechnicalAnalyzer cambiando SOLO el timeframe de fetch, igual que
M15 (v3.19.0) y H1 (v3.20.0).

═══ POR QUE EXISTE ═══════════════════════════════════════════════════════════

Medido el 13-ago-2026 con tools/backtest_h4_d1.py sobre 2000 velas D1 de MT5
(242 señales, 7,3 años: 2019 -> 2026):

    PF neto de comision   1,40
    pips por trade        +16,3
    años positivos        7 de 8
    sin los 10 mejores    sigue +6,8/trade
    sensibilidad          19 de 19 combinaciones (R:R, hold, SL) positivas

Lo ultimo es lo que sostiene la decision: no hay un pico angosto rodeado de
negativos, que es la firma del overfit (comparar con el TP de h1 refutado el
8-ago: 8p +21,3 / 10p +30,8 / 12p +8,8).

La causa mecanica es la comision: 0,8 pips sobre un movimiento medio de ~100p
es 0,8% de drag, contra ~17% en M5.

═══ POR QUE ARRANCA EN SHADOW ════════════════════════════════════════════════

1. El SWAP se come un cuarto del edge (-0,82 pips por noche comprado, hold
   medio 8 dias = 864 pips de 3.956). Con swap el bootstrap da
   CI95 [-0,53, +26,9] => CRUZA CERO => no pasa el gate de la casa.
2. La cuenta es demasiado chica: SL medio 82p => lote = riesgo$/(SL*10) =
   6,39/820 = 0,0078, por DEBAJO del minimo de 0,01. El piso obliga a
   arriesgar 1,29% en vez de 1% (hasta 3,41% con SL de 218p). El sizing
   deja de funcionar.
3. Un backtest infla 20-30%. La medicion limpia se hace clasificando EN EL
   MOMENTO, no reconstruyendo.

Por eso este track LOGUEA y NO OPERA. Ver d1_shadow_log + tools/score_d1_shadow.py.

═══ DETALLE QUE IMPORTA: LAS CONSTANTES NO SE ESCALAN ════════════════════════

El backtest probo las dos variantes. Escalar las constantes en pips por
ATR_D1/ATR_M5 (x35,8) EMPEORA fuerte: PF 1,40 -> 1,02, avg +16,3 -> +0,8.
Las ventanas chicas (breakout_dist_max 7-15p) no disparan "fuera de fase" en
D1: actuan como filtro de selectividad (242 señales en 7 años vs 1471).

Esto CONTRADICE la hipotesis del brain-review del 15-jun ("las constantes en
pips de M5 heredadas por los otros tracks disparan fuera de fase") para el
caso D1. No se toca ni una constante.

═══ FUENTE DE VELAS ══════════════════════════════════════════════════════════

Se pide interval='1d', que es la clave que entiende MT5 (price_feed.py:117) y
que ademas DESCARTA la vela en formacion (price_feed.py:142-144) => candles[-1]
es la ultima vela CERRADA. Eso reproduce exactamente el backtest, donde la
entrada es al close de la vela i con la i-1 como confirmacion.

OJO: el resto de las fuentes (Yahoo/FXCM/TwelveData) usan la clave '1day', no
'1d'. Por eso este track EXIGE MT5 y no acepta fallback: las velas diarias de
Yahoo son de EURUSD=X (otro instrumento, otro OHLC) y ademas no descartan la
vela en formacion => medirian otra cosa que la que se backtesteo.
"""
from src.analyzer.technical import TechnicalAnalyzer


# Profile D1. Los pips fijos son el nominal; compute_adaptive_sl_tp los
# reescala por ATR igual que en los otros tracks.
# Base medida: ATR-14 mediano de D1 = 71,6p. SL = 1,5xATR ~ 107p, R:R 2.
# En el barrido de sensibilidad 1,5xATR dio +16,4p/trade (1,2x dio +12,8).
D1_PROFILE = {
    'stop_loss_pips': 110,
    'take_profit_pips': 220,
    'expiry_minutes': 14400,      # 10 dias de mercado (10 velas D1)
    'min_confidence': 60,
    'direction': 'any',
    'name': 'D1-shadow-v1',
}

# Intervalo pedido al feed. Es la clave de MT5 (ver docstring).
D1_INTERVAL = '1d'


class TechnicalAnalyzerD1(TechnicalAnalyzer):
    """D1 timeframe analyzer. Override minimo: solo el fetch de candles."""

    def __init__(self, logger):
        super().__init__(logger)
        self.timeframe_label = 'D1'
        # La vela D1 cambia 1 vez por dia: no tiene sentido re-fetchear seguido.
        self._cache_ttl = 300           # vs 5s M5, 30s M15, 60s H1
        # Dedup 2 dias: un mismo nivel diario no debe re-disparar al dia
        # siguiente por un par de pips.
        self._dedup_window_sec = 172800

    def _fetch_candles(self):
        """Fetch daily candles. SOLO MT5 — sin fallback, a proposito.

        Devuelve None si lo que llego no son velas diarias del broker. El caller
        debe tratar None como "no escanear este ciclo", NO como "no hay señal":
        son cosas distintas y confundirlas es como murieron M15 y SMC.

        Valida la DATA, no la etiqueta. get_last_source() es un global de modulo
        (price_feed.py:_last_source_used) compartido por todos los tracks Y por
        el thread del dashboard, que tambien llama a fetch_candles
        (src/admin/main.py:1380 y :1971). O sea que entre nuestro fetch y la
        lectura de la etiqueta, otro thread puede pisarla. El caso peligroso no
        es el falso negativo (perder un scan, se reintenta en 15min) sino el
        falso POSITIVO: que otro track deje 'mt5' en el global justo cuando lo
        nuestro cayo a Yahoo, y terminemos midiendo velas de 5 MINUTOS de otro
        instrumento (EURUSD=X) creyendo que son diarias. Por eso la etiqueta es
        solo un filtro barato y la autoridad es el ESPACIADO REAL de las velas.
        """
        from src.common.price_feed import fetch_candles, get_last_source
        candles = fetch_candles(interval=D1_INTERVAL, count=100,
                                logger=self.logger)
        if not candles or len(candles) < 30:
            return None

        src = get_last_source()
        if src != 'mt5':
            self.logger.warning(
                f"Technical D1: fuente '{src}' != mt5 -> se descarta el fetch "
                f"(el track D1 exige velas del broker). Sin scan este ciclo.")
            return None

        if not self._son_velas_diarias(candles):
            return None

        self.logger.info(f"Technical D1: {len(candles)} candles via {src}")
        return candles

    def _son_velas_diarias(self, candles):
        """True solo si el espaciado real entre velas es de ~1 dia.

        Discrimina sin depender de ninguna etiqueta: velas M5 espacian 300s,
        H1 3600s, D1 86400s (y 259200s cruzando el fin de semana, por eso se
        usa la MEDIANA y no el promedio). Tambien exige que el campo datetime
        sea ISO parseable, que es el formato que escribe el path de MT5
        (price_feed.py:153); Yahoo escribe el epoch crudo como string.
        """
        from datetime import datetime as _dt
        import statistics as _st
        try:
            ts = [_dt.fromisoformat(c['datetime']).timestamp()
                  for c in candles[-20:]]
        except (ValueError, TypeError, KeyError) as e:
            self.logger.warning(
                f"Technical D1: el campo datetime no es ISO ({e}) -> no son "
                f"velas del path MT5. Sin scan este ciclo.")
            return False

        gaps = [b - a for a, b in zip(ts, ts[1:]) if b > a]
        if not gaps:
            self.logger.warning("Technical D1: velas sin orden temporal, skip")
            return False

        mediana = _st.median(gaps)
        if not (80000 <= mediana <= 90000):
            self.logger.warning(
                f"Technical D1: espaciado mediano {mediana:.0f}s != ~86400s "
                f"=> NO son velas diarias (¿fallback a otro timeframe?). "
                f"Sin scan este ciclo.")
            return False
        return True
