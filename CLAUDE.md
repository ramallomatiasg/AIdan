# CLAUDE.md — Contexto AIdan para asistentes IA

Este archivo es leído automáticamente por Claude Code y otras IAs. Contiene todo lo necesario para trabajar en AIdan correctamente desde el primer turno.

---

## ¿Qué es AIdan?

Bot de trading automático EUR/USD scalping M5, integrado con MetaTrader 5 (cuenta ICMarkets Raw Spread Demo). Single executable Windows portable (~50MB) que corre como GUI Tkinter + dashboard web. Usa LLMs (Groq + Ollama local) para análisis de news, post-trade y estrategias.

**Owner**: Matias Ramallo (Backend & Cloud Engineer, Yalutec, Rosario AR)
**Repo**: github.com/ramallomatiasg/AIdan
**Idioma**: Spanish con el user, inglés en código y commits.

---

## Reglas críticas del user (no negociables)

1. **NO usar `Co-Authored-By: Claude` en commits**. Los commits van directo de la cuenta del user.
2. **REBUILDEAR `AIdan.exe` después de TODA modificación de código**. El user corre desde el exe, no desde python source.
3. **Cuenta demo, NO real**. Migración a real solo bajo criterios definidos en `~/.claude/projects/F--AIdan/memory/project_real_account_goal.md`.
4. **Aprobación explícita** antes de cambios significativos. Formato preferido: `Plan / Razón / Pros / Contras / Opinión propia a proceder`.
5. **No simular soluciones con muestra <6 trades**. Histórico mostró que filtros agregados con muestra chica fueron contraproducentes (hour gate, late breakout 3p — ambos removidos).

---

## Arquitectura

### Layout

```
F:/AIdan/
├── AIdan_TodoEnUno.py        # Monolito principal (3500+ lines): GUI + analyzer + admin
├── AIdan.spec                # PyInstaller spec
├── start_aidan.bat           # Launcher (Task Scheduler 4 AM AR)
├── dist/AIdan.exe            # Binario producción (~50MB)
├── src/
│   ├── analyzer/
│   │   ├── technical.py            # Structure scanner + market state + adaptive SL/TP
│   │   ├── news_analyzer.py        # Groq + Gemma news scoring
│   │   ├── pre_planner.py          # Pre-market planner LLM
│   │   ├── llm_auditor.py          # Gemma signal audit
│   │   ├── post_trade_analyzer.py  # Gemma post-trade lessons (estructura SL/TP advice v3.15)
│   │   └── smc.py                  # Smart Money Concepts (multi-TF)
│   ├── broker/
│   │   ├── mt5_executor.py    # Orden execution + trailing + BE
│   │   └── price_feed.py      # Candle fetching MT5/Yahoo
│   ├── common/
│   │   ├── config.py          # APP_VERSION + env vars + Groq keys
│   │   └── db.py              # SQLite + learning_adjustments aggregation
│   ├── admin/main.py          # FastAPI dashboard (port 8000)
│   └── optimizer/auto_tuner.py # AutoTuner params iteration
├── tools/                    # Scripts standalone (sims, audits, benchmarks)
└── config/                   # YAML/JSON configs runtime
```

### Datos persistentes

```
%APPDATA%/AIdan/state/
├── financial_news.db    # SQLite — TODA la data (alerts, auto_strategies, trade_archive, learning_insights, etc)
├── aidan.db             # Legacy, pequeña
└── learning_insights_backup_*.csv

%APPDATA%/AIdan/data/YYYY/MM/DD/HH/news.jsonl   # News raw por hora
%APPDATA%/AIdan/config/                          # Copy of config dir from exe
%APPDATA%/AIdan/templates/                       # Copy of templates from exe
```

### Tablas SQLite clave

| Tabla | Propósito |
|---|---|
| `auto_strategies` | Trades activos/cerrados (live state) |
| `trade_archive` | Trades cerrados archivados (histórico ML) |
| `news` | News collected |
| `alerts` | LLM analysis de news → CALL/PUT/NEUTRAL |
| `learning_insights` | Patterns aprendidos de Gemma post-trade |
| `optimizer_params` | AutoTuner runtime params (breakout_dist_max, etc) |
| `blocked_setups` | ML-driven blocks |
| `mt5_config` | Kill switch, risk percent, etc |

### Tipos de estrategia (trigger_type)

