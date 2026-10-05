"""v3.65.0 - canal rapido de noticias (home de investinglive). Sin red, sin DB.

Lo que importa, en orden:
1. Que la URL que arma sea IDENTICA al <link> del RSS (si no, la misma nota entra
   dos veces y el LLM la opera dos veces).
2. Que la fecha salga de `article:published_time` (la misma del pubDate del RSS).
3. Fail-loud: home sin links o nota sin fecha => WARNING, nunca silencio.
4. Apagado por default y, apagado, el loop del collector es el de v3.64.0.
"""
import os
import re
import time
from unittest.mock import MagicMock, patch

import pytest

from src.collector import home_fast as hf
from src.collector.feed_fetcher import FeedFetcher

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


ARTICLE = _read("investinglive_article_20261005.html")
HOME = _read("investinglive_home_20261005.html")
PUB_EPOCH = 1791177203  # 2026-10-05T05:13:23Z (el pubDate del RSS de esa nota)


def _resp(text, status=200):
    r = MagicMock()
    r.text, r.status_code = text, status
    return r


# ── parsing ──────────────────────────────────────────────────────────────────

class TestParsing:
    def test_url_canonica_igual_al_link_del_rss(self):
        # <link> real del RSS del 5-oct, copiado tal cual
        rss_link = ("https://investinglive.com/news/bond-yields-remain-the-market-s-"
                    "pressure-point-even-after-soft-us-jobs-report/")
        path = "/news/bond-yields-remain-the-market-s-pressure-point-even-after-soft-us-jobs-report"
        assert hf.canonical_url(path) == rss_link
        assert hf.canonical_url(path + "/") == rss_link

    def test_home_paths_reales_sin_repetir_y_solo_news(self):
        paths = hf.home_paths(HOME)
        assert paths, "la home real del 5-oct tiene links /news/"
        assert len(paths) == len(set(paths))
        assert all(p.startswith("/news/") and p.endswith("/") for p in paths)
        assert "/markets/" not in paths

    def test_articulo_real(self):
        title, summary, ts = hf.parse_article(ARTICLE)
        assert title.startswith("Bond yields remain the market")
        assert "Payrolls cooled" in summary
        assert int(ts) == PUB_EPOCH

    def test_fecha_con_7_decimales_de_dotnet(self):
        assert int(hf.parse_published_epoch("2026-10-05T05:13:23.7071273Z")) == PUB_EPOCH

    @pytest.mark.parametrize("v", [None, "", "ayer", "2026-13-45T00:00:00Z"])
    def test_fecha_basura_da_none(self, v):
        assert hf.parse_published_epoch(v) is None

    def test_articulo_sin_fecha(self):
        assert hf.parse_article("<html><meta property=\"og:title\" content=\"x\"/></html>")[2] is None


# ── poll ─────────────────────────────────────────────────────────────────────

def _fetcher(mock_logger, now):
    return hf.HomeFastFetcher(mock_logger, FeedFetcher(mock_logger), now_fn=lambda: now)


def _routes(home=HOME, article=ARTICLE, home_status=200):
    def get(url, **kw):
        if url == hf.HOME_URL:
            return _resp(home, home_status)
        return _resp(article)
    return get


class TestPoll:
    def test_nota_fresca_sale_con_formato_de_feed_fetcher(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH + 60)
        with patch.object(hf.requests, "get", side_effect=_routes()):
            items = f.poll()
        assert items, "nota publicada hace 1 min => tiene que salir"
        it = items[0]
        for k in ("url", "title", "summary", "language", "entities", "tags", "published_at"):
            assert k in it
        assert it["url"].startswith("https://investinglive.com/news/")
        assert it["published_at"] == "2026-10-05T05:13:23"   # mismo formato que el RSS

    def test_nota_vieja_se_descarta(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH + 31 * 60)
        with patch.object(hf.requests, "get", side_effect=_routes()):
            assert f.poll() == []

    def test_no_vuelve_a_bajar_lo_ya_visto(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH + 60)
        with patch.object(hf.requests, "get", side_effect=_routes()) as g:
            f.poll()
            f.poll()
            f.poll()
            llamadas_nota = [c for c in g.call_args_list if c.args[0] != hf.HOME_URL]
        assert len(llamadas_nota) == len(hf.home_paths(HOME))

    def test_tope_por_ciclo(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH + 60)
        f.max_new = 2
        with patch.object(hf.requests, "get", side_effect=_routes()) as g:
            f.poll()
            assert len([c for c in g.call_args_list if c.args[0] != hf.HOME_URL]) == 2

    def test_home_sin_links_loguea_warning(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH)
        with patch.object(hf.requests, "get", side_effect=_routes(home="<html></html>")):
            assert f.poll() == []
        assert mock_logger.warning.called

    def test_home_caida_loguea_warning(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH)
        with patch.object(hf.requests, "get", side_effect=_routes(home_status=503)):
            assert f.poll() == []
        assert mock_logger.warning.called

    def test_nota_sin_fecha_loguea_warning(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH)
        with patch.object(hf.requests, "get", side_effect=_routes(article="<html></html>")):
            assert f.poll() == []
        assert mock_logger.warning.called

    def test_nota_que_no_responde_se_reintenta(self, mock_logger):
        f = _fetcher(mock_logger, PUB_EPOCH + 60)

        def get(url, **kw):
            if url == hf.HOME_URL:
                return _resp(HOME)
            raise TimeoutError("lenta")
        with patch.object(hf.requests, "get", side_effect=get):
            f.poll()
        assert not f.seen, "una nota que no respondio NO se marca vista"


# ── perilla y call-site ──────────────────────────────────────────────────────

class TestPerillaYCallSite:
    def test_default_apagado(self, monkeypatch):
        monkeypatch.delenv("NEWS_HOME_FAST", raising=False)
        import importlib
        import src.common.config as cfg
        importlib.reload(cfg)
        assert cfg.Config.NEWS_HOME_FAST is False

    def _collector_src(self):
        with open(os.path.join(ROOT, "AIdan_TodoEnUno.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("def run_collector_service")
        return src[i: src.index("def run_analyzer_service", i)]

    def test_collector_crea_el_canal_solo_con_la_perilla(self):
        s = self._collector_src()
        assert "if Config.NEWS_HOME_FAST:" in s
        assert s.index("if Config.NEWS_HOME_FAST:") < s.index("HomeFastFetcher(")

    def test_rss_sigue_cada_collector_interval(self):
        s = self._collector_src()
        assert re.search(r"time\.time\(\) - last_rss >= Config\.COLLECTOR_INTERVAL", s)
        assert "fetcher.fetch_feeds(sources)" in s

    def test_apagado_duerme_collector_interval(self):
        s = self._collector_src()
        assert "if home_fast is not None else Config.COLLECTOR_INTERVAL" in s

    def test_canal_rapido_usa_el_mismo_add_news(self):
        # misma funcion de guardado => mismo dedup por URL que el RSS
        s = self._collector_src()
        assert "_store(fast_items)" in s and "_store(news_items)" in s
