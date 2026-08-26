"""RSS feed fetcher.

v3.61.0 - tres bugs arreglados el 26-ago-2026, todos de la familia
"falla en silencio y devuelve algo plausible":

1. FALLA MUDA. `fetch_feeds` envolvia cada fuente en un try/except que solo
   logueaba excepciones. Una fuente que responde 200/301 con CERO entries (feed
   discontinuado, que es lo que le paso a 4 de las 5 fuentes configuradas) no
   levanta excepcion: devuelve una lista vacia y el collector sigue como si nada.
   Medido el 26-ago: FT, Reuters, MarketWatch e Investing.com devolvian 0 entries
   y 1225 de 1225 noticias de los ultimos 30 dias eran de bloomberg.com. Nadie
   se dio cuenta durante meses. Ahora una fuente vacia loguea WARNING y el
   resumen por ciclo dice cuantas fuentes aportaron.

2. SIN TIMEOUT. `self.timeout = 10` estaba asignado y NUNCA se usaba
   (`feedparser.parse(url)` no acepta timeout). Una fuente colgada bloqueaba el
   loop entero del collector, o sea latencia infinita en el resto de las
   fuentes. Ahora se baja con `requests` (timeout real) y se parsea el contenido.

3. `entries[:5]` SOBRE UN FEED NO ORDENADO. Verificado: el RSS de Bloomberg NO
   viene ordenado por fecha (en la muestra del 26-ago la 5ta entrada tenia 956
   min de antiguedad y habia items mas nuevos mas abajo). Tomar los primeros 5
   en orden de documento puede DESCARTAR las notas mas nuevas. Ahora se ordena
   por fecha de publicacion descendente antes de cortar.

Nada de esto cambia que decision toma AIdan: es plomeria del feed.
"""

import feedparser
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException
import os

# UA explicito: varios feeds (ForexFactory, TradingEconomics) devuelven 403 al
# User-Agent default de las librerias de python.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# Cuantas entradas por fuente se consideran por ciclo. El dedup por URL de
# add_news() hace que repetir items ya vistos no agregue filas, asi que este
# numero acota el trabajo por ciclo, no el volumen de noticias nuevas.
MAX_PER_SOURCE = 5