| Trigger | Origen | Confianza típica |
|---|---|---|
| `news` | LLM news scoring (Groq llama-3.3-70b) | 50-80 |
| `structure` | Breakout/breakdown detection (technical.py) | 60-85 |
| `smc` | Multi-TF supply/demand zones | 65-85 |
| `pre_planned` | LLM pre-market plan | 60-90 |
| `calendar` | Economic calendar trigger | 50-75 |

---

## Comandos clave

### Verificar AIdan corriendo

```powershell
Get-Process -Name "AIdan" -ErrorAction SilentlyContinue
(Invoke-WebRequest -Uri "http://localhost:8000/version" -UseBasicParsing).Content
```

### Ciclo "edit → rebuild → restart"

```powershell
# 1. Edit src/...
# 2. Kill AIdan
taskkill /F /IM AIdan.exe

# 3. Rebuild
cd F:\AIdan
pyinstaller --clean --noconfirm AIdan.spec

# 4. Launch (sin abrir consola)
Start-Process -FilePath "F:\AIdan\dist\AIdan.exe" -WindowStyle Hidden

# 5. Verificar version nueva
Start-Sleep -Seconds 10
(Invoke-WebRequest -Uri "http://localhost:8000/version" -UseBasicParsing).Content
```

### Endpoints API útiles (localhost:8000)

```
GET /version                  # Version actual
GET /mt5/status               # MT5 connection + balance + positions count
GET /mt5/positions            # Open positions
GET /market-state             # Price, trend, RSI, ATR, regime
GET /structure-status         # Scanner state + watching levels
GET /smc-state                # SMC multi-TF + zones
GET /auto-strategies?limit=10 # Last strategies
GET /performance              # WR, PnL, PF
```

### Query DB rápido

```python
import sqlite3, os
db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db)
# ...
```

### Git workflow (sin Co-Authored-By)

```bash
git add <files-explícitos>  # NO usar -A para evitar incluir test files
git commit -m "vX.Y.Z: descripción

Detalle multi-línea sin atribución a Claude."
git push origin main
```

---

## Modelos LLM

### Groq (free tier, cloud)

- `llama-3.3-70b-versatile` — news analysis, pre-planner
- `llama-3.1-8b-instant` — dashboard chat (latencia <500ms)

API keys hardcodeadas en `Config.GROQ_API_KEYS` con rotación. Override via `.env GROQ_API_KEY`.

### Ollama (local, free, GPU 8GB+)

- `qwen2.5:7b` — news pre-filter + signal audit + post-trade analyzer (rebautizado como `GEMMA_MODEL`)

URL: `http://localhost:11434`. Sin Ollama → AIdan usa solo Groq con degradación graceful.

---

## Versiones recientes (changelog top-of-mind)

| Version | Cambio | Estado |
|---|---|---|
| v3.6.3 | Baseline (-$93 sobre 100 trades, PF 0.59) | superada |
| v3.7-3.17 | Filter tuning iterations (ver historial git) | superada |
| v3.18.0 | Late breakout 3→7p (recuperar frecuencia) | superada |
| v3.19.0 | Track B M15 implementado (paralelo M5) | activo |
| v3.20.0 | Track C H1 implementado (paralelo M5+M15) | activo |
| v3.21-3.27 | LLM provider primario, news improvements, etc | superada |
| v3.28.0 | Telegram bot bidireccional + daily loss limit + consensus boost + spread guardian | activo |
| v3.29.x | Dashboard equity curve + heatmap + trade modal + slippage stats + filter contrib | activo |
| v3.30.0 | Performance: 15 DB indexes + cache TTL + polling redundante eliminado | activo |
| v3.30.1 | MTF candle fetch paralelo + news LLM analysis paralelo | activo |
| **v3.30.2** | **Shutdown rapido <2s + LRU cache news + query optimization /auto-strategies** | **actual** |

### Filtros activos (v3.18.0)

```
Warmup gate (10 min tras arrancar)
ATR floor 2.5p
ATR ceiling 6p
Counter-HTF (news regular path requiere conf≥65)
Counter-both (M5+HTF ambos contrarios → block)
SIM A (fully-aligned trades blocked, exhaustion entries)
Min conf 60 (bypass a 30 si impact≥55 y NO counter-HTF)
Conf ceiling 80 (anti-predictive)
Late breakout 7p
AutoTuner setup-type block
ML-driven blocked_setups patterns
Market hours (sesiones activas)
Anti-contradiction pre_planned (no PUT+CALL simultáneos)
```

