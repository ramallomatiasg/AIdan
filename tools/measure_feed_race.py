"""measure_feed_race.py - CARRERA DE FEEDS contra el calendario economico.

Paso 2 del plan del 26-ago-2026. Responde UNA pregunta con datos en vez de con
una corazonada:

    cuando sale un dato economico, QUE feed lo publica primero y a cuantos
    minutos del release?

── Por que hace falta ────────────────────────────────────────────────────────
El 26-ago se midio el trade #931 (PUT sobre el Core PCE) y salio que AIdan entro
29,7 min despues del dato. El desglose: 25,3 min los tardo Bloomberg en publicar,
4,3 min el poll del RSS, 10 SEGUNDOS el LLM y 2 segundos la orden. O sea el
cuello no es AIdan: es la fuente.

Y el problema es peor que "Bloomberg es lento": de las 76 noticias que gatillaron
operacion en 7 dias, 74 no correspondian a NINGUN evento del calendario (son
notas de opinion, entrevistas y color de mercado). Las 2 que si eran datos duros
llegaron a 29,5 y 29,1 min. El feed de Bloomberg markets es un feed de notas y
videos, no un cable de datos.

Elegir la fuente de reemplazo por "cual publica mas rapido en general" seria
adivinar: un feed que publica 149 items/hora de transcripts de earnings tiene el
item mas nuevo siempre fresco y no reporta un dato NUNCA. Lo unico que importa es
la latencia contra el RELEASE del calendario. Eso es lo que mide este script.

── Que hace ──────────────────────────────────────────────────────────────────
1. Baja el calendario de ForexFactory (thisweek.json) y se queda con los eventos
   USD/EUR de impacto High/Medium. De ahi sale la hora exacta del release.
2. Poleea N feeds candidatos cada CYCLE_SEC segundos y registra CADA item nuevo
   (por URL) con su published_at y el momento en que este script lo vio.
3. Para cada item, intenta matchearlo contra un evento del calendario cuyo
   release ya paso. Si matchea, calcula:
       lag_publicacion = published_at - hora_del_release   <- culpa de la FUENTE
       lag_deteccion   = visto_en      - published_at      <- culpa del POLL
       lag_total       = visto_en      - hora_del_release
4. Al final imprime el ranking por fuente: cuantos eventos reporto, la mediana de
   lag_total, y quien llego primero en cada evento.

── Aislamiento (importante) ──────────────────────────────────────────────────
NO toca la base de produccion. Escribe en su propio archivo:
    %APPDATA%/AIdan/state/feed_race.db
Es read-only respecto de AIdan: no crea alerts, no crea estrategias, no manda
ordenes. Se puede correr con AIdan prendido o apagado.

── Limites declarados ────────────────────────────────────────────────────────
* El matcheo titulo<->evento es por palabras clave (`EVENT_KEYWORDS`). Va a
  perder notas que hablen del dato con otras palabras => los conteos por fuente
  son una COTA INFERIOR. Lo que el script compara honestamente es la misma
  metrica entre fuentes, no el total absoluto.
* `published_at` lo pone el publisher y puede mentir (algunos backdatean o usan
  la hora de la ultima edicion). Por eso se reportan las DOS mitades separadas:
  si una fuente tiene lag_publicacion negativo, su fecha no es confiable y se
  marca.
* thisweek.json NO trae el campo `actual` (verificado 26-ago): sirve para la HORA
  del release y el forecast, no para el numero publicado.
* Una corrida de pocas horas no alcanza. Hacen falta varios dias con eventos
  High. El 28-ago 11:00 AR hay dos (Fed Chairman Warsh Speaks + Prelim Benchmark
  Payrolls Revision).

── Uso ───────────────────────────────────────────────────────────────────────
    python tools/measure_feed_race.py --hours 8        # poleear 8 horas y reportar
    python tools/measure_feed_race.py --report         # solo reportar lo ya juntado
    python tools/measure_feed_race.py --dry-run        # 1 ciclo, no escribe nada
    python tools/measure_feed_race.py --list-events    # eventos de la semana

Env: FEED_RACE_CYCLE_SEC (default 30)

── Modo --home-race (5-oct-2026): HOME vs RSS del MISMO publisher ─────────────
Otra pregunta, no la de arriba. Medido el 5-oct sobre `news` (desde el 27-ago):
Forexlive (que ahora redirige a investinglive.com) llega con mediana 5,3 min y
p90 77 min entre publicacion y deteccion, con el collector poleando cada 60 s.
La causa NO es AIdan: el CDN cachea el RSS con `s-maxage=300,
stale-while-revalidate=3600` (se vio una copia de 574 s) y ignora query strings
y `Cache-Control: no-cache`. La HOME del sitio se cachea con `s-maxage=30,
stale-while-revalidate=60` y lista los mismos titulares.

    ¿la home muestra cada nota ANTES que el RSS, y por cuanto?

Cada HOME_RACE_CYCLE_SEC (default 15) baja el RSS y la home, y registra cuando
cada canal mostro cada nota por primera vez. Las notas presentes en el 1er ciclo
son linea de base y NO puntuan (no se sabe cuando aparecieron).

CRITERIO PRE-DECLARADO (5-oct, antes de correrlo — NO mover):
  n >= 20 notas que aparecieron NUEVAS en los dos canales durante la corrida y
  mediana de la ventaja (visto_rss - visto_home) >= 3 min  =>  la home vale la
  pena como fuente rapida del collector. Si no, el RSS queda como esta.
Limite: es una sola publicacion; la ventaja depende del CDN de ellos y puede
cambiar sin aviso. Los links de la home incluyen listas laterales ("mas leidas")
⇒ solo puntuan notas que el RSS tambien trae con fecha.

    python tools/measure_feed_race.py --home-race --hours 3
    python tools/measure_feed_race.py --home-report

Env: HOME_RACE_CYCLE_SEC (default 15)
"""

