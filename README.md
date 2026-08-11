# AIdan — bot de scalping EUR/USD con IA

Bot de trading automático sobre **EUR/USD**, integrado con **MetaTrader 5** (cuenta demo ICMarkets Raw Spread).
Un solo ejecutable Windows portable: GUI Tkinter + dashboard web en `localhost:8000`.

Analiza noticias financieras con LLMs, escanea estructura de mercado en tres timeframes en paralelo
(M5 / M15 / H1), ejecuta y gestiona las posiciones en MT5, y archiva cada resultado con su contexto
para medirse a sí mismo.

> **Cuenta DEMO.** Este repo no está en dinero real y no es asesoramiento financiero. Ver [Disclaimer](#disclaimer).

---

## Estado

El track record vive en la base de datos, no acá. Para no repetir números que quedan viejos en una
semana, el diagnóstico actualizado (KPIs, qué gana y qué pierde por track, hallazgos abiertos) está en:

| Documento | Qué contiene |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | **La fuente de verdad.** Contexto completo, changelog versión por versión, hilos abiertos, metodología y decisiones con su evidencia. |
| [`AUDIT_REPORT.md`](AUDIT_REPORT.md) | Auditoría por frentes (arquitectura, estrategia, ML, infra, datos) del 31-jul-2026. |
| [`docs/mejora_continua.md`](docs/mejora_continua.md) | El loop semanal: medir → gate de significancia → shadow → activar UNO → re-medir. |
| [`docs/market_playbook.md`](docs/market_playbook.md) | Registro de regímenes de mercado y cómo debería accionar AIdan en cada uno. |

Consulta rápida del estado en vivo:

```bash
curl -s http://localhost:8000/version
curl -s http://localhost:8000/mt5/status
curl -s http://localhost:8000/performance
```

---

## Instalación

### Usuario final

1. Ejecutar `AIdan.exe`
2. Se abre solo el dashboard en `http://localhost:8000`
3. Cargar credenciales MT5 en el panel de configuración

**Requisitos:** Windows 10/11, 4 GB de RAM, MetaTrader 5 instalado, conexión a internet.

### Desarrollo

```bash
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan
pip install -r requirements.txt
python AIdan_TodoEnUno.py
```

Necesita `GROQ_API_KEY` ([Groq](https://console.groq.com/), free tier). Copiar `.env.example` a `.env`.

**Opcional:** [Ollama](https://ollama.com/) con `qwen2.5:7b` para el pre-filtro de noticias, la auditoría de
señales y el análisis post-trade. Sin Ollama el bot funciona igual, con degradación graceful.

---

## Cómo funciona

Un solo proceso levanta cinco threads:

| Thread | Cada | Qué hace |
|---|---|---|
| **Collector** | 10 min | Baja noticias financieras por RSS a SQLite. |
| **Analyzer** | 10 s | El ciclo principal: noticias → LLM, estructura M5/M15/H1, SMC, pre-plans, evaluación de estrategias vencidas. |
| **API** | — | FastAPI: dashboard + endpoints (`localhost:8000`). |
| **Trailing monitor** | 1 s | Break-even y trailing stop sobre las posiciones abiertas. |
| **Position Manager** | 15 s | Decide `HOLD` / `CLOSE_PROFIT` / `CLOSE_PROTECT` / `CLOSE_MAXHOLD` sobre lo que está vivo. |

### Los cinco orígenes de señal (`trigger_type`)

| Trigger | Origen | Timeframe |
|---|---|---|
| `structure` | Breakout / breakdown / continuación sobre niveles (`technical.py`) | M5 |
| `m15_structure` | La misma lógica sobre velas M15 | M15 |
| `h1_structure` | La misma lógica sobre velas H1 | H1 |
| `smc` | Smart Money Concepts: zonas de oferta/demanda multi-TF con confirmación | M5 sobre H1/M15 |
| `news` | Scoring de noticias con LLM (dirección + confianza) | reactivo |
| `pre_planned` | Plan pre-mercado del LLM sobre el calendario económico | agendado |

M15 y H1 son **subclases** del analizador M5: comparten el cerebro y solo cambian el feed de velas y el
perfil (SL/TP/expiry/ATR floor). Eso importa: un bug en la lógica compartida afecta a los tres.

### Cómo se decide

Cada señal atraviesa una cadena de filtros antes de convertirse en orden — warmup gates, pisos y techos
de ATR, mínimo y techo de confianza, anti-alineación total (`SIM A`), cooldown post-pérdida,
anti-contradicción, horario de mercado. La lista viva de filtros activos, con la evidencia que justifica
cada uno y los que se **removieron por evidencia contaminada**, está en `CLAUDE.md`.

SL y TP se adaptan al ATR con piso y techo por perfil; el tamaño del lote sale del riesgo en dólares
(`lote = riesgo$ / (SL × 10)`), así que **el SL no define la pérdida — la define el % de riesgo**.

---

## Arquitectura

```
AIdan_TodoEnUno.py          Monolito: GUI Tkinter + los 5 threads + orquestación
AIdan.spec                  Build de PyInstaller
dashboard_multi_theme.html  Dashboard web (3 tabs, tema claro/oscuro)
src/
  analyzer/                 technical.py · technical_m15/h1 · smc.py · news_analyzer.py
                            pre_planner.py · llm_auditor.py · post_trade_analyzer.py
  broker/                   mt5_executor.py (órdenes, BE, trailing) · price_feed.py
  common/                   config.py (APP_VERSION, env) · db.py (SQLite) · db_backup.py
                            logging_setup.py · event_window.py · telegram_*
  optimizer/                auto_tuner.py · significance.py · shadow_runner.py
                            change_manager.py · auto_applier.py · sim_engine.py
  admin/main.py             FastAPI: dashboard + API
  cloud/, reports/          Aprendizaje compartido · reporte a Google Sheets
tools/                      Medidores read-only, tests y utilidades standalone (ver CLAUDE.md)
tests/                      Suite pytest (75 tests)
docs/                       Playbook de regímenes + plan de mejora continua
config/sources.yaml         Fuentes RSS
static/                     Ícono e imágenes del dashboard
```

### Datos

Todo vive fuera del repo, en `%APPDATA%/AIdan/`:

```
state/financial_news.db   SQLite: news, alerts, auto_strategies, trade_archive,
                          learning_insights, position_manager_log, shadows…
logs/aidan.log            Log rotativo (10 MB × 5)
backups/                  Backup diario de la DB (rota a 7)
data/YYYY/MM/DD/HH/       News crudas por hora
```

Dos tablas mandan: **`auto_strategies`** es el estado vivo (buffer rotativo de 6 filas) y
**`trade_archive`** es el histórico permanente. `trade_archive` solo acepta trades que **llegaron al
broker** — toda medición de plata filtra `mt5_pnl IS NOT NULL`, que es la verdad del broker, nunca un
resultado calculado por precio.

---

## Desarrollo

### Ciclo edit → rebuild → verificar

```powershell
taskkill /F /IM AIdan.exe
pyinstaller --clean --noconfirm AIdan.spec
Start-Process -FilePath "dist\AIdan.exe" -WindowStyle Hidden
(Invoke-WebRequest -Uri "http://localhost:8000/version" -UseBasicParsing).Content
```

**Rebuildear con el mercado abierto cuesta la rueda:** cada arranque resetea los warmup gates
(M5 10 min · M15 30 min · H1 60 min) y m15 es el track que más opera. Conviene juntar cambios y hacer
un solo rebuild, preferentemente fuera de sesión.

### Tests

```bash
python -m pytest tests/ -q          # suite (75 tests)
python tools/test_<nombre>.py       # tests puntuales por versión
```

Los tests de `tools/` corren contra una **DB temporal**, nunca contra producción. Si escribís uno nuevo
que ejercite código real, apuntá `db.DB_PATH` y `db._connect` a un archivo temporal: parchear solo las
funciones que creés que escriben **no alcanza** (ver `test_prod_write_guards_v3536.py`).

### Endpoints útiles

```
/version  /mt5/status  /mt5/positions  /market-state  /structure-status  /smc-state
/auto-strategies?limit=10  /performance  /post-trade-analysis
/what-if  /theme-editor  /meta-optimization  /position-manager
```

---

## Metodología

El proyecto se rige por un principio: **un fix que no arregla nada, EMPEORA.** En un sistema en vivo un
filtro que no separa ganar de perder recorta frecuencia gratis, y un tweak sobre ruido sobreajusta.

Por eso todo cambio de lógica pasa por un gate de significancia adversarial
([`src/optimizer/significance.py`](src/optimizer/significance.py)): se reporta `n`, win rate del subset vs
baseline, p-value binomial e intervalo de Wilson al 95%. **Default = ruido** si `n < 25` o si el CI cruza
el baseline. Las reglas completas, incluida la lección de validar siempre con P&L **real** y nunca con
outcomes simulados, están en `CLAUDE.md`.

Los bugs de código son distintos: se verifican leyendo, no necesitan muestra. `tools/audit_code_patterns.py`
audita automáticamente los siete patrones de bug que ya hicieron daño en este repo.

---

## Licencia

MIT — ver [`LICENSE`](LICENSE).

## Disclaimer

Proyecto personal de investigación sobre una **cuenta demo**. No es asesoramiento financiero ni una
invitación a operar. El trading apalancado puede hacerte perder todo tu capital. Si lo corrés con dinero
real, es bajo tu exclusiva responsabilidad.