### Filtros REMOVIDOS por evidencia contaminada (no re-introducir sin data limpia)

- Hour gate UTC 12/14/20 (v3.17.0)
- Late breakout 3p (v3.18.0, ahora 7p)

---

## Estado actual del proyecto (7 May 2026)

### KPIs

- Balance demo: ~$908 (de $1000 inicial = -9% en ~3 semanas)
- WR histórico (142 trades archivo): 35%
- PnL histórico: -$168
- Frecuencia objetivo: 5-10 trades/día
- Frecuencia reciente: 3-5 trades/día (post-filtros)

### Diagnóstico estructural

3 problemas conocidos NO resueltos por filtros:
1. **Comisión = 87% pérdida neta**. Para break-even al WR 41% necesitamos avg win 6p (actualmente 4p).
2. **15-min expiry mata trades direccionalmente correctos**. Patrón observado múltiples veces.
3. **Groq mis-interpreta news con frecuencia**. Negaciones de central bank action.

### Próximo checkpoint

**Viernes 8 May 2026**. Decisión sobre:
- Continuar M5 con surgical fixes
- **Migrar a M15** (recomendación open: cambia la math de comisiones + da tiempo al setup)
- Quitarle a news el rol de trigger directional

---

## Plan triple-track (decidido 7-8 May 2026)

### Track A — M5 (mantenimiento)

- Continúa la línea v3.18.x con la versión actual.
- Solo fixes surgical, sin cambios estructurales.
- Sigue usando trigger_types: `news`, `structure`, `smc`, `pre_planned`, `calendar`.

## Roadmap aprobado 8 May 2026 (multi-cuenta / multi-moneda / dinero real)

Plan completo en `~/.claude/plans/sorted-meandering-pizza.md`. Resumen:

**Fase 1 (próximas 3-4 semanas)**: validación demo. Dejar M5+M15+H1 corriendo sin tocar arquitectura. Acumular 30+ trades por track. Decisión basada en PF + frecuencia + comisión-drag.

**Fase 2 (1-3 meses post Fase 1)**: cuenta real con TODOS los tracks que pasen PF >1.2. Si los 3 califican → operar los 3 (M5 explosivos, M15 sostenidos, H1 macro = patrones complementarios, NO competidores). Lote 0.01 por track. Risk: max 4 posiciones total, lote dividido entre tracks rentables.

**Fase 3 (6+ meses post real)**: escalar — multi-cuenta (5-7 días refactor) o multi-moneda (2-3 semanas + research por par) o profesionalizar como sistema único.

**Bloqueos actuales**: PF 0.48 (target >1.3), comisión 87% del drag M5, hardcoding EUR/USD en 104 sitios. NO escalar hasta demostrar rentabilidad en demo.

### Track C — H1 (experimental) — IMPLEMENTADO v3.20.0 (8 May 2026)

**Profile H1**:
- SL: 40p, TP: 100p, expiry: 180min (3h)
- min_confidence: 60
- ATR floor: 10p
- Frecuencia esperada: 1-2 trades/día

**trigger_type**: `h1_structure`

**Por qué H1 también**:
- Comisión 0.7p / avg win esperado 30p = **2% drag** (vs 17% M5)
- Cuenta demo, sin riesgo real, stats segregadas
- Más data > menos data para decidir el mejor timeframe

**Loop H1**: cada 5 min (`H1_SCAN_INTERVAL = 300`). H1 candles cambian cada hora.

**UI elementos H1**:
- Botón filtro `🌐 H1 (beta)` violeta
- Badge violeta `🌐 H1 STRUCT` en cards
- Chip header `🌐 H1 NW/NL · X act`
- Tercera card en panel comparativo "Triple Track"

### Track B — M15 (experimental, paralelo) — IMPLEMENTADO v3.19.0 (7 May 2026)

**Implementación**:

| Día | Componente | Archivos |
|---|---|---|
| 1 | `TechnicalAnalyzerM15` subclass + test standalone | `src/analyzer/technical_m15.py`, `tools/test_m15_feed.py` |
| 2 | Loop M15 paralelo en analyzer (cada 60s) | `AIdan_TodoEnUno.py` |
| 3 | UI: filtro `M15`, badge dorado en cards, chip stats | `dashboard_multi_theme.html` |
| 4 | Endpoint `/strategy-performance-by-track` + panel comparativo | `src/admin/main.py`, `src/common/db.py` |
| 5 | Verdict robusto + banner alert "M15 supera M5" | `dashboard_multi_theme.html` |

