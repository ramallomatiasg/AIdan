"""Tests de v3.61.0 - fail-loud del feed + perilla de fuentes extra.

Lo que se cubre y POR QUE:

* Los 3 bugs arreglados son de la familia "falla en silencio", asi que los tests
  no verifican que el happy path ande: verifican que **se levante ruido** cuando
  una fuente no aporta. Un test que solo ejercitara el happy path habria estado
  en verde los meses en que 4 de 5 fuentes estuvieron muertas.
* La perilla NEWS_EXTRA_SOURCES arranca APAGADA a proposito (agregar fuentes
  multiplica el volumen de un track que pierde plata). Hay un test que falla si
  alguien cambia el default, porque un rebuild sin tocar .env no debe cambiar el
  comportamiento.
* Test de MUTACION sobre el orden: extrae el sort real del fuente y lo evalua
  contra un feed desordenado. Si alguien vuelve a cortar `entries[:5]` sin
  ordenar, falla.

No toca la DB de produccion ni la red (todo con dobles).
"""

import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector.feed_fetcher import FeedFetcher, MAX_PER_SOURCE  # noqa: E402


class FakeLogger:
    def __init__(self):
        self.warnings, self.errors, self.infos = [], [], []

    def warning(self, m):
        self.warnings.append(str(m))

    def error(self, m):
        self.errors.append(str(m))

    def info(self, m):
        self.infos.append(str(m))

    def debug(self, m):
        pass


def _entry(title, ts=None, link=None):
    """Entrada de feed minima, con la interfaz dict-like que usa feedparser."""
    import time
    e = {
        'title': title,
        'link': link or f"http://x/{title.replace(' ', '_')}",
        'summary': 'resumen ' + title,
    }
    if ts is not None:
        e['published_parsed'] = time.gmtime(ts)
    return e


class FakeFeed:
    def __init__(self, entries, bozo=0):
        self.entries = entries
        self.bozo = bozo


class TestFailLoud(unittest.TestCase):
    """Bug 1: una fuente que responde OK pero viene VACIA tiene que hacer ruido."""

    def _fetch(self, feed_obj, status=200, err=None):
        f = FeedFetcher(FakeLogger())
        with mock.patch.object(f, '_download', return_value=(b'x', status, err)), \
             mock.patch('src.collector.feed_fetcher.feedparser.parse',
                        return_value=feed_obj):
            items = f.fetch_feeds([{'name': 'Muerta', 'url': 'http://dead'}])
        return f.logger, items

    def test_fuente_vacia_loguea_warning(self):
        log, items = self._fetch(FakeFeed([]))
        self.assertEqual(items, [])
        self.assertTrue(any('0 entries' in w for w in log.warnings),
                        f"una fuente vacia no logueo WARNING: {log.warnings}")
        self.assertTrue(any('discontinuada' in w for w in log.warnings))

    def test_todas_caidas_loguea_error(self):
        log, _ = self._fetch(FakeFeed([]))
        self.assertTrue(any('TODAS las fuentes' in e for e in log.errors),
                        "con todas las fuentes caidas no se logueo ERROR")

    def test_fuente_que_no_responde_loguea_warning(self):
        log, items = self._fetch(FakeFeed([]), status=None, err='timeout')
        self.assertEqual(items, [])
        self.assertTrue(any('NO responde' in w for w in log.warnings))

    def test_resumen_lista_las_fuentes_sin_aporte(self):
        log, _ = self._fetch(FakeFeed([]))
        self.assertTrue(any('SIN aporte' in w and 'Muerta' in w for w in log.warnings),
                        f"el resumen no nombro la fuente caida: {log.warnings}")

    def test_fuente_viva_no_dispara_el_error_global(self):
        log, items = self._fetch(FakeFeed([_entry('nota', ts=1_700_000_000)]))
        self.assertEqual(len(items), 1)
        self.assertEqual(log.errors, [])
        self.assertTrue(any('Feeds con aporte' in i for i in log.infos))


