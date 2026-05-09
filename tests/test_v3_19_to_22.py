"""
Tests para componentes v3.19.0-v3.22.0:
- GPU monitor (src/common/gpu_monitor.py)
- TechnicalAnalyzer M15/H1 (src/analyzer/technical_m15.py, technical_h1.py)
- get_strategy_performance_by_track (UNION auto_strategies + trade_archive)
- Pretrade audit framework (src/analyzer/llm_auditor.py)

Uso: pytest tests/test_v3_19_to_22.py -v
"""
import json
import os
import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest


# ── GPU Monitor ──


class TestGpuMonitor:
    def test_get_gpu_state_returns_dict_with_required_keys(self):
        from src.common import gpu_monitor
        state = gpu_monitor.get_gpu_state(force_refresh=True)
        required = {'pause_llm', 'gpu_util', 'gpu_mem_used_mb', 'gpu_mem_total_mb', 'available', 'reason'}
        assert required.issubset(state.keys())

    def test_should_pause_llm_returns_bool(self):
        from src.common.gpu_monitor import should_pause_llm
        result = should_pause_llm()
        assert isinstance(result, bool)

    def test_get_status_summary_string(self):
        from src.common.gpu_monitor import get_status_summary
        s = get_status_summary()
        assert isinstance(s, str)
        assert len(s) > 0

    def test_pause_threshold_logic(self):
        """Si util>50 AND mem>11GB -> pause. Caso opuesto -> no pause."""
        from src.common import gpu_monitor

        # Patch subprocess.run to simulate "GPU busy"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "80, 12500, 16303"
        with patch('src.common.gpu_monitor.subprocess.run', return_value=mock_result):
            # Force refresh
            state = gpu_monitor.get_gpu_state(force_refresh=True)
            assert state['pause_llm'] == True
            assert state['gpu_util'] == 80

        # Simulate "GPU idle"
        mock_result.stdout = "10, 3000, 16303"
        with patch('src.common.gpu_monitor.subprocess.run', return_value=mock_result):
            state = gpu_monitor.get_gpu_state(force_refresh=True)
            assert state['pause_llm'] == False
            assert state['gpu_util'] == 10


# ── Technical M15/H1 profiles ──


class TestTechnicalM15:
    def test_m15_profile_has_required_keys(self):
        from src.analyzer.technical_m15 import M15_PROFILE
        required = {'stop_loss_pips', 'take_profit_pips', 'expiry_minutes', 'min_confidence', 'name'}
        assert required.issubset(M15_PROFILE.keys())

    def test_m15_profile_values_reasonable(self):
        from src.analyzer.technical_m15 import M15_PROFILE
        # M15 SL/TP debe ser ~3x M5 (M5 default era 5/25)
        assert 10 <= M15_PROFILE['stop_loss_pips'] <= 25
        assert 30 <= M15_PROFILE['take_profit_pips'] <= 80
        # Expiry debe ser >= 30min
        assert M15_PROFILE['expiry_minutes'] >= 30

    def test_m15_class_inherits_technical(self):
        from src.analyzer.technical_m15 import TechnicalAnalyzerM15
        from src.analyzer.technical import TechnicalAnalyzer
        assert issubclass(TechnicalAnalyzerM15, TechnicalAnalyzer)

    def test_m15_overrides_fetch_candles(self, mock_logger):
        """Verifica que _fetch_candles usa interval='15min'."""
        from src.analyzer.technical_m15 import TechnicalAnalyzerM15
        analyzer = TechnicalAnalyzerM15(mock_logger)
        # Patch the price_feed call
        with patch('src.common.price_feed.fetch_candles') as mock_fetch:
            mock_fetch.return_value = [{'open': 1.17, 'high': 1.18, 'low': 1.16, 'close': 1.17, 'datetime': '2026-05-08'}]
            analyzer._fetch_candles()
            # Verify called with interval='15min'
            args, kwargs = mock_fetch.call_args
            assert kwargs.get('interval') == '15min'


class TestTechnicalH1:
    def test_h1_profile_has_required_keys(self):
        from src.analyzer.technical_h1 import H1_PROFILE
        required = {'stop_loss_pips', 'take_profit_pips', 'expiry_minutes', 'min_confidence', 'name'}
        assert required.issubset(H1_PROFILE.keys())

    def test_h1_profile_larger_than_m15(self):
        from src.analyzer.technical_m15 import M15_PROFILE
        from src.analyzer.technical_h1 import H1_PROFILE
        # H1 SL/TP/expiry debe ser >= M15
        assert H1_PROFILE['stop_loss_pips'] > M15_PROFILE['stop_loss_pips']
        assert H1_PROFILE['take_profit_pips'] > M15_PROFILE['take_profit_pips']
        assert H1_PROFILE['expiry_minutes'] > M15_PROFILE['expiry_minutes']

    def test_h1_class_inherits_technical(self):
        from src.analyzer.technical_h1 import TechnicalAnalyzerH1
        from src.analyzer.technical import TechnicalAnalyzer
        assert issubclass(TechnicalAnalyzerH1, TechnicalAnalyzer)

    def test_h1_overrides_fetch_candles_to_1h(self, mock_logger):
        from src.analyzer.technical_h1 import TechnicalAnalyzerH1
        analyzer = TechnicalAnalyzerH1(mock_logger)
        with patch('src.common.price_feed.fetch_candles') as mock_fetch:
            mock_fetch.return_value = [{'open': 1.17, 'high': 1.18, 'low': 1.16, 'close': 1.17, 'datetime': '2026-05-08'}]
            analyzer._fetch_candles()
            args, kwargs = mock_fetch.call_args
            assert kwargs.get('interval') == '1h'