class FeedFetcher:
    def __init__(self, logger, timeout=10):
        self.logger = logger
        self.timeout = timeout

    def _download(self, url):
        """Bajar el feed con timeout REAL. Devuelve (contenido, status, error)."""
        try:
            resp = requests.get(url, timeout=self.timeout,
                                headers={'User-Agent': _UA})
            return resp.content, resp.status_code, None
        except Exception as e:
            return None, None, str(e)

    @staticmethod
    def _entry_ts(entry):
        """Timestamp de publicacion como epoch UTC, o None si el feed no lo trae."""
        from calendar import timegm
        for attr in ('published_parsed', 'updated_parsed'):
            try:
                pp = entry.get(attr)
            except Exception:
                pp = None
            if pp:
                try:
                    return timegm(pp)
                except Exception:
                    continue
        return None

    def fetch_feeds(self, sources):
        """Fetch and parse feeds from all sources.

        Fail-loud: una fuente que no aporta entries loguea WARNING (ver bug 1 en
        el docstring del modulo). El resumen final permite ver de un vistazo si
        el feed se degrado sin que nada tire excepcion.
        """
        news_items = []
        alive, dead = [], []

        for source in sources:
            name = source.get('name', '?')
            url = source.get('url', '')
            content, status, err = self._download(url)

            if err is not None:
                self.logger.warning(f"Feed '{name}' NO responde ({err}) -> 0 items")
                dead.append(name)
                continue

            try:
                feed = feedparser.parse(content)
                entries = list(feed.entries)
            except Exception as e:
                self.logger.warning(f"Feed '{name}' no se pudo parsear (HTTP {status}): {e}")
                dead.append(name)
                continue

            if not entries:
                # NO es una excepcion: el feed contesta bien y viene vacio. Este
                # es exactamente el caso que estuvo mudo durante meses.
                self.logger.warning(
                    f"Feed '{name}' devolvio 0 entries (HTTP {status}, "
                    f"bozo={getattr(feed, 'bozo', '?')}) -> fuente probablemente "
                    f"discontinuada: {url}")
                dead.append(name)
                continue

            # Bug 3: ordenar por fecha antes de cortar. Los items sin fecha van
            # al final (no se pueden priorizar honestamente).
            entries.sort(
                key=lambda e: (self._entry_ts(e) is not None, self._entry_ts(e) or 0),
                reverse=True)

            got = 0
            for entry in entries[:MAX_PER_SOURCE]:
                news = self._extract_news(entry, name)
                if news:
                    news_items.append(news)
                    got += 1
            if got:
                alive.append(f"{name}:{got}")
            else:
                self.logger.warning(
                    f"Feed '{name}' tenia {len(entries)} entries pero ninguna extraible")
                dead.append(name)

        if dead:
            self.logger.warning(
                f"Feeds SIN aporte este ciclo ({len(dead)}/{len(sources)}): "
                f"{', '.join(dead)}")
        self.logger.info(f"Feeds con aporte: {', '.join(alive) if alive else 'NINGUNO'}")
        if not alive and sources:
            self.logger.error(
                "TODAS las fuentes de noticias estan caidas -> el track news queda ciego")

        return news_items

    def _extract_news(self, entry, source_name):
        """Extract and normalize news from feed entry"""
        try:
            title = entry.get('title', 'No title')
            link = entry.get('link', '')

            # Get summary or description
            summary = entry.get('summary', entry.get('description', ''))
            summary = self._clean_html(summary)[:500]  # Max 500 chars

            # Detect language
            try:
                language = detect(title + ' ' + summary)
            except LangDetectException:
                language = 'unknown'

            # Extract entities (simple pattern matching)
            entities = self._extract_entities(title + ' ' + summary)

            # Extract tags
            tags = self._extract_tags(title + ' ' + summary)

            # Extract publication date from feed entry
            published_at = None
            ts = self._entry_ts(entry)
            if ts is not None:
                try:
                    published_at = datetime.utcfromtimestamp(ts).isoformat()
                except Exception:
                    pass
            if not published_at and entry.get('published'):
                published_at = str(entry.get('published'))[:25]

            return {
                'url': link,
                'title': title,
                'summary': summary,
                'language': language,
                'source': source_name,
                'entities': entities,
                'tags': tags,
                'published_at': published_at,
                'fetched_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error extracting news: {str(e)}")
            return None

    def _clean_html(self, text):
        """Remove HTML tags from text"""
        if not text:
            return ""
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)

    def _extract_entities(self, text):
        """Extract financial entities from text"""
        entities = []
        keywords = {
            'FED': ['fed', 'federal reserve'],
            'ECB': ['ecb', 'european central bank'],
            'BOE': ['bank of england', 'boe'],
            'Powell': ['powell'],
            'CPI': ['cpi', 'consumer price index'],
            'GDP': ['gdp', 'gross domestic product'],
            'S&P500': ['s&p 500', 'sp 500'],
            'Nasdaq': ['nasdaq'],
            'DOW': ['dow jones', 'dow'],
        }

        text_lower = text.lower()
        for entity, patterns in keywords.items():
            for pattern in patterns:
                if pattern in text_lower:
                    entities.append(entity)
                    break

        return list(set(entities))

    def _extract_tags(self, text):
        """Extract topic tags from text"""
        tags = []
        topic_patterns = {
            'monetary_policy': ['interest rate', 'fed', 'central bank', 'inflation'],
            'market_volatility': ['volatility', 'crash', 'surge', 'plunge'],
            'earnings': ['earnings', 'profit', 'revenue', 'loss'],
            'merger': ['merger', 'acquisition', 'takeover', 'deal'],
            'crypto': ['bitcoin', 'ethereum', 'crypto', 'blockchain'],
            'tech': ['tech', 'ai', 'software', 'semiconductor'],
            'energy': ['oil', 'gas', 'energy', 'renewable'],
            'geopolitics': ['war', 'sanctions', 'trade war', 'tariff'],
        }

        text_lower = text.lower()
        for tag, patterns in topic_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    tags.append(tag)
                    break

        return list(set(tags))

    def save_to_file(self, news_items):
        """Save news to JSONL file organized by date"""
        if not news_items:
            return

        now = datetime.utcnow()
        data_dir = f"data/{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}"
        os.makedirs(data_dir, exist_ok=True)

        file_path = f"{data_dir}/news.jsonl"

        with open(file_path, 'a') as f:
            for item in news_items:
                f.write(json.dumps(item) + '\n')

        self.logger.info(f"Saved {len(news_items)} items to {file_path}")
