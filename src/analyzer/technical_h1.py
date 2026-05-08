"""
Technical analyzer H1 (track C experimental, paralelo a M5+M15).

Hereda de TechnicalAnalyzer cambiando solo el timeframe de fetch.
H1 es la mejor math de comisión: 0.7p / ~30p avg win = 2% drag.
Frecuencia esperada baja: 0-2 trades/día.

Profile H1 (constante en este módulo): SL=40p TP=100p expiry=180min.
ATR-14 en H1 es naturalmente ~5-8x el M5, así que los clamps internos
se autoescalan vía compute_adaptive_sl_tp.

Plan dual-track (ahora triple) decidido 8 May 2026 (ver CLAUDE.md).
Track A=M5, Track B=M15, Track C=H1. Cada uno con stats separadas.
"""
from src.analyzer.technical import TechnicalAnalyzer


# Profile recomendado para H1.
# H1 candles tienen 12-30p de range típico. SL/TP escalan ~3x el M15.
H1_PROFILE = {
    'stop_loss_pips': 40,
    'take_profit_pips': 100,
    'expiry_minutes': 180,       # 3h - ventana razonable para H1 setup
    'min_confidence': 60,
    'direction': 'any',
    'name': 'H1-experimental-v1',
}


class TechnicalAnalyzerH1(TechnicalAnalyzer):
    """H1 timeframe analyzer. Override mínimo: solo el fetch de candles."""

    def __init__(self, logger):
        super().__init__(logger)
        self.timeframe_label = 'H1'
        # Cache TTL alto: H1 candles cambian cada hora
        self._cache_ttl = 60  # vs 5s default M5, 30s M15

    def _fetch_candles(self):
        """Fetch 1-hour candles from best available source."""
        from src.common.price_feed import fetch_candles, get_last_source
        candles = fetch_candles(interval='1h', count=100, logger=self.logger)
        if candles:
            self.logger.info(f"Technical H1: {len(candles)} candles via {get_last_source()}")
        return candles
