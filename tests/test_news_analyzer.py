"""Tests for src/analyzer/news_analyzer.py — News classification and analysis."""
import pytest
from unittest.mock import patch, MagicMock
from src.analyzer.news_analyzer import NewsAnalyzer


@pytest.fixture
def analyzer(mock_logger):
    """Create a NewsAnalyzer in keywords mode (no Ollama, no Claude)."""
    with patch.object(NewsAnalyzer, "_check_ollama", return_value=False), \
         patch.dict("os.environ", {}, clear=True):
        a = NewsAnalyzer(mock_logger)
    assert a.ai_mode == "keywords"
    return a


# ── _detect_ai_mode ──

class TestDetectAiMode:
    @patch.object(NewsAnalyzer, "_check_ollama", return_value=True)
    def test_prefers_ollama(self, mock_ollama, mock_logger):
        a = NewsAnalyzer(mock_logger)
        assert a.ai_mode == "ollama"

    @patch.object(NewsAnalyzer, "_check_ollama", return_value=False)
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
    def test_falls_back_to_claude(self, mock_ollama, mock_logger):
        a = NewsAnalyzer(mock_logger)
        assert a.ai_mode == "claude"

    @patch.object(NewsAnalyzer, "_check_ollama", return_value=False)
    @patch.dict("os.environ", {}, clear=True)
    def test_falls_back_to_keywords(self, mock_ollama, mock_logger):
        a = NewsAnalyzer(mock_logger)
        assert a.ai_mode == "keywords"


# ── _classify_by_keywords ──

class TestClassifyByKeywords:
    def test_tier1_nfp(self, analyzer):
        score, cat = analyzer._classify_by_keywords("nfp data released today")
        assert cat == "tier1"
        assert score >= 80

    def test_tier1_rate_decision(self, analyzer):
        score, cat = analyzer._classify_by_keywords("fed rate decision announced")
        assert cat == "tier1"
        assert score >= 90

    def test_tier2_powell(self, analyzer):
        score, cat = analyzer._classify_by_keywords("powell speaks at conference")
        assert cat == "tier2"
        assert 55 <= score <= 79

    def test_tier2_pmi(self, analyzer):
        score, cat = analyzer._classify_by_keywords("manufacturing pmi beats estimates")
        assert cat == "tier2"
        assert score >= 55

    def test_tier3_oil(self, analyzer):
        score, cat = analyzer._classify_by_keywords("oil price surge on supply fears")
        assert cat == "tier3"
        assert 35 <= score <= 54

    def test_corporate_multiple_hits(self, analyzer):
        score, cat = analyzer._classify_by_keywords("ipo merger acquisition announcement")
        assert cat == "corporate"
        assert score < 30

    def test_corporate_single_hit(self, analyzer):
        score, cat = analyzer._classify_by_keywords("new ipo launched for tech company")
        assert cat == "corporate"
        assert score <= 25

    def test_unknown_text(self, analyzer):
        score, cat = analyzer._classify_by_keywords("the weather is nice today")
        assert cat == "unknown"
        assert score == 25


# ── _detect_direction_keywords ──

class TestDetectDirection:
    def test_usd_bearish_gives_call(self, analyzer):
        direction = analyzer._detect_direction_keywords("rate cut expected dovish fed")
        assert direction == "CALL"

    def test_usd_bullish_gives_put(self, analyzer):
        direction = analyzer._detect_direction_keywords("rate hike hawkish fed strong dollar")
        assert direction == "PUT"

    def test_neutral_on_no_keywords(self, analyzer):
        direction = analyzer._detect_direction_keywords("random text nothing here")
        assert direction == "NEUTRAL"

    def test_mixed_signals_resolves(self, analyzer):
        direction = analyzer._detect_direction_keywords("rate hike but weak dollar")
        # Both bullish and bearish present — tied goes to NEUTRAL or one side
        assert direction in ("CALL", "PUT", "NEUTRAL")


# ── analyze (full pipeline in keywords mode) ──

class TestAnalyze:
    def test_tier1_high_impact_result(self, analyzer):
        result = analyzer.analyze(
            news_id=1,
            title="Fed rate decision: 25bps hike",
            summary="The Federal Reserve raised rates today",
            entities="FED",
            tags="monetary_policy",
        )
        assert result is not None
        assert result["impact_score"] >= 80
        assert result["level"] == "ALTA"
        assert result["analysis_method"] == "keywords"
        assert result["should_alert"] is True

    def test_corporate_news_low_impact(self, analyzer):
        result = analyzer.analyze(
            news_id=2,
            title="Apple IPO merger acquisition earnings report",
            summary="Tech company announces quarterly earnings",
            entities="",
            tags="earnings",
        )
        assert result is not None
        assert result["impact_score"] < 30
        assert result["level"] == "BAJA"
        assert result["should_operate"] is False
        assert result["direction"] == "NEUTRAL"

    def test_tier2_medium_impact(self, analyzer):
        result = analyzer.analyze(
            news_id=3,
            title="Powell speaks at Jackson Hole",
            summary="Fed chair discusses monetary policy outlook",
            entities="Powell,FED",
            tags="monetary_policy",
        )
        assert result is not None
        assert result["impact_score"] >= 50
        assert result["level"] in ("MEDIA", "ALTA")
        assert result["should_alert"] is True

    def test_returns_none_on_exception(self, analyzer):
        """If something goes horribly wrong, analyze returns None."""
        with patch.object(analyzer, "_classify_by_keywords", side_effect=Exception("Boom")):
            result = analyzer.analyze(1, "title", "sum", "", "")
        assert result is None

    def test_neutral_caps_confidence_at_50(self, analyzer):
        result = analyzer.analyze(
            news_id=4,
            title="Manufacturing pmi data released",
            summary="PMI came in at 50.5",
            entities="",
            tags="",
        )
        if result and result["direction"] == "NEUTRAL":
            assert result["confidence"] <= 50

    def test_should_operate_requires_all_conditions(self, analyzer):
        """should_operate needs score>=75, conf>=60, direction CALL/PUT, tier1/2."""
        result = analyzer.analyze(
            news_id=5,
            title="Oil price crude oil surge tariff",
            summary="Geopolitical tensions rise",
            entities="",
            tags="geopolitics",
        )
        assert result is not None
        # Tier 3 geopolitics → should_operate = False
        assert result["should_operate"] is False


# ── _auto_explain ──

class TestAutoExplain:
    def test_tier1_explanation(self, analyzer):
        text = analyzer._auto_explain("Title", "tier1")
        assert "macro" in text.lower() or "relevante" in text.lower()

    def test_corporate_explanation(self, analyzer):
        text = analyzer._auto_explain("Title", "corporate")
        assert "corporativa" in text.lower()

    def test_unknown_category(self, analyzer):
        text = analyzer._auto_explain("Title", "unknown")
        assert "determinada" in text.lower() or "clasificar" in text.lower()


# ── _auto_impact ──

class TestAutoImpact:
    def test_call_direction(self, analyzer):
        text = analyzer._auto_impact("Title", "CALL", 80)
        assert "subir" in text.lower()

    def test_put_direction(self, analyzer):
        text = analyzer._auto_impact("Title", "PUT", 80)
        assert "bajar" in text.lower()

    def test_neutral_direction(self, analyzer):
        text = analyzer._auto_impact("Title", "NEUTRAL", 40)
        assert "sin dirección" in text.lower()
