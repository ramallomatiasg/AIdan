"""
Technical analyzer M15 (track B experimental, paralelo al M5).

Hereda de TechnicalAnalyzer cambiando solo el timeframe de fetch.
Los thresholds de SL/TP se autoescalan via ATR-14 (que en M15 es naturalmente
~3x más grande que en M5), así que la lógica interna no necesita cambiar.

Profile M15 (constante en este módulo) tiene SL/TP base ~3x el M5 default
para reflejar el time horizon más largo. El profile M5 default era SL 5p / TP 25p.

Plan dual-track decidido 7 May 2026 (ver CLAUDE.md). Track B: M15 corre en
paralelo al M5 (track A). Decisión final del rumbo en 30+ trades acumulados.
"""
from src.analyzer.technical import TechnicalAnalyzer


# Profile recomendado para M15. Lo usa la integración (AIdan_TodoEnUno) cuando
# llama a compute_adaptive_sl_tp con este profile.
# Filosofía: SL ~3x el M5 default (5p → 15p), TP ~3x (25p → 60p). El ATR-14
# en M15 será naturalmente ~3x más grande que en M5 para mismo mercado, así
# que los clamps internos de compute_adaptive_sl_tp escalan automáticamente.
M15_PROFILE = {
    'stop_loss_pips': 15,
    'take_profit_pips': 60,
    'expiry_minutes': 45,        # vs 15 en M5 — da tiempo a que el setup se materialice
    'min_confidence': 60,
    'direction': 'any',
    'name': 'M15-experimental-v1',
}


class TechnicalAnalyzerM15(TechnicalAnalyzer):
    """M15 timeframe analyzer. Override mínimo: solo el fetch de candles."""

    def __init__(self, logger):
        super().__init__(logger)
        self.timeframe_label = 'M15'
        # Cache TTL más alto: M15 candles cambian cada 15 min, no cada 5
        self._cache_ttl = 30  # vs 5s default

    def _fetch_candles(self):
        """Fetch 15-min candles from best available source."""
        from src.common.price_feed import fetch_candles, get_last_source
        candles = fetch_candles(interval='15min', count=100, logger=self.logger)
        if candles:
            self.logger.info(f"Technical M15: {len(candles)} candles via {get_last_source()}")
        return candles