**Profile M15** (constante en `technical_m15.py:M15_PROFILE`):
- SL: 15p, TP: 60p, expiry: 45min
- min_confidence: 60
- Frecuencia: ~1-3 trades/día (M15 candles cambian cada 15min)

**trigger_type**: `m15_structure` (futuro `m15_smc` cuando se agregue)

**Filtros M15** (subset del M5):
- ATR floor 5p (vs M5 2.5p, M15 escala 3x)
- Counter-both (HTF + M5 ambos contrarios → block)
- Conf ceiling 80
- Anti-spam (no opposite activa)
- SIN late breakout (escala distinta), SIN hour gate (ya removido v3.17)

**Criterios de decisión** (en `loadTrackComparison` UI):
- Bajo 10 trades M15: "esperando data"
- 10-14 trades: comparativa preliminar, no decidir
- 15+ trades:
  - **M15 SIGNIFICATIVAMENTE mejor**: PF > 1.0 + PnL positivo + +$20 sobre M5 → banner "considerar migracion"
  - **M15 mejor moderado**: PF > A_PF * 1.3 + PF >= 0.9
  - **M5 mejor**: A_PF > B_PF * 1.3 + A_PF >= 0.9
  - **Empate**: mantener ambos

**UI elementos**:
- Botón filtro `⏰ M15 (beta)` dorado en barra de filtros del tab Estrategias
- Cards M15 con badge dorado `⏰ M15 STRUCT` distintivo
- Chip header `⏰ M15 NW/NL · X act` (auto-hide si 0 trades)
- Panel "Comparativa Dual-Track" con 2 cards lado a lado
- Banner dorado destacado cuando M15 supera M5 significativamente

**Riesgo al M5**: cero. Track B vive en try/except aislado. Si M15 falla, M5 sigue normal.

**Próximos pasos abiertos**:
- M15_PROFILE en DB en lugar de constante (permite ajuste sin rebuild)
- Cuenta demo MT5 separada para Track B (aislamiento total de capital)
- Más trigger types M15 (`m15_smc`)

---

## Glosario de patrones observados

- **Expiry-loss**: trade direccionalmente correcto que cierra por timeout antes de hit TP. Frecuente en M5 con expiry 15min.
- **Catch-the-falling-knife**: AIdan ve un breakdown como "structure breakout" y compra el bottom. SL hit en <2 min.
- **Counter-HTF**: dirección contraria a HTF bias (H1+). Históricamente -EV.
- **Counter-both**: dirección contraria a M5 trend Y HTF bias. Bloqueado.
- **SIM A**: trade fully-aligned (M5+HTF+regime todos en una dirección). Bloqueado por exhaustion entry.
- **Bypass**: news con impact ≥55 puede pasar conf threshold de 30 si NO es counter-HTF.

---

## Tools disponibles en `tools/`

| Script | Propósito |
|---|---|
| `backtest_h1_m15.py` | Backtest estructural-only sobre candles MT5 históricas. Re-corre `detect_structure_signals()` y simula SL/TP/expiry hit. Solo trigger `structure`, sin news/calendar/pre_planned/smc-live. |
| `backtest_parallel.py` | Backtest paralelo de combinaciones de filtros sobre `trade_archive` (trades ya ejecutados). |
| `backtest_weekly.py` | Wrapper semanal de `backtest_parallel.py` con notificación Telegram. |
| `test_m15_feed.py` | Test standalone del feed M15 (verificar candles + indicators). |
| `analyze_trending.py` | Analiza % tiempo en tendencia vs lateral del histórico. |
| `deep_analysis.py` | Análisis profundo de trade_archive (patrones, correlaciones). |
| `ml_feature_analysis.py` | Feature importance ML sobre features de trades. |
| `benchmark_llm_models.py` | Benchmark velocidad/calidad de modelos Ollama. |
| `aidan_watchdog.py` | Watchdog que reinicia AIdan si se cuelga. |

### Backtest H1+M15 results (30 días, 27 Mar → 8 May 2026)

**M15** (693 signals, sin filtros completos):
- WR 49.2%, PF 1.10, +189.6p, avg 0.27p/trade
- Setup ganadores: `trend_continuation_bull` (+236p), `trend_continuation_bear` (+82p)
- Setup perdedores: `momentum_expansion` (-52p), `breakdown_support` (-71p)

