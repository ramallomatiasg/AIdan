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
GET /theme-editor             # Editor visual de paleta CSS (Thariq-style)
GET /what-if                  # What-if simulator sobre trade_archive REAL
GET /trade-archive-data       # JSON con todos los trades archivados (data del what-if)
GET /meta-optimization        # Dashboard meta-optimizer (pending_changes + audit trail)
GET /pending-changes          # JSON lista pending_changes (con filter ?status=X)
GET /pending-changes/{id}     # Detalle de un cambio + history + shadow stats
POST /pending-changes/{id}/approve  # Aplicar al live (skip shadow validation)
POST /pending-changes/{id}/revert   # Revertir cambio aplicado
POST /pending-changes/{id}/reject   # Marcar rechazado
POST /pending-changes/{id}/start-shadow  # Iniciar shadow validation
GET /meta-optimization-status # Resumen counts por status + active filters + baseline
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
| v3.30.2 | Shutdown rapido <2s + LRU cache news + query optimization /auto-strategies | activo |
| v3.30.3 | Fix /recent Markdown (escape `_`) + drawdown alert daily-basis (no spam lifetime) | activo |
| v3.30.4 | HTML interactive tools: theme editor + backtest report (inspired by Thariq/Anthropic) | activo |
| v3.30.5 | Theme editor: font-size + card-padding sliders ahora cascadean visualmente (em units) | activo |
| v3.30.6 | What-if simulator: filtros retroactivos sobre trade_archive REAL (164 trades) | activo |
| v3.30.7 | Remove backtest HTML report + tutorial inline en what-if simulator | activo |
| v3.31.0 | Meta-Optimization: shadow mode + LLM nightly analyst (19h AR) + auto-applier + monitor con rollback | activo |
| v3.31.1 | Full autopilot: auto_start_shadow_for_proposed() — proposed→shadow_validating automatico, max 3 simultaneos, dedup | activo |
| v3.31.2 | Manual trigger: boton ▶ Run analyst en dashboard reemplaza Task Scheduler (user puede correr cuando quiera) | activo |
| v3.31.3 | Hotfix: NameError `logger` en start_services (splash quedaba colgado en "Iniciando Dashboard API") | activo |
| v3.31.4 | Hotfix pre-plan: sanity check expandido + SL/TP del LLM (no profile M5) + min_conf 60 + lot cap 0.05 | activo |
| v3.31.5 | UI fix: pre-plans ejecutadas mostraban created_at (ayer 5pm) en vez de event_time. Priorizar event_time siempre | activo |
| v3.31.6 | Hotfix nightly_analyst: claude CLI `--input-file` no existe → usar stdin + `--dangerously-skip-permissions` (Opus funciona) | activo |
| v3.31.7 | Warmup gate M15 (30min) + H1 (60min): bloquea trades en primeros minutos post-restart (sobre-operacion fix) | activo |
| v3.31.8 | CRITICO: shadow runner bugs — hour_utc/session/setup_type vacios → filtros block_hour/block_session/block_setup nunca disparaban | activo |
| v3.32.0 | Math fixes: TP 15→20p + BE trigger 50% + trail 80% (atacar "gana poco/pierde mucho") | activo |
| v3.32.1 | User awake window: no abrir H1 después de 19h AR (expiry 3h cae en madrugada). Configurable via env. | activo |
| v3.33.0 | REFACTOR Fase B: macro context (htf_bias + daily_ctx) ahora GARANTIZADO en M5/M15/H1 (antes None si M5 skipped). + tool train_confidence_model.py (Fase A preparatoria, Brier 0.28 vs 0.39) | activo |
| v3.34.0 | REFACTOR Fase C: Entry Quality Gates basados en hallazgos ML | activo |
| v3.35.0 | ML Confidence Predictor: modelos dedicados (news AUC 0.75, m15 AUC 0.625) + feature flag USE_ML_CONFIDENCE (default OFF). Endpoints `/ml-predictor/status` y `/ml-predictor/test`. | activo |
| v3.35.1 | Counter-HTF news gate: threshold 65 → 60 (= base min_conf). 26 May: 4 news directional, 0 strategies. v3.34.0 entry gates + v3.35.0 ML predictor ya filtran exhaustion/low-P(win), duplicar con 65 acumulaba filtros sin evidencia. Tambien: cleanup meta-filters viejos (revert #10, reject #7/#9/#13). | activo |
| v3.35.2 | Bugfix: duplicate MT5 order durante reconexion. Strategy #537 (26 May post-MT5 reconnect 11:07) genero 2 tickets en MT5 (limit order send tiro exception pero orden si llego al server). Orphan detector cerro la duplicada al spread (-$0.80 commissions waste). Fix: idempotency check en open_position + en _try_limit_order failure paths via comment match "AIdan #{strategy_id}" en positions/orders. | activo |
| v3.35.3 | ATR floor M5 bajado 2.5 → 2.0p (news + structure + SMC). Semana 26 May: mercado quieto (ATR 1.8-2.3p casi todo el dia, lunes feriado US/UK) dejaba AIdan con 0-1 trades/dia. ML predictor (v3.35.0) actua como red de seguridad. M15 (5p) y H1 (10p) sin cambios. | activo |
| v3.36.0 | Live Position Manager (Fase 1: reglas, sin LLM). Gestor en vivo que decide HOLD/CLOSE_PROFIT/CLOSE_PROTECT/CLOSE_MAXHOLD sobre posiciones abiertas, reemplazando el expiry ciego + force-close por mechas re-analizadas (bug del #538). Thread cada 15s. MODE=log/active/off. MAX_HOLD 90/120/240min (M5/M15/H1). Profit-lock arma a 60% TP, cierra si retrocede 40% del pico. Tabla position_manager_log. | activo |
| **v3.37.0** | **Position Manager Fases 2+3 construidas (defaults seguros). Fase 2: LLM Exit Advisor (`src/analyzer/exit_advisor.py`) — en zona ambigua (soft-expiry HOLD) consulta Gemma local (fallback Groq) HOLD/CLOSE/TIGHTEN. Sub-flag POSITION_MANAGER_LLM (default OFF), rate-limit 5min/posicion, GPU-aware, CLOSE_LLM action. Fase 3: endpoints `/position-manager/state` + `/stats` + dashboard standalone `/position-manager` (tools/position_manager.html). Activacion pendiente de validar Fase 1 con trades reales.** | **actual** |

### Filtros activos (v3.18.0)

```
Warmup gate M5 (10 min tras arrancar)
Warmup gate M15 (30 min — 2 velas frescas)  -- v3.31.7
Warmup gate H1 (60 min — 1 vela fresca)      -- v3.31.7
ATR floor 2.0p (M5 — v3.35.3, antes 2.5p)
ATR ceiling 6p
Counter-HTF (news regular path requiere conf≥60 — v3.35.1)
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

## Estado actual del proyecto (11 May 2026)

### KPIs

- Balance demo: ~$899 (de $1000 inicial = -10.1% en ~4 semanas)
- WR histórico (165 trades archivo): 37.0%
- PnL histórico: **-$167.59**
- PF histórico: **0.55** (target >1.3)
- Frecuencia objetivo: 5-10 trades/día
- Frecuencia REAL reciente: **8 trades/día promedio** (11 May: 8 trades, 1 win = WR 12.5%)

### Diagnóstico estructural

4 problemas conocidos NO resueltos por filtros:
1. **Comisión = 87% pérdida neta**. Para break-even al WR 41% necesitamos avg win 6p (actualmente 4p).
2. **15-min expiry mata trades direccionalmente correctos**. Patrón observado múltiples veces.
3. **Groq mis-interpreta news con frecuencia**. Negaciones de central bank action.
4. **Confidence MAL CALIBRADA** (descubierto 11 May 2026 via what-if simulator). Ver sección dedicada abajo.

### Análisis 11 May 2026 — Calibración de confidence

**Descubrimiento via what-if simulator**: la confidence score (0-100) NO es predictor monotónico del win rate. Subir `min_confidence` empeora resultados porque elimina ganadores chiquitos sin filtrar perdedores.

**Tabla WR por bucket de confidence (165 trades histórico)**:

| Conf | Trades | WR | PnL |
|---|---|---|---|
| 30-39 | 5 | 40% | -$2.70 |
| **40-49** | **7** | **43%** | **+$8.60** ✓ |
| 50-59 | 22 | 36% | -$32.21 |
| 60-64 | 37 | 38% | -$12.56 |
| 65-69 | 17 | 35% | -$36.06 |
| **70-74** | **32** | **34%** | **-$60.12** ✗ |
| 75-79 | 16 | 44% | +$1.00 |
| 80-84 | 11 | 36% | -$1.50 |
| 85-89 | 8 | 50% | -$11.96 |
| **90-94** | **6** | **0%** | **-$23.38** ✗✗ |
| 95-100 | 4 | 50% | +$3.30 |

**Hallazgos clave**:
- Conf **90-94: 0% WR** → las más "confiadas" son las peores
- Conf **40-49: 43% WR** → mejor que muchos buckets altos
- Conf **70-74: -$60.12** (32 trades) → el bucket más perdedor en absoluto
- **NO existe correlación monotónica conf→WR**

**Cumulative "si filtro min_conf >= X"**:

| min_conf | n | WR | PnL |
|---|---|---|---|
| ≥0 | 165 | 37.0% | -$167.59 (baseline) |
| ≥50 | 153 | 36.6% | -$173.49 (peor) |
| ≥60 | 131 | 36.6% | -$141.28 |
| ≥70 | 77 | 36.4% | -$92.66 |
| ≥75 | 45 | 37.8% | -$32.54 |
| ≥85 | 18 | 33.3% | -$32.04 |

**Subir el piso no ayuda**. AIdan ya tiene `conf_ceiling 80` desde v3.11 (anti-predictive) — esto valida que el TECHO sí aporta, no el piso.

**Root cause (hipótesis)**: la fórmula `dynamic_conf` (technical.py:451) suma puntos de factores redundantes (MA trend + HTF + RSI + momentum miden lo mismo). Cuando todos alinean = conf 90+ = **exhaustion entry** (mercado ya se movió, por revertir). Es por eso que existe SIM A (block fully-aligned).

**Análisis por session (165 trades)**:

| Session | Trades | WR | PnL |
|---|---|---|---|
| **london** | 7 | 28.6% | +$2.40 ✓ (muestra inútil) |
| late_ny | 55 | 36.4% | -$50.89 |
| ny | 68 | 38.2% | -$61.40 |
| overlap | 33 | 39.4% | -$44.70 |
| off | 2 | 0% | -$13.00 |

**Lectura**: TODAS las sessions pierden plata (excepto London con 7 trades = ruido). El problema no es de session específica — es estructural.

### Opciones para corregir confidence (post-Fase 1)

1. **Opción A — Bucket-based blocking (rápido, riesgo bajo)**. Block conf 70-74 y 85-94 explícitamente en `blocked_setups`. Allow conf 40-49. Tiempo: 1-2h. Riesgo: overfitting muestra chica.

2. **Opción B — Empirical confidence (medio plazo)**. Reemplazar fórmula por WR real histórico del setup_type. Ya existe `setup_win_rates` cached parcialmente. Tiempo: 2-3 días.

3. **Opción C — Logistic regression / ML proper (largo plazo)**. Entrenar modelo con features del trade_archive → P(win) calibrada. Requiere muestra 500+. Tiempo: 2-3 días + data.

4. **Opción D — A/B test paralelo (validación)**. M5 actual + M5-bucket-filter en paralelo 30 días. Decisión empírica.

### Restricción real: frecuencia de trades vs target

**Target original (CLAUDE.md viejo)**: 200-300 trades para validación robusta.

**Realidad observada (11 May)**: ~8 trades/día. Para 200-300 trades necesitamos **25-37 días más** (final de mayo / mediados de junio). NO vamos a tener muestra robusta antes de eso. Decisiones intermedias serán siempre **provisorias**.

**Implicancia**: cualquier cambio estructural (Opciones A-D arriba) debe esperar a ese horizonte. Fixes surgical (block bucket específico con muestra >20) son aceptables con caveats documentados.

### Próximo checkpoint

**Viernes 15 May 2026** — review semanal:
- Trades acumulados por track (M5 vs M15 vs H1)
- ¿Patrón conf no-monotónica persiste con data nueva?
- Heatmap horas: ¿16h UTC y 19h UTC siguen siendo 0% WR?
- Decisión: surgical fix bucket 70-74 vs seguir esperando

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
- **Confidence inversion** (11 May 2026): patrón observado donde conf alta (90+) tiene WR inferior a conf media (40-49). Causa: factores redundantes en `dynamic_conf` se suman → alineación total = exhaustion. Mismo principio que SIM A pero medido numericamente.

---

## Tools disponibles en `tools/`

| Script | Propósito |
|---|---|
| `backtest_h1_m15.py` | Backtest estructural-only sobre candles MT5 históricas. Re-corre `detect_structure_signals()` y simula SL/TP/expiry hit. Solo trigger `structure`, sin news/calendar/pre_planned/smc-live. |
| `dashboard_theme_editor.html` | Editor visual standalone con color pickers + sliders para todos los CSS vars del dashboard. Live preview de cards/charts/tables. Presets (Dark/Light/Midnight/Terminal/Sunset). Botón export CSS al clipboard. Endpoint: `/theme-editor`. |
| `what_if_simulator.html` | Simulador retroactivo sobre `trade_archive` REAL (164+ trades). Sliders min_conf/conf_ceil/atr_floor/atr_ceil + checkboxes trigger/dir/session/dow/hour/htf_bias + bloqueo counter-HTF + exclude SL-hit-only. Recomputa WR/PF/PnL al instante, delta vs baseline real. Equity curve, heatmap por hora, breakdown trigger. Endpoint: `/what-if`. Data via `/trade-archive-data`. |
| `meta_optimization.html` | Dashboard del meta-optimizer v3.31.0. Muestra pending_changes por status, baseline vs shadow PF, audit trail por cambio, action buttons (approve/revert/reject/start-shadow). Endpoint: `/meta-optimization`. |
| `nightly_analyst.py` | Manual trigger desde dashboard (botón ▶ Run analyst). LLM analyst (Opus → Groq → Ollama fallback chain) analiza stats 24h/7d/30d y propone cambios JSON estructurados. Min sample thresholds + guard-rails hard-coded. Inicia shadow validation automaticamente vía auto_applier. v3.31.2: removida la Task Scheduler. |
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
11. ❌ **NO tocar `dynamic_conf` formula con muestra <300 trades** (11 May 2026). Confidence está mal calibrada pero arreglarla con muestra chica = overfitting garantizado. Esperar Fase 1 completa.

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

## Meta-Optimization (v3.31.0)

Sistema de mejora continua autonomo implementado 14 May 2026. Plan completo en `~/.claude/plans/sorted-meandering-pizza.md`.

### Arquitectura

```
LLM Analyst (19:00 AR cron)  →  pending_changes (proposed)
        ↓                              ↓
Shadow Runner (auto)         →  shadow_strategies + shadow_trades
        ↓                              ↓
Auto-Applier (cada 10min)    →  pending_changes (validated → applied)
        ↓                              ↓
Monitor (cada 50 trades)     →  Auto-revert si PF cae >10%
```

### Componentes

- **`tools/nightly_analyst.py`**: ejecutable manualmente desde dashboard (botón ▶ Run analyst). LLM fallback chain: Opus 4.7 → Groq llama-3.3-70b → deepseek-r1:14b → deepseek-r1:7b → qwen2.5:7b. Genera input JSON (stats 24h/7d/30d por buckets conf/trigger/hora/session/htf), invoca LLM, parsea output JSON, persiste como pending_changes con `source='nightly_<kind>_<model>'`. v3.31.2: removida la Task Scheduler diaria — ahora 100% on-demand.
- **`src/optimizer/shadow_runner.py`**: cuando se crea auto_strategy, evalua signal contra todos los pending_changes con status='shadow_validating'. Crea shadow_strategies con decision=taken/skipped. Daemon paralelo simula outcomes con sim_engine.py usando candles posteriores.
- **`src/optimizer/sim_engine.py`**: motor de simulacion SL/TP/expiry compartido (refactor de backtest_h1_m15.py).
- **`src/optimizer/change_manager.py`**: apply/revert engine con guard-rails. Funciones: `apply_change()`, `revert_change()`, `is_signal_blocked_by_meta_filters()`, `get_confidence_adjustment_for_signal()`.
- **`src/optimizer/auto_applier.py`**: daemon. Promueve shadow_validating → validated (si shadow PF > baseline + 0.15 y muestra >= 30 trades). Aplica validated → applied (max 1 a la vez). Monitorea applied; auto-revert si PF live cae >10% en 50 trades.

### Tablas nuevas en DB

- `pending_changes`: cola de cambios. Status: proposed → shadow_validating → validated → applied → reverted | rejected.
- `shadow_strategies`: signals simulados con config alternativa (decision=taken/skipped).
- `shadow_trades`: outcomes simulados.
- `change_history`: audit trail inmutable.
- `active_meta_filters`: filtros activos consumidos por scanner en cada signal.

### Change types soportados (lista cerrada)

`block_setup_type`, `block_conf_bucket`, `block_hour_utc`, `block_session`, `block_pattern`, `tune_optimizer_param`, `adjust_setup_confidence`, `adjust_min_confidence_per_track`.

### Guard-rails hardcoded (NO se pueden tocar)

`mt5_config`, `risk_percent`, `max_lot`, `daily_loss_limit`, `kill_switch`, MT5 credentials, Groq API keys, `dynamic_conf` formula.

### Thresholds del auto-applier

- `SHADOW_MIN_TRADES=30`: minimo shadow trades antes de validar
- `SHADOW_MIN_PF_DELTA=0.15`: shadow PF debe superar baseline + delta
- `VALIDATION_DROP_PCT=0.10`: live PF cayendo >10% post-apply → auto-revert
- `MONITOR_INTERVAL_TRADES=50`: chequeo cada N trades post-apply
- `COOLDOWN_DAYS_AFTER_REVERT=7`: pausa tras revert

### Telegram alerts (formato breve)

```
🌙 Analyst 19:00 — 14 May
Modelo: opus / Trades 24h: 9 (WR 33%)
Propuesta: block conf bucket 70-79
Estado: shadow validation 7-14d

✅ Cambio aplicado
block_conf_bucket {"bucket_lo":70,"bucket_hi":79}
Shadow PF +0.18 vs baseline 0.55

⚠️ Cambio revertido
block_hour_utc {"hours":[16,19]}
PF cayó -12% en 50 trades post-apply
```

NO se reporta costo de tokens en Telegram (solo log local).

### Setup operacional

**v3.31.2**: removida la Task Scheduler. Ahora se ejecuta **manualmente** desde el dashboard:

1. Abrir `http://localhost:8000/meta-optimization` (botón 🤖 en header del dashboard)
2. Seleccionar modelo (Auto-detect / Force Opus / Force Groq / Force Ollama)
3. Click **▶ Run analyst** — corre en background, status polling cada 3s
4. Al terminar (1-5 min típico) muestra:
   - Cambios propuestos (lista con reasoning)
   - Log tail expandible
   - Resultado: success / timeout / error

**Endpoints**:
- `POST /nightly-analyst/run?model=X` — dispara análisis manual
- `GET /nightly-analyst/status` — estado actual (running, last_result, last_changes)

### Riesgos documentados

1. **Muestra chica**: 12 trades/día → shadow 7-14d = 80-160 trades. Min sample per change tipo restringe over-claiming.
2. **Concept drift**: cambios aplicados se re-evaluan implicitamente en monitor (PF live actual).
3. **Cascade failure**: max 1 cambio applied a la vez + cooldown 7d post-revert.
4. **LLM alucina**: schema validation + lista cerrada change_types + guard-rails + min_sample requirements.
5. **Costo runaway Opus**: max 1 sesion/dia, fallback a Groq/local si no disponible.

### Critério de éxito (4 semanas post-deploy)

- ≥ 5 cambios propuestos por LLM
- ≥ 2 validados via shadow
- ≥ 1 aplicado al live
- PF acumulado ≥ 0.70 (vs baseline 0.55)
- 0 violaciones de guard-rails
- ≤ 2 cambios revertidos (significaria que validation funciona)

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

## Backlog de ideas para probar (ordenadas por esfuerzo/impacto)

Ideas de mejora identificadas el 22 May durante el refactor mayor.
Cada una NO probada todavía. Listadas para no perderlas y atacar en orden:

### Quick wins (horas → 1 día)

1. **Random Forest / XGBoost** (en vez de logistic regression)
   - Logistic es lineal — capaz el problema es no-lineal
   - Mismo `train_confidence_model.py`, solo cambiar el modelo
   - Esfuerzo: 1-2 horas. Validación inmediata (comparar AUC vs LR 0.48)

2. **Auto-tuning de gates v3.34.0**
   - Hoy puse vel > 6p y body/atr > 1.3 — thresholds arbitrarios
   - Backtest sobre archive con todas las combinaciones (vel 3,4,5,6,7,8 × body 1.1,1.2,1.3,1.4,1.5)
   - Encontrar el punto de mejor PF post-gates
   - Esfuerzo: 2-3 horas

3. **Modelos separados POR trigger_type**
   - Hoy 1 modelo para todos los trades
   - News + structure + smc tienen patrones distintos
   - Train 1 modelo por trigger con sklearn
   - Esfuerzo: 0.5 día

### Mediano esfuerzo (1-2 días)

4. **Volume features (MT5 tick_volume)**
   - MT5 da tick_volume (no real volume forex pero proxy)
   - Volume spike en breakout = signal más fuerte
   - Volume bajo = posible false breakout
   - Esfuerzo: 1 día (extracción + feature + validación)

5. **Confluencia multi-TF concreta (no binaria)**
   - Hoy solo htf_bias = bullish/bearish/neutral (3 valores)
   - Falta: score 0-10 de alineación M5+M15+H1+H4+D1
   - Cuanto más alineados, mejor el trade
   - Esfuerzo: 1 día (MTFAnalyzer ya tiene trends, solo sumar)

6. **Niveles psicológicos como features**
   - Números redondos (1.1700, 1.1750, 1.1800)
   - High/low de los últimos 3-5 días (no solo día previo)
   - Distance to nearest level como feature
   - Esfuerzo: 1 día

7. **Régimen del mercado (trending vs ranging)**
   - Detectar régimen con ADX o similar
   - Confidence diferente por régimen
   - Esfuerzo: 1-2 días

### Mayor esfuerzo (3+ días)

8. **Timing features finos**
   - mins_since_last_swing_high/low
   - candles_since_breakout (cuán reciente el setup)
   - pullback_depth (cuánto retrocedió antes de continuar)
   - consolidation_duration antes del move
   - Esfuerzo: 2-3 días (feature engineering complicado)

9. **News sentiment cuantificado (más granular)**
   - Hoy solo impact_score 0-100 como entrada
   - Falta: sentiment direction score numérico (no solo categórico)
   - Time decay del impact (news 1h vs 1 día)
   - Esfuerzo: 2 días

10. **Pivot a swing trading (TF más largo)**
    - Operar H4/D1 en vez de M5/M15
    - TP/SL más grandes → comisión % mucho menor
    - Menos sensible al timing exacto
    - Esfuerzo: 1-2 semanas (rediseño parcial del scanner)

### NO factibles con data actual (necesitan otro feed)

11. **Orderbook / liquidity zones** (no tenemos data)
12. **Inter-market correlation (DXY, treasuries, oil)** (requiere feed adicional)
13. **News sentiment cualitativo del LLM mejor estructurado**

### Próximos pasos planeados (orden)

- **Weekend 23-24 May**: probar #1 (Random Forest), #2 (gate tuning), #3 (modelo por trigger)
- **Si alguno mueve AUC >0.6**: continuar con #4 (volume) + #5 (multi-TF score)
- **Si ninguno mejora**: discutir con user pivot a #10 (swing) o cierre

---

**Última actualización**: 27 May 2026 — v3.37.1 (botón 🎛️ Position Manager en header del dashboard → abre /position-manager)