# ── Strategy performance by track ──


class TestStrategyPerformanceByTrack:
    def test_returns_three_tracks(self):
        from src.common.db import get_strategy_performance_by_track
        result = get_strategy_performance_by_track()
        assert 'track_a_m5' in result
        assert 'track_b_m15' in result
        assert 'track_c_h1' in result

    def test_each_track_has_required_metrics(self):
        from src.common.db import get_strategy_performance_by_track
        result = get_strategy_performance_by_track()
        for track in ['track_a_m5', 'track_b_m15', 'track_c_h1']:
            t = result[track]
            for key in ['total', 'wins', 'losses', 'win_rate', 'sum_pnl', 'profit_factor']:
                assert key in t, f"Missing {key} in {track}"

    def test_pf_special_values(self):
        """PF = 999 cuando hay wins sin losses (infinito)."""
        from src.common.db import get_strategy_performance_by_track
        result = get_strategy_performance_by_track()
        for track in ['track_a_m5', 'track_b_m15', 'track_c_h1']:
            t = result[track]
            # PF >= 0 always
            assert t['profit_factor'] >= 0
            # Si total=0 -> PF=0
            if t['total'] == 0:
                assert t['profit_factor'] == 0


# ── Pretrade Audit ──


class TestPretradeAudit:
    def test_pretrade_audits_table_creates(self):
        from src.analyzer.llm_auditor import _ensure_pretrade_audits_table
        from src.common.db import DB_PATH
        _ensure_pretrade_audits_table()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pretrade_audits'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None, "Tabla pretrade_audits no fue creada"

    def test_pretrade_strict_returns_none_on_gpu_busy(self):
        """Verifica skip si GPU pause flag activado."""
        from src.analyzer import llm_auditor
        signal_context = {
            'direction': 'CALL', 'price': 1.17, 'trend': 'bullish',
            'htf_bias': 'bullish', 'rsi': 60, 'momentum': 'up',
            'volatility': 'normal', 'atr': 5.0, 'confidence': 70,
            'sl_pips': 5, 'tp_pips': 10, 'rr': '1:2',
        }
        with patch('src.common.gpu_monitor.should_pause_llm', return_value=True):
            result = llm_auditor.audit_pretrade_strict(signal_context)
            assert result is None  # debe skipear si GPU busy

    def test_pretrade_strict_validates_input_safely(self):
        """No crashea con inputs vacíos."""
        from src.analyzer.llm_auditor import audit_pretrade_strict
        # Empty context shouldn't crash
        try:
            result = audit_pretrade_strict({})
            # Either None (no Ollama) or dict
            assert result is None or isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"audit_pretrade_strict crashed on empty input: {e}")


# ── Imports sanity (regression check) ──


class TestImportsRegression:
    """Verifica que módulos críticos importan sin errores. Detecta breaking refactors."""

    def test_config_imports(self):
        from src.common.config import Config
        assert Config.VERSION  # debe tener versión

    def test_technical_m15_imports(self):
        from src.analyzer.technical_m15 import TechnicalAnalyzerM15, M15_PROFILE
        assert TechnicalAnalyzerM15 and M15_PROFILE

    def test_technical_h1_imports(self):
        from src.analyzer.technical_h1 import TechnicalAnalyzerH1, H1_PROFILE
        assert TechnicalAnalyzerH1 and H1_PROFILE

    def test_gpu_monitor_imports(self):
        from src.common.gpu_monitor import should_pause_llm, get_gpu_state, get_status_summary
        assert callable(should_pause_llm)
        assert callable(get_gpu_state)
        assert callable(get_status_summary)

    def test_llm_auditor_imports(self):
        from src.analyzer.llm_auditor import audit_signal, audit_pretrade_strict, log_pretrade_audit
        assert callable(audit_signal)
        assert callable(audit_pretrade_strict)
        assert callable(log_pretrade_audit)

    def test_post_trade_analyzer_imports(self):
        from src.analyzer.post_trade_analyzer import analyze_closed_trade, POST_TRADE_MODEL
        assert callable(analyze_closed_trade)
        assert POST_TRADE_MODEL  # debe tener modelo default

    def test_db_get_strategy_performance_by_track_imports(self):
        from src.common.db import get_strategy_performance_by_track
        assert callable(get_strategy_performance_by_track)
