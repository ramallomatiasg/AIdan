"""Canal rapido de noticias: la HOME de investinglive (ex Forexlive). v3.65.0.

POR QUE EXISTE
--------------
Medido el 5-oct-2026 sobre `news` (desde el 27-ago): Forexlive llega con mediana
5,3 min y p90 77 min entre publicacion y deteccion, con el collector poleando
cada 60 s. El cuello NO es AIdan: el CDN del sitio cachea el RSS con
`s-maxage=300, stale-while-revalidate=3600` (se vio una copia de 574 s) e ignora
query strings y `Cache-Control: no-cache`.

La HOME se cachea con `s-maxage=30, stale-while-revalidate=60` y lista los mismos
links, y la pagina de cada nota es `no-store` y trae `article:published_time`
IDENTICO al pubDate del RSS (verificado al segundo). Entonces: la home dice QUE
nota es nueva, la pagina de la nota da titulo/resumen/fecha, y la URL canonica es
la MISMA que trae el RSS => cuando el RSS la traiga despues, `add_news` la
deduplica por URL y no hay doble fila.

Se activa con NEWS_HOME_FAST=true (env, sin rebuild). Apagado = el collector se
comporta exactamente como en v3.64.0.

FAIL-LOUD (la clase de bug que mas dano hizo aca es "falla en silencio"):
home sin links /news/ o nota sin fecha => WARNING, nunca una lista vacia muda.
"""

import re
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://investinglive.com"
HOME_URL = BASE_URL + "/"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

_HREF_RE = re.compile(r'href="(/news/[a-z0-9\-]+/?)"')
_META_RE = r'<meta[^>]+(?:property|name)="{key}"[^>]+content="([^"]*)"'


def home_paths(html):
    """Paths '/news/slug/' de la home, en orden y sin repetir."""
    out = []
    for p in _HREF_RE.findall(html or ""):
        if not p.endswith("/"):
            p += "/"
        if p not in out:
            out.append(p)
    return out


def canonical_url(path):
    """Misma forma que el <link> del RSS: https://investinglive.com/news/slug/"""
    if not path.endswith("/"):
        path += "/"
    return BASE_URL + path


def _meta(html, key):
    m = re.search(_META_RE.format(key=re.escape(key)), html or "")
    if not m:
        return None
    import html as _h
    return _h.unescape(m.group(1)).strip() or None


def parse_published_epoch(value):
    """'2026-10-05T05:13:23.7071273Z' -> epoch UTC. None si no se puede."""
    if not value:
        return None
    s = value.strip().replace("Z", "+00:00")
    # .NET manda 7 decimales; fromisoformat de 3.11 acepta hasta 6.
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def parse_article(html):
    """(titulo, resumen, epoch_publicacion) de la pagina de una nota."""
    title = _meta(html, "og:title")
    summary = _meta(html, "og:description") or _meta(html, "description") or ""
    ts = parse_published_epoch(_meta(html, "article:published_time"))
    return title, summary, ts


class HomeFastFetcher:
    """Detecta notas nuevas en la home y las devuelve con el formato de FeedFetcher."""

    def __init__(self, logger, feed_fetcher, timeout=10, max_age_min=30.0,
                 max_new_per_cycle=8, now_fn=time.time):
        self.logger = logger
        self.ff = feed_fetcher          # reusa _extract_news (idioma, entidades, tags)
        self.timeout = timeout
        self.max_age_min = max_age_min  # mas vieja que esto: el RSS ya la trae, no es "rapida"
        self.max_new = max_new_per_cycle
        self.now_fn = now_fn
        self.seen = set()               # paths ya resueltos (nuevos o descartados)

    def _get(self, url):
        resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": _UA})
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.text

    def poll(self):
        """Un ciclo. Devuelve lista de dicts como FeedFetcher._extract_news."""
        try:
            html = self._get(HOME_URL)
        except Exception as e:
            self.logger.warning(f"home-fast: la home NO responde ({e}) -> 0 items")
            return []
        paths = home_paths(html)
        if not paths:
            self.logger.warning("home-fast: la home no trae links /news/ -> "
                                "cambio el formato del sitio? canal rapido CIEGO")
            return []

        items = []
        nuevos = [p for p in paths if p not in self.seen][: self.max_new]
        for path in nuevos:
            self.seen.add(path)
            url = canonical_url(path)
            try:
                art = self._get(url)
            except Exception as e:
                self.logger.warning(f"home-fast: nota {path} no responde ({e})")
                self.seen.discard(path)   # reintentar el proximo ciclo
                continue
            title, summary, ts = parse_article(art)
            if not title or ts is None:
                self.logger.warning(f"home-fast: nota {path} sin titulo/fecha "
                                    f"(title={bool(title)}, ts={ts}) -> descartada")
                continue
            age_min = (self.now_fn() - ts) / 60.0
            if age_min > self.max_age_min:
                continue    # vieja: lista lateral o ya cubierta por el RSS
            entry = {"title": title, "link": url, "summary": summary,
                     "published_parsed": time.gmtime(ts)}
            news = self.ff._extract_news(entry, "Forexlive home")
            if news:
                items.append(news)
                self.logger.info(f"home-fast: NUEVA a {age_min:.1f} min de publicada: "
                                 f"{title[:70]}")
        return items