import argparse
import datetime as dt
import os
import sqlite3
import statistics
import sys
from collections import defaultdict

try:
    import feedparser
    import requests
except ImportError as e:
    print(f"Falta una dependencia: {e}")
    sys.exit(1)

# ── Candidatos ───────────────────────────────────────────────────────────────
# Medidos en vivo el 26-ago-2026. La columna items/hora es la tasa de
# publicacion, que NO es lo que decide: esta aca para leer el resultado con
# contexto (una fuente con tasa altisima y 0 eventos reportados es ruido).
CANDIDATES = [
    # (nombre,             url,                                                      items/hora medidos)
    ("Bloomberg",          "https://feeds.bloomberg.com/markets/news.rss",           1.1),
    ("FXStreet",           "https://www.fxstreet.com/rss/news",                      4.5),
    ("Investing Economy",  "https://www.investing.com/rss/news_14.rss",             10.0),
    ("Investing Forex",    "https://www.investing.com/rss/news_1.rss",               0.3),
    ("Investing News",     "https://www.investing.com/rss/news.rss",               149.3),
    ("MarketWatch",        "https://feeds.content.dowjones.io/public/rss/mw_topstories", 16.9),
    ("Forexlive",          "https://www.forexlive.com/feed",                         2.0),
    ("Forexlive news",     "https://www.forexlive.com/feed/news",                    0.9),
    ("Forexlive CB",       "https://www.forexlive.com/feed/centralbank",             0.5),
]

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Palabras clave por familia de evento. La clave se busca EN EL TITULO de la nota
# Y en el titulo del evento del calendario: si las dos lo tienen, es un match.
# Lista deliberadamente conservadora: preferimos perder matches antes que inventar
# uno (un falso match arruina la mediana de latencia, que es todo el resultado).
EVENT_KEYWORDS = [
    "pce", "cpi", "gdp", "nonfarm", "payroll", "unemployment", "jobless",
    "claims", "retail sales", "consumer confidence", "consumer sentiment",
    "inflation expectations", "ppi", "durable goods", "ism", "pmi",
    "trade balance", "housing starts", "building permits", "new home sales",
    "existing home sales", "factory orders", "industrial production",
    "fomc", "rate decision", "interest rate", "powell", "warsh", "lagarde",
    "ecb", "beige book", "jolts", "adp", "core pce",
]

