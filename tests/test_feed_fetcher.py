"""Tests for src/collector/feed_fetcher.py — RSS feed fetching and parsing."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from src.collector.feed_fetcher import FeedFetcher


@pytest.fixture
def fetcher(mock_logger):
    return FeedFetcher(mock_logger)


@pytest.fixture
def sample_sources():
    return [
        {"name": "Reuters", "url": "https://feeds.reuters.com/reuters/businessNews"},
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss"},
    ]


@pytest.fixture
def mock_feed_entry():
    """A fake feedparser entry."""
    entry = MagicMock()
    entry.get = lambda key, default="": {
        "title": "Fed raises interest rates by 25 basis points",
        "link": "https://reuters.com/article/fed-rates",
        "summary": "<p>The Federal Reserve raised interest rates today.</p>",
    }.get(key, default)
    return entry


# ── FeedFetcher._clean_html ──

class TestCleanHtml:
    def test_strips_tags(self, fetcher):
        assert fetcher._clean_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_empty_string(self, fetcher):
        assert fetcher._clean_html("") == ""

    def test_none_returns_empty(self, fetcher):
        assert fetcher._clean_html(None) == ""

    def test_plain_text_unchanged(self, fetcher):
        assert fetcher._clean_html("No HTML here") == "No HTML here"


# ── FeedFetcher._extract_entities ──

class TestExtractEntities:
    def test_detects_fed(self, fetcher):
        entities = fetcher._extract_entities("Federal Reserve raises rates")
        assert "FED" in entities

    def test_detects_ecb(self, fetcher):
        entities = fetcher._extract_entities("ECB holds steady on policy")
        assert "ECB" in entities

    def test_detects_multiple_entities(self, fetcher):
        entities = fetcher._extract_entities("Powell speaks about CPI data and GDP")
        assert "Powell" in entities
        assert "CPI" in entities
        assert "GDP" in entities

    def test_no_entities(self, fetcher):
        entities = fetcher._extract_entities("Nice weather today")
        assert entities == []


# ── FeedFetcher._extract_tags ──

class TestExtractTags:
    def test_detects_monetary_policy(self, fetcher):
        tags = fetcher._extract_tags("Interest rate decision by central bank")
        assert "monetary_policy" in tags

    def test_detects_geopolitics(self, fetcher):
        tags = fetcher._extract_tags("Trade war tariff escalation")
        assert "geopolitics" in tags

    def test_detects_crypto(self, fetcher):
        tags = fetcher._extract_tags("Bitcoin reaches new high")
        assert "crypto" in tags

    def test_no_tags(self, fetcher):
        tags = fetcher._extract_tags("Random boring sentence")
        assert tags == []


# ── FeedFetcher._extract_news ──

class TestExtractNews:
    def test_extracts_valid_entry(self, fetcher, mock_feed_entry):
        news = fetcher._extract_news(mock_feed_entry, "Reuters")
        assert news is not None
        assert news["title"] == "Fed raises interest rates by 25 basis points"
        assert news["url"] == "https://reuters.com/article/fed-rates"
        assert "FED" in news["entities"]
        assert "monetary_policy" in news["tags"]
        assert news["source"] == "Reuters"

    def test_truncates_summary_to_500_chars(self, fetcher):
        entry = MagicMock()
        long_text = "A" * 1000
        entry.get = lambda key, default="": {
            "title": "Title",
            "link": "https://x.com",
            "summary": long_text,
        }.get(key, default)

        news = fetcher._extract_news(entry, "Test")
        assert len(news["summary"]) <= 500

    def test_handles_missing_summary(self, fetcher):
        entry = MagicMock()
        entry.get = lambda key, default="": {
            "title": "Bare title",
            "link": "https://x.com",
        }.get(key, default)

        news = fetcher._extract_news(entry, "Test")
        assert news is not None
        assert news["summary"] == ""

    def test_returns_none_on_exception(self, fetcher):
        entry = MagicMock()
        entry.get = MagicMock(side_effect=Exception("Parse error"))
        news = fetcher._extract_news(entry, "Test")
        assert news is None


# ── FeedFetcher.fetch_feeds ──

class TestFetchFeeds:
    """v3.61.0: fetch_feeds ya no llama a feedparser.parse(url) — baja el feed con
    requests (timeout real) y parsea el contenido. Estos tests mockean las DOS
    mitades; antes solo mockeaban el parse y por eso salian a la red de verdad."""

    @staticmethod
    def _dl_ok(status=200):
        return patch("src.collector.feed_fetcher.requests.get",
                     return_value=MagicMock(content=b"<rss/>", status_code=status))

    @patch("src.collector.feed_fetcher.feedparser.parse")
    def test_fetches_from_all_sources(self, mock_parse, fetcher, sample_sources, mock_feed_entry):
        mock_feed = MagicMock()
        mock_feed.entries = [mock_feed_entry, mock_feed_entry]
        mock_parse.return_value = mock_feed

        with self._dl_ok():
            results = fetcher.fetch_feeds(sample_sources)
        assert len(results) == 4  # 2 sources x 2 entries
        assert mock_parse.call_count == 2

    @patch("src.collector.feed_fetcher.feedparser.parse")
    def test_continues_on_source_error(self, mock_parse, fetcher, sample_sources, mock_feed_entry):
        """If one source fails, other sources should still be fetched."""
        mock_feed_ok = MagicMock()
        mock_feed_ok.entries = [mock_feed_entry]
        mock_parse.side_effect = [Exception("Parse error"), mock_feed_ok]

        with self._dl_ok():
            results = fetcher.fetch_feeds(sample_sources)
        assert len(results) == 1  # Only second source succeeds
        # v3.61.0: una fuente que no se puede parsear ahora es WARNING (fail-loud
        # por fuente), no un error suelto: lo que importa es que se loguee.
        assert fetcher.logger.warning.called

    @patch("src.collector.feed_fetcher.feedparser.parse")
    def test_limits_to_5_entries_per_source(self, mock_parse, fetcher, mock_feed_entry):
        mock_feed = MagicMock()
        mock_feed.entries = [mock_feed_entry] * 10
        mock_parse.return_value = mock_feed

        with self._dl_ok():
            results = fetcher.fetch_feeds([{"name": "Test", "url": "https://test.com"}])
        assert len(results) == 5  # Capped at MAX_PER_SOURCE

    @patch("src.collector.feed_fetcher.feedparser.parse")
    def test_empty_feed(self, mock_parse, fetcher):
        mock_feed = MagicMock()
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        with self._dl_ok():
            results = fetcher.fetch_feeds([{"name": "Empty", "url": "https://empty.com"}])
        assert results == []
        # v3.61.0: un feed vacio ya NO puede pasar en silencio
        assert fetcher.logger.warning.called

    @patch("src.collector.feed_fetcher.feedparser.parse")
    def test_network_error_no_llama_al_parser(self, mock_parse, fetcher):
        """Si la descarga falla no se parsea nada y no explota el ciclo."""
        with patch("src.collector.feed_fetcher.requests.get",
                   side_effect=OSError("timeout")):
            results = fetcher.fetch_feeds([{"name": "Down", "url": "https://down.com"}])
        assert results == []
        assert mock_parse.call_count == 0
        assert fetcher.logger.warning.called


# ── FeedFetcher.save_to_file ──

class TestSaveToFile:
    def test_saves_news_as_jsonl(self, fetcher, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        items = [
            {"title": "News 1", "url": "https://a.com"},
            {"title": "News 2", "url": "https://b.com"},
        ]
        fetcher.save_to_file(items)

        # Find the created file
        jsonl_files = list(tmp_path.rglob("news.jsonl"))
        assert len(jsonl_files) == 1

        lines = jsonl_files[0].read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["title"] == "News 1"

    def test_skips_empty_list(self, fetcher, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fetcher.save_to_file([])
        jsonl_files = list(tmp_path.rglob("news.jsonl"))
        assert len(jsonl_files) == 0
