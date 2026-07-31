"""Tests for src/analyzer/news_analyzer.py — News classification and analysis."""
import pytest
from unittest.mock import patch, MagicMock
from src.analyzer.news_analyzer import NewsAnalyzer


@pytest.fixture
def analyzer(mock_logger):
    """Create a NewsAnalyzer in keywords mode (ni Ollama ni Groq disponibles).

    v3.48.0 — antes esto patcheaba solo `_check_ollama` + limpiaba os.environ y
    asumia que sin env vars no habia LLM. Falso desde v3.21: `_check_groq()` lee
    `Config.GROQ_API_KEY`, que tiene un default en codigo -> el modo real salia
    'groq' y reventaban 27 tests. Ademas `_check_groq` hace un GET real a
    api.groq.com: patchearlo saca la red de la suite (deterministica y rapida).
    """
    with patch.object(NewsAnalyzer, "_check_ollama", return_value=False), \
         patch.object(NewsAnalyzer, "_check_groq", return_value=False):
        a = NewsAnalyzer(mock_logger)
    assert a.ai_mode == "keywords"
    return a


# ── _detect_ai_mode ──

class TestDetectAiMode:
    """Contrato real (v3.21.0): LLM_PROVIDER_PRIMARY = ollama | groq | auto.
    El modo 'claude' ya no existe en _detect_ai_mode."""

    @patch.object(NewsAnalyzer, "_check_groq", return_value=True)
    @patch.object(NewsAnalyzer, "_check_ollama", return_value=True)
    @patch.dict("os.environ", {"LLM_PROVIDER_PRIMARY": "ollama"})
    def test_primary_ollama_prefers_local(self, mock_ollama, mock_groq, mock_logger):
        assert NewsAnalyzer(mock_logger).ai_mode == "ollama"

    @patch.object(NewsAnalyzer, "_check_groq", return_value=True)
    @patch.object(NewsAnalyzer, "_check_ollama", return_value=True)
    @patch.dict("os.environ", {"LLM_PROVIDER_PRIMARY": "auto"})
    def test_auto_prefers_groq(self, mock_ollama, mock_groq, mock_logger):
        assert NewsAnalyzer(mock_logger).ai_mode == "groq"

    @patch.object(NewsAnalyzer, "_check_groq", return_value=False)
    @patch.object(NewsAnalyzer, "_check_ollama", return_value=True)
    @patch.dict("os.environ", {"LLM_PROVIDER_PRIMARY": "auto"})
    def test_auto_falls_back_to_ollama(self, mock_ollama, mock_groq, mock_logger):
        assert NewsAnalyzer(mock_logger).ai_mode == "ollama"

    @patch.object(NewsAnalyzer, "_check_groq", return_value=False)
    @patch.object(NewsAnalyzer, "_check_ollama", return_value=False)
    def test_falls_back_to_keywords(self, mock_ollama, mock_groq, mock_logger):
        assert NewsAnalyzer(mock_logger).ai_mode == "keywords"


# ── _keyword_prefilter ──
#
# v3.48.0 — este bloque REEMPLAZA a ~22 tests que llamaban a `_classify_by_keywords`,
# `_detect_direction_keywords`, `_auto_explain` y `_auto_impact`: cuatro metodos que
# NO EXISTEN en el modulo. Testeaban un clasificador tier1/tier2/tier3/corporate que
# se elimino cuando el LLM paso a ser obligatorio (v3.21). Estaban rojos desde
# entonces => cero senal. Se cubre en cambio lo que el modulo SI hace hoy.

class TestKeywordPrefilter:
    """El pre-filtro corre en TODA noticia antes de gastar una llamada al LLM."""

    def test_always_relevant_forces(self, analyzer):
        assert analyzer._keyword_prefilter("ECB interest rate decision", "") == "force"

    def test_irrelevant_topic_skips(self, analyzer):
        result = analyzer._keyword_prefilter("Celebrity wedding in Hollywood", "")
        assert result in ("skip", "pass")

    def test_uncertain_passes_to_ai(self, analyzer):
        assert analyzer._keyword_prefilter("Company announces new product line", "") == "pass"


class TestAnalyzeDegradedMode:
    """Contrato del modo degradado (sin Groq ni Ollama).

    OJO: 'keywords' NO significa "analiza por keywords". Desde v3.21 no hay
    analisis sin LLM: una noticia RELEVANTE devuelve None y se loguea
    'AI NOT AVAILABLE'. Es comportamiento intencional, verificado en el codigo
    (news_analyzer._analyze_with_ai) — se testea para que quede fijado.
    """

    def test_relevant_news_returns_none_without_llm(self, analyzer):
        result = analyzer.analyze(
            news_id=1,
            title="Fed rate decision: 25bps hike",
            summary="The Federal Reserve raised rates today",
            entities="FED",
            tags="monetary_policy",
        )
        assert result is None

    def test_irrelevant_news_short_circuits_without_llm(self, analyzer):
        """La noticia filtrada NO llega al LLM: devuelve dict de bajo impacto."""
        result = analyzer.analyze(
            news_id=2,
            title="Apple IPO merger acquisition earnings report",
            summary="Tech company announces quarterly earnings",
            entities="",
            tags="earnings",
        )
        assert result is not None
        assert result["analysis_method"] == "keyword_filter"
        assert result["should_operate"] is False
        assert result["direction"] == "NEUTRAL"
        assert result["impact_score"] < 30