CYCLE_SEC = int(os.getenv("FEED_RACE_CYCLE_SEC", "30"))
AR_TZ = dt.timezone(dt.timedelta(hours=-3))


# ── Persistencia (archivo propio, NUNCA la DB de produccion) ─────────────────
def _db_path():
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "AIdan", "state")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "feed_race.db")


def _init_db(path):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feed_items (
            url            TEXT PRIMARY KEY,
            source         TEXT NOT NULL,
            title          TEXT,
            published_at   TEXT,      -- UTC naive ISO, tal como lo da el feed
            seen_at        TEXT NOT NULL,  -- UTC naive ISO, cuando ESTE script lo vio
            matched_event  TEXT,
            event_time     TEXT,      -- UTC naive ISO del release
            event_impact   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fi_src ON feed_items(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fi_evt ON feed_items(matched_event)")
    conn.commit()
    return conn


# ── Calendario ───────────────────────────────────────────────────────────────
def fetch_calendar():
    """Eventos USD/EUR High/Medium de la semana, con la hora del release en UTC."""
    resp = requests.get(FF_URL, headers={"User-Agent": _UA}, timeout=20)
    resp.raise_for_status()
    out = []
    for e in resp.json():
        if e.get("country") not in ("USD", "EUR"):
            continue
        if e.get("impact") not in ("High", "Medium"):
            continue
        try:
            t = dt.datetime.fromisoformat(e["date"])  # tz-aware
        except Exception:
            continue
        utc = t.astimezone(dt.timezone.utc).replace(tzinfo=None)
        out.append({
            "title": e["title"],
            "utc": utc,
            "impact": e["impact"],
            "country": e.get("country"),
            "forecast": e.get("forecast", ""),
            "previous": e.get("previous", ""),
        })
    out.sort(key=lambda x: x["utc"])
    return out


def match_event(title, published_utc, events, max_lag_min=240):
    """Evento del calendario al que se refiere la nota, o None.

    Regla: el release tiene que haber pasado ANTES de la publicacion (una nota no
    puede reportar un numero que todavia no salio) y no hace mas de max_lag_min.
    Entre varios candidatos gana el mas cercano en el tiempo.
    """
    if not published_utc:
        return None
    tl = (title or "").lower()
    kws = [k for k in EVENT_KEYWORDS if k in tl]
    if not kws:
        return None
    best = None
    for ev in events:
        if ev["utc"] > published_utc:
            continue
        lag = (published_utc - ev["utc"]).total_seconds() / 60
        if lag > max_lag_min:
            continue
        evl = ev["title"].lower()
        if not any(k in evl for k in kws):
            continue
        if best is None or lag < best[0]:
            best = (lag, ev)
    return best[1] if best else None


# ── Poll ─────────────────────────────────────────────────────────────────────
def _entry_published_utc(entry):
    from calendar import timegm
    for attr in ("published_parsed", "updated_parsed"):
        pp = entry.get(attr)
        if pp:
            try:
                return dt.datetime.utcfromtimestamp(timegm(pp))
            except Exception:
                continue
    return None


def poll_once(conn, events, dry_run=False, verbose=False):
    """Un ciclo sobre todos los candidatos. Devuelve (nuevos, matches_nuevos)."""
    now = dt.datetime.utcnow()
    nuevos = 0
    matches = []
    for name, url, _rate in CANDIDATES:
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": _UA})
            feed = feedparser.parse(resp.content)
            entries = list(feed.entries)
        except Exception as e:
            print(f"  [{name}] error: {e}")
            continue
        if not entries:
            print(f"  [{name}] 0 entries (HTTP {getattr(resp, 'status_code', '?')})")
            continue
        for entry in entries:
            link = entry.get("link", "")
            if not link:
                continue
            title = entry.get("title", "")
            pub = _entry_published_utc(entry)
            ev = match_event(title, pub, events)
            if dry_run:
                if ev:
                    matches.append((name, title, pub, ev))
                continue
            try:
                cur = conn.execute(
                    "INSERT INTO feed_items (url, source, title, published_at, seen_at,"
                    " matched_event, event_time, event_impact) VALUES (?,?,?,?,?,?,?,?)",
                    (link, name, title,
                     pub.isoformat() if pub else None,
                     now.isoformat(),
                     ev["title"] if ev else None,
                     ev["utc"].isoformat() if ev else None,
                     ev["impact"] if ev else None))
                if cur.rowcount:
                    nuevos += 1
                    if ev:
                        matches.append((name, title, pub, ev))
                        lag = (pub - ev["utc"]).total_seconds() / 60
                        print(f"  >> MATCH [{name}] +{lag:.1f}min de '{ev['title']}' :: {title[:60]}")
                    elif verbose:
                        print(f"     [{name}] {title[:70]}")
            except sqlite3.IntegrityError:
                pass  # ya visto
        conn.commit() if not dry_run else None
    return nuevos, matches


# ── Reporte ──────────────────────────────────────────────────────────────────
def report(conn):
    rows = conn.execute("""
        SELECT source, title, published_at, seen_at, matched_event, event_time, event_impact
        FROM feed_items WHERE matched_event IS NOT NULL
    """).fetchall()

    tot = conn.execute("SELECT source, COUNT(*) FROM feed_items GROUP BY source").fetchall()
    print("\n" + "=" * 78)
    print("CARRERA DE FEEDS - items juntados por fuente")
    print("=" * 78)
    rate = {n: r for n, _u, r in CANDIDATES}
    for src, n in sorted(tot, key=lambda x: -x[1]):
        print(f"  {src:20} {n:6} items   (tasa medida 26-ago: {rate.get(src, '?')}/hora)")

    if not rows:
        print("\nTodavia NINGUN item matcheo un evento del calendario.")
        print("Eso ya es informacion: significa que ninguna de estas fuentes reporto")
        print("un dato en la ventana medida. Dejarlo corriendo sobre un dia con")
        print("eventos High (mirar --list-events).")
        return

    per_src = defaultdict(list)
    per_event = defaultdict(list)
    fecha_rara = set()
    for src, title, pub, seen, ev, evt, imp in rows:
        try:
            p = dt.datetime.fromisoformat(pub) if pub else None
            s = dt.datetime.fromisoformat(seen)
            e = dt.datetime.fromisoformat(evt)
        except Exception:
            continue
        if p is None:
            continue
        lag_pub = (p - e).total_seconds() / 60
        lag_det = (s - p).total_seconds() / 60
        lag_tot = (s - e).total_seconds() / 60
        if lag_pub < 0:
            fecha_rara.add(src)
            continue
        per_src[src].append((lag_pub, lag_det, lag_tot))
        per_event[(ev, imp)].append((src, lag_pub, lag_tot, title))

    print("\n" + "=" * 78)
    print("LATENCIA CONTRA EL RELEASE (lo unico que decide)")
    print("=" * 78)
    print(f"{'fuente':20} {'eventos':>8} {'FUENTE':>9} {'POLL':>7} {'TOTAL':>8}")
    print(f"{'':20} {'':>8} {'med.min':>9} {'med.min':>7} {'med.min':>8}")
    ranking = []
    for src, v in per_src.items():
        med_pub = statistics.median(x[0] for x in v)
        med_det = statistics.median(x[1] for x in v)
        med_tot = statistics.median(x[2] for x in v)
        ranking.append((med_tot, src, len(v), med_pub, med_det))
    for med_tot, src, n, med_pub, med_det in sorted(ranking):
        print(f"  {src:18} {n:8} {med_pub:9.1f} {med_det:7.1f} {med_tot:8.1f}")
    if fecha_rara:
        print(f"\n  ⚠️ fechas de publicacion no confiables (lag negativo, descartadas): "
              f"{', '.join(sorted(fecha_rara))}")

    print("\n" + "=" * 78)
    print("QUIEN LLEGO PRIMERO, EVENTO POR EVENTO")
    print("=" * 78)
    for (ev, imp), lst in sorted(per_event.items(), key=lambda x: min(y[2] for y in x[1])):
        lst.sort(key=lambda x: x[2])
        src, lag_pub, lag_tot, title = lst[0]
        otras = ", ".join(f"{s} +{lt:.0f}" for s, _lp, lt, _t in lst[1:4])
        print(f"\n  [{imp}] {ev}")
        print(f"    1ro: {src} a +{lag_tot:.1f} min   ({title[:56]})")
        if otras:
            print(f"    despues: {otras}")

    print("\n" + "=" * 78)
    print("COMO LEER ESTO")
    print("=" * 78)
    print("  * Columna FUENTE = cuanto tarda el publisher en escribir. No se puede bajar")
    print("    cambiando codigo: es la unica razon por la que se cambia de fuente.")
    print("  * Columna POLL = cuanto tarda en verlo quien poleea. Se baja con CYCLE_SEC.")
    print("  * El research dice que ~80% del movimiento post-dato pasa en 3 MINUTOS.")
    print("    Una fuente con TOTAL > 5 min no sirve para operar el dato, por mas que")
    print("    sea la mas rapida del ranking. Si NINGUNA baja de ~5 min, la conclusion")
    print("    honesta es que el camino RSS no existe y hay que ir por el calendario")
    print("    (armar la orden ANTES del release), no por la noticia.")
    print("  * Una fuente con muchos items y 0 eventos reportados es ruido, no velocidad.")


# ── Modo --home-race: home vs RSS del mismo publisher ────────────────────────
HOME_URL = "https://investinglive.com/"
HOME_RSS = "https://investinglive.com/feed"
HOME_RACE_CYCLE_SEC = int(os.getenv("HOME_RACE_CYCLE_SEC", "15"))
HOME_MIN_N = 20
HOME_MIN_LEAD_MIN = 3.0


def _news_path(url):
    """'/news/slug' normalizado (sin dominio ni barra final), o None."""
    import re
    m = re.search(r"(/news/[a-z0-9\-]+)", url or "")
    return m.group(1) if m else None


def _home_paths(html):
    import re
    return list(dict.fromkeys(re.findall(r"/news/[a-z0-9\-]+", html or "")))


def _init_home_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS home_race (
            run_id        TEXT NOT NULL,
            path          TEXT NOT NULL,
            channel       TEXT NOT NULL,   -- 'rss' | 'home'
            seen_at       TEXT NOT NULL,   -- UTC naive ISO
            baseline      INTEGER NOT NULL, -- 1 = ya estaba en el 1er ciclo
            published_at  TEXT,            -- UTC naive ISO (solo del RSS)
            cdn_age       INTEGER,         -- header Age del RSS al verla
            PRIMARY KEY (run_id, path, channel)
        )
    """)
    conn.commit()


def home_poll_once(conn, run_id, baseline):
    now = dt.datetime.utcnow().isoformat()
    vistos = {"rss": 0, "home": 0}
    for channel, url in (("rss", HOME_RSS), ("home", HOME_URL)):
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": _UA})
        except Exception as e:
            print(f"  [{channel}] error: {e}")
            continue
        if resp.status_code != 200:
            print(f"  [{channel}] HTTP {resp.status_code}")
            continue
        rows = []
        if channel == "rss":
            age = resp.headers.get("Age")
            for entry in feedparser.parse(resp.content).entries:
                p = _news_path(entry.get("link", ""))
                pub = _entry_published_utc(entry)
                if p:
                    rows.append((p, pub.isoformat() if pub else None,
                                 int(age) if age and age.isdigit() else None))
        else:
            rows = [(p, None, None) for p in _home_paths(resp.text)]
        if not rows:
            print(f"  [{channel}] 0 notas (cambio el formato del sitio?)")
        for p, pub, age in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO home_race VALUES (?,?,?,?,?,?,?)",
                (run_id, p, channel, now, 1 if baseline else 0, pub, age))
            if cur.rowcount and not baseline:
                vistos[channel] += 1
                print(f"  NEW [{channel}] {p[6:76]}")
    conn.commit()
    return vistos


def home_report(conn):
    _init_home_table(conn)
    rows = conn.execute("""
        SELECT h.run_id, h.path, h.seen_at, r.seen_at, r.published_at, r.cdn_age
        FROM home_race h JOIN home_race r
          ON r.run_id = h.run_id AND r.path = h.path AND r.channel = 'rss'
        WHERE h.channel = 'home' AND h.baseline = 0 AND r.baseline = 0
    """).fetchall()
    solo = conn.execute("""
        SELECT channel, COUNT(*) FROM home_race x WHERE baseline = 0 AND NOT EXISTS (
            SELECT 1 FROM home_race y WHERE y.run_id = x.run_id AND y.path = x.path
              AND y.channel <> x.channel)
        GROUP BY channel""").fetchall()
    runs = conn.execute("SELECT COUNT(DISTINCT run_id) FROM home_race").fetchone()[0]

    print("\n" + "=" * 78)
    print(f"HOME vs RSS (investinglive) - {runs} corrida(s)")
    print("=" * 78)
    leads, pub_rss, pub_home = [], [], []
    for _run, path, h_seen, r_seen, pub, age in rows:
        h, r = dt.datetime.fromisoformat(h_seen), dt.datetime.fromisoformat(r_seen)
        lead = (r - h).total_seconds() / 60
        leads.append(lead)
        txt = f"  ventaja home {lead:+6.1f} min"
        if pub:
            p = dt.datetime.fromisoformat(pub)
            pub_rss.append((r - p).total_seconds() / 60)
            pub_home.append((h - p).total_seconds() / 60)
            txt += f" | pub->rss {pub_rss[-1]:5.1f} | pub->home {pub_home[-1]:5.1f}"
        print(f"{txt} | age={age if age is not None else '-':>4} | {path[6:50]}")
    for ch, n in solo:
        print(f"  solo en {ch} (no puntua): {n}")
    # Home ya la tenia en la linea de base y el RSS la mostro DESPUES: la ventaja es
    # al menos (visto_rss - inicio de la corrida). Censurada => se informa aparte y
    # NO entra en el criterio.
    cens = conn.execute("""
        SELECT r.seen_at, (SELECT MIN(seen_at) FROM home_race z WHERE z.run_id = r.run_id)
        FROM home_race r JOIN home_race h
          ON h.run_id = r.run_id AND h.path = r.path AND h.channel = 'home'
        WHERE r.channel = 'rss' AND r.baseline = 0 AND h.baseline = 1
    """).fetchall()
    if cens:
        mins = [(dt.datetime.fromisoformat(a) - dt.datetime.fromisoformat(b)).total_seconds() / 60
                for a, b in cens]
        print(f"  home ya la tenia al arrancar y el RSS la mostro despues: {len(cens)} "
              f"(ventaja >= {statistics.median(mins):.1f} min de mediana, censurada, no puntua)")

    n = len(leads)
    print("\n" + "-" * 78)
    if not n:
        print("Ninguna nota nueva vista en los dos canales todavia.")
        return
    med = statistics.median(leads)
    print(f"n={n}  mediana ventaja home={med:+.1f} min  "
          f"home primero en {sum(l > 0 for l in leads)}/{n}  "
          f"rss primero en {sum(l < 0 for l in leads)}/{n}")
    if pub_rss:
        print(f"publicacion->deteccion  RSS mediana {statistics.median(pub_rss):.1f} min  "
              f"| HOME mediana {statistics.median(pub_home):.1f} min")
    print(f"\nCRITERIO PRE-DECLARADO: n>={HOME_MIN_N} y mediana >= {HOME_MIN_LEAD_MIN:.0f} min")
    if n < HOME_MIN_N:
        print(f"  -> SIN VEREDICTO (n={n} < {HOME_MIN_N}): seguir juntando, no concluir.")
    elif med >= HOME_MIN_LEAD_MIN:
        print("  -> PASA: la home vale la pena como fuente rapida del collector.")
    else:
        print("  -> NO PASA: el RSS queda como esta.")


def run_home_race(conn, hours):
    import time
    _init_home_table(conn)
    run_id = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    fin = dt.datetime.utcnow() + dt.timedelta(hours=hours)
    print(f"home-race {run_id}: cada {HOME_RACE_CYCLE_SEC}s hasta "
          f"{(fin + dt.timedelta(hours=-3)).strftime('%H:%M')} AR")
    v = home_poll_once(conn, run_id, baseline=True)
    base = conn.execute("SELECT channel, COUNT(*) FROM home_race WHERE run_id=? GROUP BY channel",
                        (run_id,)).fetchall()
    print(f"  linea de base (no puntua): {dict(base)}")
    try:
        while dt.datetime.utcnow() < fin:
            time.sleep(HOME_RACE_CYCLE_SEC)
            home_poll_once(conn, run_id, baseline=False)
    except KeyboardInterrupt:
        print("\ncortado a mano")
    home_report(conn)


def main():
    ap = argparse.ArgumentParser(description="Carrera de feeds contra el calendario economico")
    ap.add_argument("--home-race", action="store_true",
                    help="home vs RSS de investinglive (usar con --hours)")
    ap.add_argument("--home-report", action="store_true",
                    help="solo reportar lo juntado por --home-race")
    ap.add_argument("--hours", type=float, default=0,
                    help="cuantas horas poleear (0 = un solo ciclo)")
    ap.add_argument("--report", action="store_true", help="solo reportar lo ya juntado")
    ap.add_argument("--dry-run", action="store_true", help="1 ciclo, sin escribir nada")
    ap.add_argument("--list-events", action="store_true", help="eventos de la semana y salir")
    ap.add_argument("--verbose", action="store_true", help="loguear cada item nuevo")
    args = ap.parse_args()

    path = _db_path()
    conn = _init_db(path)
    print(f"DB del arnes: {path}   (NO es la de produccion)")

    if args.report:
        report(conn)
        return

    if args.home_report:
        home_report(conn)
        return

    if args.home_race:
        run_home_race(conn, args.hours if args.hours > 0 else 0.25)
        return

    events = fetch_calendar()
    print(f"Calendario: {len(events)} eventos USD/EUR High/Medium esta semana")

    if args.list_events:
        now = dt.datetime.utcnow()
        for e in events:
            ar = (e["utc"] + dt.timedelta(hours=-3)).strftime("%a %d %H:%M")
            estado = "ya salio" if e["utc"] <= now else "pendiente"
            print(f"  {ar} AR  [{e['impact']:6}] {e['country']} {e['title'][:44]:44} "
                  f"fc={e['forecast'] or '-':>7}  {estado}")
        return

    if args.dry_run:
        print("\n--dry-run: 1 ciclo, sin escribir")
        _n, m = poll_once(conn, events, dry_run=True, verbose=args.verbose)
        print(f"\nitems que matchearian un evento AHORA: {len(m)}")
        for name, title, pub, ev in m[:20]:
            lag = (pub - ev["utc"]).total_seconds() / 60
            print(f"  [{name}] +{lag:.1f}min '{ev['title']}' :: {title[:55]}")
        return

    if args.hours <= 0:
        print("\nUn ciclo:")
        n, m = poll_once(conn, events, verbose=args.verbose)
        print(f"  items nuevos: {n}, matches nuevos: {len(m)}")
        report(conn)
        return

    import time
    fin = dt.datetime.utcnow() + dt.timedelta(hours=args.hours)
    print(f"Poleeando cada {CYCLE_SEC}s hasta {fin.strftime('%H:%M')} UTC "
          f"({(fin + dt.timedelta(hours=-3)).strftime('%H:%M')} AR). Ctrl+C para cortar.\n")
    ciclo = 0
    try:
        while dt.datetime.utcnow() < fin:
            ciclo += 1
            n, m = poll_once(conn, events, verbose=args.verbose)
            ahora = dt.datetime.utcnow() + dt.timedelta(hours=-3)
            print(f"[{ahora.strftime('%H:%M:%S')} AR ciclo {ciclo}] "
                  f"nuevos={n} matches={len(m)}")
            time.sleep(CYCLE_SEC)
    except KeyboardInterrupt:
        print("\ncortado a mano")
    report(conn)


if __name__ == "__main__":
    main()