**H1** (212 signals):
- WR 50.5%, PF 1.17, +156.2p, avg **0.74p/trade** (mejor avg)
- Setup ganador estrella: `breakout_resistance` WR 72% +209p
- Setup perdedores: `breakdown_support` (-50p), `momentum_expansion` (-15p)

**Lecturas honestas**:
- 99% de trades terminan en expiry (SL/TP raramente hit) → thresholds holgados vs ATR real
- Ambos tracks tienen edge MARGINAL estructural sin filtros adicionales (PF 1.1 ≈ break-even con fricción)
- H1 confirma tesis de comisión drag bajo: avg 0.74p/trade vs M15 0.27p
- Backtest **infla metricas 20-30%** vs real → PF real estimado ~0.85-0.95 (NO rentable solo)
- Necesita capas adicionales (htf_bias, anti-spam, LLM auditor) que demo SÍ tiene

### Caveats del backtest H1+M15

1. Solo trigger `structure` (sin news ~30% de signals reales)
2. Sin htf_bias derivado de SMC live (filtro counter-HTF inactivo)
3. AutoTuner params actuales sobre data vieja (mild data leakage)
4. Sin spread variable, slippage, latency execution
5. Backtest infla metricas vs producción real con fricción

---

## Cosas que NO se deben hacer

1. ❌ Modificar código sin aprobación explícita del user.
2. ❌ Hacer commits con `Co-Authored-By: Claude`.
3. ❌ Agregar filtros con muestra <6 trades de evidencia.
4. ❌ Tocar `mt5_config` (kill switch, risk_percent) sin permiso.
5. ❌ Borrar trade_archive, learning_insights, o cualquier histórico.
6. ❌ Modificar `Config.GROQ_API_KEYS` salvo si user pide rotación explícita.
7. ❌ Llamar a APIs reales con dinero. Demo only.
8. ❌ Ejecutar simulaciones que escriban a la DB de producción.
9. ❌ Cambiar el modelo de LLM por uno pago sin permiso.
10. ❌ Hacer deploys (rebuild + commit) sin test previo de imports.

## Cosas que SÍ son apropiadas hacer proactivamente

1. ✅ Diagnosticar trades específicos por id si user pregunta.
2. ✅ Reportar estado MT5 + version + posiciones cuando user pide "status".
3. ✅ Sugerir simulaciones standalone en `tools/` para validar antes de change.
4. ✅ Pedir clarification con formato Plan/Razón/Pros/Contras/Opinión.
5. ✅ Loggear tu análisis en español, código en inglés.
6. ✅ Verificar que AIdan arranca sin error tras rebuild (capture stderr).
7. ✅ Sanity import check antes de rebuild: `python -c "from src.common.config import Config; print(Config.VERSION)"`.

---

## Para levantar contexto rápido en una sesión nueva

```bash
# 1. Verificar AIdan corriendo y version
curl -s http://localhost:8000/version

# 2. Estado MT5 + daily PnL
curl -s http://localhost:8000/mt5/status

# 3. Últimas estrategias
curl -s http://localhost:8000/auto-strategies?limit=5

# 4. Performance histórico
curl -s http://localhost:8000/performance

# 5. Leer este CLAUDE.md
cat F:/AIdan/CLAUDE.md
```

---

## Reglas de mantenimiento de este archivo

**IMPORTANTE**: con cada cambio significativo (nueva versión, feature, herramienta, hallazgo de backtest), CLAUDE.md DEBE actualizarse. Antes de cada sesión nueva con asistentes IA, leer este archivo completo para mantener contexto. La última actualización siempre debe coincidir con la versión activa en `Config.APP_VERSION`.

**Checklist tras cada cambio**:
- ✅ Bumpear `APP_VERSION` en `src/common/config.py`
- ✅ Actualizar tabla de versiones en CLAUDE.md
- ✅ Si agregaste tool nuevo → línea en sección Tools
- ✅ Si cambió diagnóstico/KPI → actualizar "Estado actual"
- ✅ Sanity check imports antes de rebuild
- ✅ Rebuild AIdan.exe
- ✅ Verificar `/version` en endpoint
- ✅ Commit (sin Co-Authored-By)
- ✅ Push a origin/main
- ✅ Actualizar línea final "Última actualización"

---

**Última actualización**: 9 May 2026 — v3.30.2