class TestTimeoutReal(unittest.TestCase):
    """Bug 2: el timeout estaba asignado y no se usaba."""

    def test_download_pasa_timeout_a_requests(self):
        f = FeedFetcher(FakeLogger(), timeout=7)
        with mock.patch('src.collector.feed_fetcher.requests.get') as g:
            g.return_value = mock.Mock(content=b'x', status_code=200)
            f._download('http://x')
        self.assertEqual(g.call_args.kwargs.get('timeout'), 7,
                         "el timeout no llego a requests.get")

    def test_download_manda_user_agent(self):
        f = FeedFetcher(FakeLogger())
        with mock.patch('src.collector.feed_fetcher.requests.get') as g:
            g.return_value = mock.Mock(content=b'x', status_code=200)
            f._download('http://x')
        ua = g.call_args.kwargs.get('headers', {}).get('User-Agent', '')
        self.assertIn('Mozilla', ua, "sin User-Agent varios feeds devuelven 403")

    def test_excepcion_de_red_no_propaga(self):
        f = FeedFetcher(FakeLogger())
        with mock.patch('src.collector.feed_fetcher.requests.get',
                        side_effect=OSError('boom')):
            content, status, err = f._download('http://x')
        self.assertIsNone(content)
        self.assertIn('boom', err)


class TestOrdenPorFecha(unittest.TestCase):
    """Bug 3: el RSS de Bloomberg NO viene ordenado y se cortaba en [:5]."""

    def test_se_queda_con_las_mas_nuevas(self):
        base = 1_700_000_000
        # feed desordenado a proposito: la mas nueva esta ULTIMA
        entries = [_entry(f"vieja{i}", ts=base - 3600 * (i + 10))
                   for i in range(MAX_PER_SOURCE)]
        entries.append(_entry('NUEVA', ts=base))
        f = FeedFetcher(FakeLogger())
        with mock.patch.object(f, '_download', return_value=(b'x', 200, None)), \
             mock.patch('src.collector.feed_fetcher.feedparser.parse',
                        return_value=FakeFeed(entries)):
            items = f.fetch_feeds([{'name': 'S', 'url': 'http://s'}])
        titles = [i['title'] for i in items]
        self.assertIn('NUEVA', titles,
                      "la nota mas nueva se perdio: se corto sin ordenar")
        self.assertEqual(len(items), MAX_PER_SOURCE)

    def test_items_sin_fecha_van_al_final(self):
        base = 1_700_000_000
        entries = [_entry('sin_fecha')] + [_entry('con_fecha', ts=base)]
        f = FeedFetcher(FakeLogger())
        with mock.patch.object(f, '_download', return_value=(b'x', 200, None)), \
             mock.patch('src.collector.feed_fetcher.feedparser.parse',
                        return_value=FakeFeed(entries)):
            items = f.fetch_feeds([{'name': 'S', 'url': 'http://s'}])
        self.assertEqual(items[0]['title'], 'con_fecha',
                         "un item sin fecha se priorizo sobre uno fechado")

    def test_mutacion_el_sort_existe_en_el_fuente(self):
        """Si alguien saca el sort, este test falla aunque los de arriba pasen
        (podrian pasar por casualidad si el feed llega ordenado)."""
        src = io.open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'src', 'collector', 'feed_fetcher.py'),
            encoding='utf-8').read()
        idx_sort = src.find('entries.sort(')
        idx_slice = src.find('entries[:MAX_PER_SOURCE]')
        self.assertGreater(idx_sort, 0, "desaparecio el sort por fecha")
        self.assertGreater(idx_slice, 0, "cambio la forma de cortar las entries")
        self.assertLess(idx_sort, idx_slice,
                        "el sort quedo DESPUES del corte: no sirve de nada")
        self.assertIn('reverse=True', src[idx_sort:idx_sort + 300],
                      "el sort no es descendente: se queda con las mas VIEJAS")


