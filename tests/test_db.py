"""Tests for src/common/db.py — SQLite CRUD operations."""
import sqlite3
import pytest
from datetime import datetime, timedelta
from src.common.db import (
    init_db, add_news, get_unprocessed_news, mark_news_processed,
    add_alert, get_recent_alerts, get_stats, record_signal_result,
    get_performance_stats, cleanup_old_data, add_auto_strategy,
    get_active_strategies, record_strategy_result, get_strategy_performance,
    get_news_fetch_time,
)


# ── init_db ──

class TestInitDb:
    def test_creates_all_tables(self, in_memory_db):
        conn = sqlite3.connect(in_memory_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected = {"news", "alerts", "errors", "signal_results",
                    "strategies", "auto_strategies", "strategy_results"}
        assert expected.issubset(tables)

    def test_is_idempotent(self, in_memory_db):
        """Calling init_db twice should not raise."""
        init_db()  # already called by fixture; call again
        conn = sqlite3.connect(in_memory_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM news")
        assert cursor.fetchone()[0] == 0
        conn.close()


# ── add_news / get_unprocessed_news ──

class TestNewsOperations:
    def test_add_news_returns_id(self, in_memory_db):
        news_id = add_news(
            url="https://example.com/1",
            title="Fed raises rates",
            summary="The Fed raised rates by 25bps",
            language="en",
            entities="FED",
            tags="monetary_policy",
        )
        assert news_id is not None
        assert isinstance(news_id, int)

    def test_add_duplicate_url_returns_none(self, in_memory_db):
        add_news("https://dup.com", "Title", "Sum", "en", "", "")
        result = add_news("https://dup.com", "Other", "Other", "en", "", "")
        assert result is None

    def test_get_unprocessed_news_returns_new_items(self, in_memory_db):
        add_news("https://a.com", "A", "sumA", "en", "", "")
        add_news("https://b.com", "B", "sumB", "en", "", "")
        results = get_unprocessed_news()
        assert len(results) == 2

    def test_get_unprocessed_excludes_processed(self, in_memory_db):
        nid = add_news("https://c.com", "C", "sumC", "en", "", "")
        mark_news_processed(nid)
        results = get_unprocessed_news()
        assert len(results) == 0

    def test_get_news_fetch_time(self, in_memory_db):
        nid = add_news("https://ft.com", "FT", "sum", "en", "", "")
        fetch_time = get_news_fetch_time(nid)
        assert fetch_time is not None

    def test_get_news_fetch_time_missing_id(self, in_memory_db):
        assert get_news_fetch_time(99999) is None


# ── Alerts ──

class TestAlertOperations:
    def _seed_news(self, in_memory_db):
        return add_news("https://alert-test.com", "Rate cut", "ECB cuts", "en", "ECB", "monetary_policy")

    def test_add_alert(self, in_memory_db):
        nid = self._seed_news(in_memory_db)
        add_alert(nid, 85, "ALTA", "Rate cut", "EUR up", "Bullish EUR", "ollama", True, "CALL", 78.5)
        conn = sqlite3.connect(in_memory_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM alerts")
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_get_recent_alerts_returns_low_score_too(self, in_memory_db):
        """v3.48.0 — el test viejo asumia un filtro score<50 que YA NO EXISTE.

        get_recent_alerts() dice explicito en su docstring: "Get ALL alerts from
        today — no score filter, user sees everything". El cambio fue intencional
        (el dashboard muestra todo); el test se habia quedado en la version vieja.
        Verificado contra la implementacion, no es un bug.
        """
        nid = self._seed_news(in_memory_db)
        add_alert(nid, 30, "BAJA", "Low", "None", "Skip", "keywords")
        results = get_recent_alerts()
        assert len(results) == 1


# ── Stats ──

class TestStats:
    def test_get_stats_empty_db(self, in_memory_db):
        stats = get_stats()
        assert stats["total_news"] == 0
        assert stats["total_alerts"] == 0
        assert stats["news_last_hour"] == 0

    def test_get_stats_with_data(self, in_memory_db):
        add_news("https://s1.com", "S1", "sum", "en", "", "")
        add_news("https://s2.com", "S2", "sum", "en", "", "")
        stats = get_stats()
        assert stats["total_news"] == 2


# ── Signal results / performance ──

class TestPerformance:
    def test_record_and_get_performance(self, in_memory_db):
        nid = add_news("https://perf.com", "P", "s", "en", "", "")
        add_alert(nid, 80, "ALTA", "E", "I", "M", "ollama", True, "CALL", 75)
        record_signal_result(1, "win")
        record_signal_result(1, "win")  # upsert — still 1 row
        stats = get_performance_stats()
        assert stats["wins"] == 1
        assert stats["win_rate"] == 100.0

    def test_performance_empty(self, in_memory_db):
        stats = get_performance_stats()
        assert stats["win_rate"] == 0


# ── Auto-strategies ──

class TestAutoStrategies:
    def _seed(self, in_memory_db):
        nid = add_news("https://strat.com", "NFP", "beat", "en", "FED", "")
        add_alert(nid, 90, "ALTA", "E", "I", "M", "ollama", True, "CALL", 80)
        return nid

    def test_add_and_get_strategy(self, in_memory_db):
        self._seed(in_memory_db)
        sid = add_auto_strategy(1, "NFP beat", "CALL", 1.0850, 1.0830, 1.0880, 80, 90)
        assert sid is not None
        strategies = get_active_strategies()
        assert len(strategies) == 1

    def test_strategy_cap_at_6(self, in_memory_db):
        self._seed(in_memory_db)
        for i in range(7):
            add_auto_strategy(1, f"S{i}", "CALL", 1.08, 1.07, 1.09, 70, 80)
        strategies = get_active_strategies()
        assert len(strategies) <= 6

    def test_record_strategy_result(self, in_memory_db):
        """v3.48.0 — el test viejo esperaba que get_strategy_performance() contara
        el 'loss' escrito en strategy_results. Ya no: win/loss salen de
        trade_archive (fuente persistente que sobrevive al cap de 6 strategies);
        de strategy_results solo se leen los break_even. Comportamiento
        intencional y verificado en db.py:get_strategy_performance — no es un bug.

        Se testea lo que la funcion SI garantiza hoy: la fila queda registrada.
        """
        self._seed(in_memory_db)
        sid = add_auto_strategy(1, "Test", "PUT", 1.08, 1.07, 1.09, 70, 80)
        record_strategy_result(sid, "loss")

        conn = sqlite3.connect(in_memory_db)
        row = conn.execute(
            "SELECT result FROM strategy_results WHERE strategy_id = ?", (sid,)
        ).fetchone()
        conn.close()
        assert row is not None and row[0] == "loss"

        # trade_archive vacio => la stat agregada no cuenta este loss (por diseño)
        stats = get_strategy_performance()
        assert stats["losses"] == 0


# ── Cleanup ──

class TestCleanup:
    def test_cleanup_removes_old_data(self, in_memory_db):
        nid = add_news("https://old.com", "Old", "s", "en", "", "")
        # Manually backdate the row
        conn = sqlite3.connect(in_memory_db)
        conn.execute(
            "UPDATE news SET fetched_at = ? WHERE id = ?",
            (datetime.utcnow() - timedelta(hours=100), nid),
        )
        conn.commit()
        conn.close()

        cleanup_old_data(hours=72)
        stats = get_stats()
        assert stats["total_news"] == 0

    def test_cleanup_keeps_recent_data(self, in_memory_db):
        add_news("https://recent.com", "Recent", "s", "en", "", "")
        cleanup_old_data(hours=72)
        stats = get_stats()
        assert stats["total_news"] == 1