class TestPerillaFuentesExtra(unittest.TestCase):
    """La perilla arranca apagada: un rebuild sin tocar .env no cambia nada."""

    YAML = """
sources:
  - name: "Bloomberg"
    url: "http://bbg"
extra_sources:
  - name: "FXStreet"
    url: "http://fx"
  - name: "Forexlive"
    url: "http://fl"
"""

    def _get_sources(self, knob):
        import importlib
        with mock.patch.dict(os.environ, {'NEWS_EXTRA_SOURCES': knob}, clear=False):
            import src.common.config as cfg
            importlib.reload(cfg)
            with mock.patch('os.path.exists', return_value=True), \
                 mock.patch('builtins.open', mock.mock_open(read_data=self.YAML)):
                return cfg.Config.get_sources()

    def test_default_apagado(self):
        import importlib
        env = {k: v for k, v in os.environ.items() if k != 'NEWS_EXTRA_SOURCES'}
        with mock.patch.dict(os.environ, env, clear=True):
            import src.common.config as cfg
            importlib.reload(cfg)
            self.assertFalse(cfg.Config.NEWS_EXTRA_SOURCES,
                             "NEWS_EXTRA_SOURCES no puede venir prendida por default: "
                             "multiplica el volumen de un track que pierde plata")

    def test_apagada_solo_devuelve_sources(self):
        srcs = self._get_sources('false')
        self.assertEqual([s['name'] for s in srcs], ['Bloomberg'])

    def test_prendida_suma_las_extra(self):
        srcs = self._get_sources('true')
        self.assertEqual([s['name'] for s in srcs],
                         ['Bloomberg', 'FXStreet', 'Forexlive'])

    def test_yaml_sin_extra_sources_no_explota(self):
        import importlib
        with mock.patch.dict(os.environ, {'NEWS_EXTRA_SOURCES': 'true'}, clear=False):
            import src.common.config as cfg
            importlib.reload(cfg)
            with mock.patch('os.path.exists', return_value=True), \
                 mock.patch('builtins.open',
                            mock.mock_open(read_data='sources:\n  - name: A\n    url: u\n')):
                self.assertEqual(cfg.Config.get_sources(), [{'name': 'A', 'url': 'u'}])


class TestSourcesYamlDelRepo(unittest.TestCase):
    """El yaml del repo tiene que quedar consistente con la decision tomada."""

    def setUp(self):
        import yaml
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'config', 'sources.yaml')
        with io.open(p, encoding='utf-8') as f:
            self.data = yaml.safe_load(f)

    def test_las_muertas_ya_no_estan_activas(self):
        urls = ' '.join(s['url'] for s in self.data.get('sources', []))
        for muerta in ('feeds.ft.com', 'feeds.reuters.com',
                       'feeds.marketwatch.com', 'feeds.investing.com'):
            self.assertNotIn(muerta, urls,
                             f"{muerta} devuelve 0 entries: no puede seguir en `sources`")

    def test_activas_son_las_medidas_como_rapidas(self):
        nombres = [s['name'] for s in self.data['sources']]
        self.assertIn('Forexlive', nombres,
                      "Forexlive publica el dato a +15 SEGUNDOS del release "
                      "(Bloomberg a +25,3 min): es la razon de todo el cambio")
        self.assertEqual(nombres, ['Forexlive', 'Bloomberg'],
                         "el orden importa: el cable rapido primero")

    def test_forexlive_es_el_feed_principal_no_el_de_news(self):
        """El /feed/news de Forexlive NO tenia el Core PCE; el /feed si.
        Si alguien lo cambia por el sub-feed, se pierde cobertura de datos."""
        url = [s['url'] for s in self.data['sources'] if s['name'] == 'Forexlive'][0]
        self.assertTrue(url.rstrip('/').endswith('forexlive.com/feed'),
                        f"Forexlive tiene que apuntar al feed principal, no a {url}")

    def test_extra_sources_existe_y_no_esta_vacia(self):
        self.assertTrue(self.data.get('extra_sources'),
                        "las candidatas medidas tienen que quedar registradas en el yaml")

    def test_yaml_es_ascii_puro(self):
        """El exe lee este archivo con el locale de Windows. Un caracter no-ASCII
        tiraba UnicodeDecodeError y dejaba al collector SIN NINGUNA fuente."""
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'config', 'sources.yaml')
        raw = io.open(p, 'rb').read()
        try:
            raw.decode('ascii')
        except UnicodeDecodeError as e:
            self.fail(f"config/sources.yaml tiene un byte no-ASCII en {e.start}: "
                      f"{raw[max(0, e.start-30):e.start+10]!r}")

    def test_get_sources_lee_utf8_explicito(self):
        """Test de mutacion: si alguien saca el encoding='utf-8' de get_sources,
        volvemos al bug del cp1252."""
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'src', 'common', 'config.py')
        src = io.open(p, encoding='utf-8').read()
        i = src.find('def get_sources')
        self.assertGreater(i, 0)
        cuerpo = src[i:i + 1200]
        self.assertIn("encoding='utf-8'", cuerpo,
                      "get_sources() volvio a abrir el yaml sin encoding explicito")


if __name__ == '__main__':
    unittest.main(verbosity=2)
