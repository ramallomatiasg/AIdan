# AIdan — Auditoría completa

**Fecha**: 31 Jul 2026 · **Versión auditada**: v3.47.1 · **Repo**: `F:\AIdan` (branch `main`, working tree limpio)
**Método**: lectura de código + medición empírica directa sobre `%APPDATA%\AIdan\state\financial_news.db` (14 MB, 566 filas en `trade_archive`) + investigación web.
**Alcance**: 18.971 líneas en `src/` + 4.379 en `AIdan_TodoEnUno.py` = ~23.4k LOC Python.

> **Nota metodológica**: todos los números de performance salen de la DB real (`mt5_pnl`, broker-truth), no de simulación. "Data limpia" = trades con `created_at >= 2026-06-20` (post-fixes v3.40.18/19), **n=139**. Donde una propuesta no pasa el gate de significancia que ya usa el proyecto (n≥25 y CI de Wilson que no cruza el baseline), lo digo explícitamente en vez de venderla.

---

## 0. Resumen ejecutivo

**El sistema está a 3,5 puntos porcentuales de win-rate de ser breakeven, y hay un lever medido que cubre esa distancia.** Ese es el titular.

| Métrica (data limpia, n=139) | Valor |
|---|---|
| Win rate | 38,1 % |
| PnL | −$24,73 |
| Profit factor | 0,864 |
| Payoff (avgWin/avgLoss) | 1,40 ($2,97 / $2,12) |
| **WR necesario para breakeven** | **41,6 %** |
| Frecuencia | ~4,8 trades/día |

Los 5 hallazgos que importan, en orden:

1. **🔴 El R:R ya NO es el problema.** El fix v3.40.18 funcionó: el payoff realizado es 1,40 (no 1,2). El diagnóstico histórico "expiry mata trades" está muerto: de 139 trades, **83 pegan SL, 51 pegan TP, 5 otra cosa**. El problema es la *selección de entradas*, y eso ya está medido abajo.
2. **🔴 Tres de los cinco tracks queman lo que ganan los otros dos.** `news + smc + h1` = n=45, WR 24,4 %, **−$56,61**. `m15 + structure` = n=94, WR 44,7 %, **+$31,88**. Apagar los tres perdedores convierte el período limpio de −$24,73 a **+$31,88** (§2.4). *Caveat honesto: p=0,039 pero el CI de Wilson es [14,2 %–38,7 %] y el baseline es 38,1 % → roza el gate por 0,6 pp. No pasa formalmente.*
3. **🔴 La confianza no es una probabilidad, y se puede demostrar en una línea.** Brier score usando `confidence/100` como P(win) = **0,3689**. Predecir la constante 0,37 para todos los trades da **0,2302**. El número de confianza es *literalmente peor que no tener número*. No es "mala calibración", es ausencia de calibración (§2.3, §3.2).
4. **🔴 El bucle de aprendizaje está roto en tres puntos independientes, todos verificados.** `setup_type` es NULL en **546/546** filas del archivo → mata el blend histórico de `dynamic_conf` (paso 6), mata `block_setup_type` y mata `adjust_setup_confidence`. El meta-optimizer no aplica un cambio desde el **1 Jun** (`change_history` último registro; `pending_changes`: 13 rejected, 1 reverted, **0 applied jamás**). El `LearningEngine` escribió 10.736 insights que nadie consume en la ruta de decisión (§2.5).
5. **🔴 Credenciales expuestas.** Tres API keys de Groq **commiteadas** en `src/common/config.py:37-41` (están en HEAD). Un **Personal Access Token de GitHub** embebido en la URL del remote en `.git/config`. El repo hoy responde 404 anónimo (privado), lo que baja la severidad pero no la elimina — rotar igual (§5.1).

Y un hallazgo de proceso: **la suite de tests está rota** — 5 failed, 24 errors, 64 passed. Nadie la corre (§1.4).

---

## 1. Arquitectura y calidad de código

### 1.1 Estructura

El layout `src/` está razonablemente modularizado (broker / analyzer / optimizer / common / admin). El problema no es la ausencia de módulos, es la **concentración de la lógica de orquestación**:

| Archivo | LOC | Rol |
|---|---|---|
| `AIdan_TodoEnUno.py` | 4.379 | GUI + los 3 loops de scan + ejecución + PM + arranque |
| `src/common/db.py` | 3.628 | Todo el acceso a datos, 92 funciones que abren su propia conexión |
| `src/admin/main.py` | 3.222 | FastAPI: ~60 endpoints + HTML embebido |
| `src/analyzer/technical.py` | 1.639 | Scanner de estructura + `dynamic_conf` + SL/TP adaptativo |
| `src/broker/mt5_executor.py` | 1.009 | Órdenes, trailing, BE, idempotencia |

Esos 5 archivos son el **60 % del código**. `AIdan_TodoEnUno.py` no es "un monolito heredado": es donde vive la máquina de estados de trading, mezclada con Tkinter.

**¿Conviene dividirlo?** Sí, pero **no todo y no ahora**. La división de alto valor y bajo riesgo es sacar los tres loops de scan (M5 ~líneas 2200-2600, M15 ~3324, H1 ~3474) a `src/analyzer/scan_loops.py` con una firma común `scan(track_cfg) -> list[Signal]`. Hoy los tres loops son **copias con variaciones**: la misma secuencia de gates reescrita tres veces. Eso es exactamente por qué el bug de `htf_bias` vs `htf_trend` mató M15/H1 durante dos semanas sin que nadie lo viera. Sacar la GUI o el dashboard del monolito es cosmético y no compra nada.

### 1.2 Manejo de errores — el riesgo estructural, cuantificado

El proyecto ya identificó "la clase de bug que mató M15" (excepción tragada a `logger.debug`). Acá está medida:

- **477** bloques `except Exception` en `src/` + `AIdan_TodoEnUno.py`.
- **189 de ellos (40 %) terminan en `pass` o `logger.debug`** — es decir, fallan en silencio por diseño.
- Concentración: `AIdan_TodoEnUno.py` 165, `admin/main.py` 89, `db.py` 35, `mt5_executor.py` 24.

Esto no es un defecto estético. Cada uno de esos 189 sitios es un lugar donde una feature puede morir sin dejar rastro, exactamente como pasó con M15/H1 (v3.40.0), con SMC reversal (v3.40.17), con la dedup del pre-planner (v3.40.8) y con el straddle de calendar. **Son cuatro repeticiones documentadas del mismo patrón.**

**Fix propuesto (barato, alto impacto)**: una utilidad `src/common/guard.py` con un decorador/context-manager que loguee a WARNING con stack + incremente un contador en la tabla `errors` (que existe y tiene **0 filas** — nadie la usa). Reemplazar mecánicamente los `except: pass` de las rutas de decisión (technical, scan loops, mt5_executor) primero. Un contador de errores por sitio, visible en el dashboard, convierte "murió en silencio" en "murió y hay un número que sube".

### 1.3 Acceso a datos

`db.py` abre **92 conexiones SQLite** independientes (una por función), con **99 `conn.close()`**. No hay:
- `PRAGMA journal_mode=WAL` → los lectores bloquean a los escritores.
- `PRAGMA busy_timeout` → un lock concurrente tira `database is locked` inmediatamente, que después cae en uno de los 189 `except: pass`.
- Pool de conexiones ni `check_same_thread` explícito.

Con **~5 threads concurrentes** (scan loop, position manager 15 s, trailing 1 s, learning engine, FastAPI) golpeando el mismo archivo, esto es una fuente de fallos silenciosos difusa. No es teórico: es la explicación más probable de escrituras perdidas esporádicas.

**Fix (30 min, riesgo bajo)**: una función `_connect()` única con `WAL` + `busy_timeout=5000` + `foreign_keys=ON`, y reemplazar los 92 `sqlite3.connect(DB_PATH)` por ella. Es un sed con revisión.

### 1.4 Testing — roto

```
5 failed, 64 passed, 24 errors in 30.16s
```

- `tests/test_news_analyzer.py`: 24 errores + 3 fallos, todos del mismo origen (`assert 'groq' == 'keywords'` en el fixture de línea 13) → el fixture asume que no hay Groq configurado, y como las keys están **hardcodeadas en `config.py`**, el detector siempre elige `groq`. Los tests hardcodeados chocan con las credenciales hardcodeadas.
- `tests/test_db.py`: 2 fallos reales (`test_record_strategy_result`, `test_get_recent_alerts_filters_low_score`).

**Cobertura de lo que importa: cero.** No hay un solo test sobre `mt5_executor.open_position` (idempotencia, dirección de SL/TP, sizing), sobre `compute_adaptive_sl_tp`, ni sobre los gates de ejecución. El CLAUDE.md ya marca esto como "sube de prioridad antes de Fase 2 (cuenta real)". Confirmo: **es el requisito bloqueante #1 para dinero real**, más que cualquier mejora de estrategia.

### 1.5 Logging

Hay **dos** módulos de logging que compiten (`src/common/logging.py` y `logging_setup.py`), ambos JSON, ninguno con file handler ni rotación. El proyecto ya notó el síntoma: *"AIdan no persiste logs — gap conocido"* (incidente 14 Jun, causa no determinable). Con 4.379 líneas de orquestación y 189 excepts mudos, **no tener logs en disco es la deuda operativa más cara**: cada incidente es irrecuperable por construcción.

### 1.6 Otros

- **116 hardcodes de EUR/USD** en el código → bloquea multi-moneda (ya identificado en el roadmap Fase 3). No urgente.
- **29 constantes de conversión a pips** (`* 10000`) dispersas en `technical.py` → asume par de 5 decimales; rompe con JPY.
- `requirements.txt` **no incluye** `joblib`, `scikit-learn`, `numpy` ni `pandas`, que `confidence_predictor.py` y todas las tools importan. El build funciona por accidente (PyInstaller los toma del entorno). Reproducibilidad = 0.
- `ANALYZER_INTERVAL = 10s` (`config.py:30`) sobre velas M5 → **30× de sobre-muestreo**. No es un bug de corrección, pero es CPU y locks de DB gratis; también multiplica los reintentos de ejecución.
- Hay **2 worktrees git abandonados** en `.claude/worktrees/` con copias viejas de `db.py`. Limpiar.

---

## 2. Estrategia de trading

### 2.1 Feature engineering actual

`dynamic_conf` (`technical.py:460-620`) suma ~9 bloques sobre una base de 40:

| Paso | Aporta | Estado real |
|---|---|---|
| 1. Alineación setup×mercado | 0 a +20 | activo |
| 2. Trend strength | ±10 | activo |
| 3. Contexto RSI | ±8 | activo |
| 4. Volatilidad | ±8 | activo |
| 4b. Gate ATR (<2p) | −12 | activo |
| 5. Patrón de vela | +5 | activo |
| **6. Blend WR histórico** | **±15** | **🔴 MUERTO** |
| 7. Sesión | ±10 | activo |
| **8. Alineación trend+HTF** | **0** | **neutralizado a propósito (v3.7.0)** |

**Corrección a una premisa previa**: el brief dice que el macro-trend se cuenta ~3 veces. **Eso ya no es cierto en el código actual.** El paso 8 fue *explícitamente neutralizado* en v3.7.0 (`technical.py:559-575`) con un comentario que documenta la evidencia. El triple-conteo del que hablaba la revisión del 15 Jun ya no existe en la fórmula; lo que queda es un doble-conteo suave entre el paso 1 (`trend_strength` dentro de la rama de setup) y el paso 2 (`trend_strength` otra vez). Es colinealidad real pero de magnitud mucho menor (+18/+10 en el peor caso, no +38).

**Lo que sí está roto es el paso 6.** Consume `get_setup_win_rates()` (`db.py:1872`), que lee `strategy_results` (6 filas) y `signal_results` (427 filas, **todas `news`**). Y en `trade_archive`, `setup_type` es **NULL en 546/546 filas**. El bucle "aprendé qué setups ganan y ajustá la confianza" nunca cerró, para ningún track. Confirmado empíricamente.

### 2.2 Gestión de riesgo

**Lo que está bien** (verificado en código, no lo toques):
- Sizing: `riesgo$ / (SL_pips × 10)` en `mt5_executor.py:171`, con clamp. ~1 % por trade. **Correcto, y tiene una implicación que el proyecto ya entendió**: el SL no determina la pérdida en dólares, el 1 % sí. Apretar el SL no reduce la pérdida, solo baja el WR.
- BE/trailing (`AIdan_TodoEnUno.py:3660-3718`): solo mueve el SL a favor, nunca lo afloja.
- `tp_cap` escalado por expiry (v3.40.18, `technical.py:1600-1620`): **funcionó**. Payoff realizado 1,40.

**Lo que falta**:
- **No hay control de drawdown por racha ni por equity.** Existe el daily loss limit (−$30) y el kill switch, pero nada entre "perdí un trade" y "perdí el día". Con 4,8 trades/día y rachas de 11 pérdidas documentadas (11 Jun), un stop por racha o un sizing decreciente sería el control faltante.
- **Sizing fijo al 1 % sin relación con el edge.** Con payoff b=1,40 y p=0,381, el Kelly completo es `f* = p − (1−p)/b = 0,381 − 0,619/1,40 = −0,061` → **negativo**. Kelly dice: con estos números, el tamaño óptimo es cero. Eso no significa "apagá todo": significa que **el 1 % fijo actual está enmascarando que el edge agregado no existe**, y que cualquier sizing adaptativo debe calcularse *por track*, no global (§2.4, donde m15 sí tiene edge). Fuente: [Kelly Criterion for Algo Traders](https://paperswithbacktest.com/course/kelly-criterion-position-sizing) — media-Kelly captura ~75 % del crecimiento con mucho menos drawdown, y "un Kelly negativo significa que la estrategia no tiene edge; ningún tamaño lo arregla".

### 2.3 Calibración de confianza — medición nueva

Buckets sobre data limpia (n=139):

| Bucket | n | WR real | PnL | "Promete" |
|---|---|---|---|---|
| 40-49 | 2 | 50,0 % | −$4,70 | 45 % |
| 50-59 | 13 | 30,8 % | −$9,56 | 55 % |
| 60-69 | 35 | 31,4 % | **−$34,10** | 65 % |
| 70-79 | 40 | 42,5 % | −$4,30 | 75 % |
| 80-89 | 28 | 39,3 % | **+$20,02** | 85 % |
| 90-99 | 21 | 42,9 % | +$7,91 | 95 % |

**Dos lecturas, ambas importantes:**

1. **La "inversión de confianza" murió.** El fantasma de mayo (conf 90 = 0 % WR) **no aparece** en data limpia: 90-99 rinde 42,9 %, el segundo mejor bucket. Era artefacto de la pila sucia + R:R roto. Confirmo el hallazgo del 28-jul del proyecto. El corte útil está en 70: **conf<70 → 32 % WR / −$48,36 (n=50)** vs **conf≥70 → 41,7 % WR / +$23,63 (n=89)**.

2. **Pero la confianza sigue sin ser una probabilidad.** Brier score con `conf/100` como P(win) = **0,3689**. Predecir siempre 0,37 = **0,2302**. El score es **60 % peor que una constante**. La razón es de escala, no de orden: el sistema dice "85 %" y acierta 39 %. Tiene *algún* poder de ranking débil (monótono de 60 en adelante) y **cero** valor como probabilidad.

Esto importa porque todo lo aguas abajo trata al número como si fuera una probabilidad: los gates de min_conf, el consensus boost, los prompts al LLM. **La corrección correcta no es tocar la fórmula** (regla del proyecto: no con <300 limpios) **sino envolverla**: mantener `dynamic_conf` como *score de ranking* y ajustar encima un mapeo monótono score→P(win) de 2 parámetros (Platt). Con n=139 eso es viable — Platt necesita poca data, isotónica necesita ~1000+ (§3.3).

### 2.4 El lever grande: composición de tracks

Data limpia, desglose por `trigger_type`:

| Track | n | WR | PnL | PF | avgWin | avgLoss |
|---|---|---|---|---|---|---|
| **m15_structure** | 73 | 42,5 % | **+$27,98** | **1,33** | $3,65 | −$2,03 |
| **structure** | 21 | 52,4 % | **+$3,90** | **1,17** | $2,45 | −$2,30 |
| h1_structure | 18 | 27,8 % | −$5,81 | 0,47 | $1,03 | −$0,84 |
| smc | 5 | 20,0 % | −$12,60 | 0,05 | $0,70 | −$3,33 |
| **news** | 22 | 22,7 % | **−$38,20** | **0,23** | $2,32 | −$2,93 |

Agrupado:

- **`m15 + structure`**: n=94, WR **44,7 %**, **+$31,88** (avg +$0,34/trade) → **arriba del breakeven de 41,6 %**.
- **`news + smc + h1`**: n=45, WR **24,4 %**, **−$56,61** (avg −$1,26/trade).

**Los dos tracks buenos ya son rentables. Los tres malos se comen la ganancia y $24,73 más.**

Aplicando el gate de significancia del propio proyecto al grupo perdedor: `p = 0,0387` (binomial one-sided vs baseline 38,1 %), **pero** Wilson 95 % CI = **[14,2 % – 38,7 %]**, que cruza el baseline por 0,6 pp. **Formalmente NO pasa el gate.** Está a un par de trades de pasarlo, igual que la celda "entrada pegada" el 17-jul (que pasó una semana después).

Mi lectura calibrada: `news` por sí solo ya tiene un veredicto independiente y devastador — la medición del 24-jul demostró **cero habilidad direccional** del LLM (discriminación −1 pp, Fisher p=0,92, anti-skill vs el drift). Ese hallazgo no depende de estos 22 trades. **Para `news` la evidencia no es estadística de PnL, es causal: el generador de la señal no tiene información.** No hace falta esperar al gate de PnL para algo cuyo motor ya se midió vacío. `smc` (n=5) y `h1` (n=18) son muestras chicas y ahí sí corresponde esperar.

### 2.5 Sistema de aprendizaje — qué cierra y qué no

| Bucle | Escribe | ¿Se consume en la decisión? |
|---|---|---|
| `LearningEngine` | `learning_insights` (**10.736** filas), `learning_metrics` (6.576) | ❌ Solo dashboard. Ni siquiera toca `self.tuner` (se guarda en `__init__:47` y **nunca se usa**). |
| `post_trade_analyzer` (Gemma) | `post_trade_analysis` (552) | ❌ Solo el endpoint `/post-trade-analysis` y `get_learned_lessons()`. |
| `get_learned_lessons()` | — | ⚠️ **Único bucle vivo**: alimenta el prompt de `news_analyzer.py:605`. Es decir, el aprendizaje solo retroalimenta **al track que ya se demostró sin edge**. |
| `dynamic_conf` paso 6 | — | ❌ Muerto (`setup_type` NULL). |
| Meta-optimizer | `pending_changes` (14), `change_history` (1.965) | ❌ **0 applied jamás**. 13 rejected, 1 reverted. Último movimiento: **1 Jun**. |
| `auto_tuner` | `optimizer_params` (34 iter) | ⚠️ Vivo pero casi inerte: desde abril solo cambió **3 params** (`breakout_dist_max` 15→7, `breakdown_dist_max` 15→7, `block_outside_sessions` False→True). |
| `confidence_predictor` | — | ❌ Apagado por flag. |
| `shadow_runner` | `shadow_strategies` (1.751), `shadow_trades` (1.296) | ❌ Alimenta al auto_applier, que nunca aplicó nada. |

**Diagnóstico**: hay **siete** mecanismos de aprendizaje construidos y **uno** conectado — al track equivocado. Se escribieron ~20.000 filas de "aprendizaje" que no cambian ni una decisión. Esto es, con diferencia, el mayor desperdicio de ingeniería del proyecto, y explica por qué "¿se está puliendo?" tiene respuesta negativa.

---

## 3. Modelo ML / IA

### 3.1 Estado del `confidence_predictor`

`src/optimizer/confidence_predictor.py` (202 líneas). Apagado con `USE_ML_CONFIDENCE=false`. **El apagado fue correcto** y está bien documentado: `tools/revalidate_predictor.py` mostró que el AUC 0,75 era artefacto de un split único de ~12 trades de test; el honesto es ~0,57 (p 0,17-0,34). El workflow del 31-may refutó RF/XGB/LR/por-trigger sobre n=276.

Dos observaciones técnicas sobre el módulo, para cuando se reactive:
- **Imputa medianas silenciosamente** (líneas 116-132). Un vector con 8 de 20 features faltantes produce una predicción con aire de confianza. Debería devolver `None` si faltan más de N features críticas.
- **Mapea `p_win * 100` directo a "confidence"** (línea 182), mezclando dos escalas: una probabilidad calibrada de 0,42 se convierte en "confianza 42", que después compite contra un `min_conf=60` diseñado para la escala heurística. Ese solo detalle haría que el modelo ML nunca dispare un trade.

### 3.2 Qué enfoque conviene ahora

La pregunta correcta no es "¿qué modelo?" sino **"¿qué tarea?"**. Los intentos previos fallaron porque intentaron *reemplazar* la confianza con un clasificador entrenado desde cero sobre pocos datos. La tarea barata y de alto rendimiento es distinta:

**No aprendas P(win) desde features. Aprendé la función que mapea el score que ya tenés a P(win).**

| Enfoque | Params a estimar | n mínimo | Veredicto |
|---|---|---|---|
| **Platt (sigmoide de 2 params) sobre `confidence`** | **2** | **~100** | ✅ **Recomendado** |
| Isotónica sobre `confidence` | ~k bins | ~1000 | ❌ Sobreajusta a n=139 |
| Regresión logística multi-feature | 15-25 | ~500 | ❌ Ya refutada |
| GBM / RF | cientos | ~2000+ | ❌ Ya refutada (overfit textbook) |
| Redes | miles | — | ❌ No |

Con n=139 y **2** parámetros, Platt está dentro del presupuesto estadístico. La literatura lo respalda directamente: *"Platt scaling es la opción práctica cuando el conjunto de calibración es chico… es eficiente en datos comparado con isotónica"*, y la isotónica solo iguala/supera con **1000+ puntos** ([KDnuggets](https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling), [Niculescu-Mizil & Caruana, ICML'05](https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf)). El workflow específico para trading —*"empezá con reliability plots y bucket tests, después aplicá una capa monótona de calibración sobre ventanas held-out… lo que importa menos es el método y más la disciplina de ajustar sobre el pasado y congelarlo antes del siguiente slice"*— es exactamente lo que le falta ([Alphora](https://alphora.io/learn/how-do-you-calibrate-a-trading-probability/)).

**Qué compra esto concretamente**: convierte `confidence` de un número decorativo en `P(win)` usable, y con eso el *sizing por Kelly fraccionario por track* deja de ser imposible de calcular. Es el desbloqueo de §2.2.

### 3.3 Validación — el error que se sigue repitiendo

Todos los experimentos ML del proyecto usaron **split cronológico único 80/20**, y todos se cayeron al re-validarlos. Eso no es mala suerte, es el método. El estándar para series temporales financieras es **purged/embargoed CV** — purga las etiquetas solapadas entre train y test y agrega un embargo temporal ([Purged cross-validation, Wikipedia](https://en.wikipedia.org/wiki/Purged_cross-validation)). Y para elegir entre configuraciones, el **Deflated Sharpe Ratio** corrige el sesgo de selección por testeo múltiple, que es precisamente el sesgo que produjo "AUC 0,75" ([López de Prado, *The 10 Reasons Most ML Funds Fail*](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)).

**Nota justa**: el gate de significancia que el proyecto ya construyó (`significance.py`, binomial + Wilson) **es** una versión de esto y ha funcionado — rechazó correctamente el hour gate, los entry gates, fade-chop (3×) y el sesgo direccional. La brecha no está en la disciplina, está en que ese gate no se aplica a los *experimentos ML offline*, solo a los hallazgos de trading. Un `tools/cv_purged.py` cerraría el hueco.

### 3.4 Drift y reentrenamiento

No existe ninguno de los dos. Con un régimen que ya demostró invertir conclusiones (el "chop tóxico" del 3-jul se dio vuelta el 17-jul), esto no es opcional a mediano plazo. La forma barata: guardar la distribución de las features al entrar (ya está en `entry_context`, **0 % faltante en data limpia** — muy bien) y correr un PSI/KS mensual. `Evidently` lo hace con un preset y produce HTML ([Evidently: data drift](https://www.evidentlyai.com/ml-in-production/data-drift)). No hace falta MLflow todavía; con un modelo de 2 parámetros, versionarlo es un JSON con fecha.

---

## 4. Infraestructura y ops

| Área | Estado | Riesgo |
|---|---|---|
| Deployment | PyInstaller → exe, arranque manual/Task Scheduler | Bajo (funciona) |
| **Logs persistentes** | **NO EXISTEN** | **🔴 Alto** |
| Monitoreo | Dashboard + Telegram (bueno) | Medio (es reactivo, no histórico) |
| **Backups de la DB** | **NINGUNO** (0 referencias a backup/VACUUM en `db.py`) | **🔴 Alto** |
| Persistencia de estado | SQLite 14 MB, sin WAL, sin busy_timeout | Medio |
| Reproducibilidad | Sin seeds, sin versionado de modelos, deps ML no declaradas | Medio |
| Latencia de decisión | Loop cada 10 s sobre velas de 5 min | Bajo (sobra) |

**El backup es el hueco más grave y el más barato de tapar.** Un archivo de 14 MB contiene el 100 % del track record del proyecto — 566 trades, 10.736 insights, todos los shadows. Un `sqlite3 .backup` diario con rotación de 7 días es literalmente 5 líneas. Hoy un disco corrupto borra cuatro meses de trabajo, y todo el método del proyecto (medir antes de tocar) depende de esa data.

Sobre los logs: el incidente del 14 Jun quedó con "causa no determinable". Va a volver a pasar. Un `RotatingFileHandler` en `%APPDATA%\AIdan\logs\` (10 MB × 5) resuelve la clase entera.

---

## 5. Data engineering

### 5.1 🔴 Seguridad de credenciales

1. **Tres claves de Groq en `src/common/config.py:37-41`**, en texto plano, **presentes en HEAD** del repo. El repo responde 404 anónimo (privado o inexistente), lo que limita el daño — pero están en el historial de git y en cada copia clonada.
2. **Un GitHub PAT (`ghp_…`) embebido en la URL del remote** en `.git/config`. Cualquiera con acceso al disco o a un backup del working tree lo tiene.
3. Una `TWELVE_DATA_API_KEY` hardcodeada (`config.py:33`) y una URL de webhook de Google Apps Script (`config.py:76`).
4. ✅ Las credenciales de MT5 sí están correctamente en env (`config.py:80-82`), sin defaults. Bien hecho.

**Acción**: rotar las 3 keys de Groq y el PAT, mover a `.env`, y purgar el historial (`git filter-repo`) o al menos aceptar que las viejas quedan quemadas. **Esto se hace antes que cualquier mejora de estrategia** — es la única categoría del informe donde el costo de esperar crece solo.

### 5.2 Look-ahead bias

**Bien manejado, mejor que el promedio.** Dos controles reales:
- `entry_context` se persiste **en el momento** de la señal (0 % faltante en data limpia), no se reconstruye después.
- El proyecto ya derivó y aplica la regla `CUT_BEFORE_S ≥ 300` tras cazar un lookahead real el 12-jun (el bucket ">15p/60min" que daba p=0,010 con cutoff −60 s y era ruido con −300 s).

Esa lección está internalizada y es la razón por la que las mediciones recientes son confiables. **No tocar este mecanismo.**

### 5.3 Almacenamiento

**SQLite a 14 MB / 566 trades no es un problema y no lo va a ser.** A 4,8 trades/día, llegar a 10.000 trades toma ~6 años. La recomendación de migrar a Postgres/Timescale **no aplica** — sería complejidad sin beneficio. Lo que sí conviene:

- **Ahora**: WAL + busy_timeout + backup (§1.3, §4).
- **Si en algún momento se guardan velas tick-a-tick o se hace research pesado**: DuckDB leyendo Parquet, sin migrar la DB operativa. DuckDB es OLAP, vive en un archivo como SQLite, y es la mejor herramienta actual para ETL analítico ([comparativa de time-series DBs](https://medium.com/@ev_kozloski/timeseries-databases-performance-testing-7-alternatives-56a3415e6e9e)). Timescale solo tendría sentido con múltiples escritores concurrentes o replicación, que no es el caso.

### 5.4 Fuentes de datos

MT5 (velas + deals, la fuente de verdad) + Forex Factory (calendario, ya rescatado del auto-ban 429) + RSS de noticias (5.978 filas) + Groq/Ollama. Cobertura razonable. El gap real no es de fuentes sino de **etiquetado**: `setup_type` NULL en 546/546 hace que toda la data de setups sea inservible para aprender. **Ese es el fix de data engineering con mejor ratio del proyecto** (§6, DT-2).

---

## 6. Deuda técnica priorizada

Score = Impacto (1-5) × Urgencia (1-5) ÷ Esfuerzo (1-5).

| # | Item | Archivo | Imp | Urg | Esf | Score |
|---|---|---|---|---|---|---|
| **DT-1** | Credenciales commiteadas (3 Groq + PAT) | `config.py:37-41`, `.git/config` | 4 | 5 | 1 | **20,0** |
| **DT-2** | `setup_type` NULL 546/546 → mata 3 mecanismos | `db.py:1347`, archive | 5 | 4 | 1 | **20,0** |
| **DT-3** | Sin backup de la DB | ops | 5 | 4 | 1 | **20,0** |
| **DT-4** | Sin logs persistentes | `logging_setup.py` | 4 | 4 | 1 | **16,0** |
| **DT-5** | Composición de tracks (3 perdedores) | scan loops | 5 | 4 | 2 | **10,0** |
| **DT-6** | SQLite sin WAL/busy_timeout, 92 conexiones | `db.py` | 3 | 3 | 1 | **9,0** |
| **DT-7** | Confianza sin calibrar (Brier 0,37 vs 0,23) | `technical.py:460` | 4 | 3 | 2 | **6,0** |
| **DT-8** | Suite de tests rota (5F/24E) | `tests/` | 3 | 4 | 2 | **6,0** |
| **DT-9** | 189 excepts silenciosos | transversal | 4 | 3 | 3 | **4,0** |
| **DT-10** | Cero tests del path de ejecución | `tests/` | 5 | 3 | 4 | **3,8** |
| **DT-11** | Meta-optimizer muerto (0 applied) | `auto_applier.py` | 3 | 2 | 3 | **2,0** |
| **DT-12** | Loops M5/M15/H1 triplicados | `AIdan_TodoEnUno.py` | 3 | 2 | 4 | **1,5** |
| DT-13 | `requirements.txt` sin deps ML | `requirements.txt` | 2 | 2 | 1 | 4,0 |
| DT-14 | 116 hardcodes EUR/USD | transversal | 2 | 1 | 5 | 0,4 |

---

## 7. Propuestas concretas

### P1 — Rotar credenciales y sacarlas del código `[DT-1]`
**Qué**: mover las 3 keys de Groq de `config.py:37-41` a `.env`; quitar el PAT de la URL del remote (usar `gh auth` o credential manager); rotar ambas. Dejar `GROQ_API_KEYS = json.loads(os.getenv("GROQ_API_KEYS","[]"))`.
**Por qué**: están en HEAD y en el historial. Efecto lateral bueno: arregla de paso 24 de los 27 errores de test (§1.4), porque el fixture asume que no hay Groq configurado.

### P2 — Poblar `setup_type` en el archivo `[DT-2]`
**Qué**: en el path de archivado (`db.py:1347` ya tiene el fallback `ctx.get('setup_type') or trigger_type`), asegurar que la señal lo propague — hoy llega vacío desde el scan. Una línea en cada uno de los 3 loops.
**Por qué**: desbloquea simultáneamente (a) el paso 6 de `dynamic_conf` (±15 pts que hoy nunca se aplican), (b) `block_setup_type` del meta-optimizer, (c) `adjust_setup_confidence` (`change_manager.py:322`, que nunca puede matchear). Tres mecanismos construidos y muertos, revividos con un fix de datos.
**Caveat**: revivir el paso 6 *cambia el comportamiento vivo*. Recomiendo poblar el campo ahora (solo datos, no-op) y **dejar el paso 6 apagado** hasta tener 3-4 semanas de `setup_type` limpio. Si no, se calibra sobre nada — el error que la metodología del proyecto evita.

### P3 — Backup + logs `[DT-3, DT-4]`
**Qué**: `tools/backup_db.py` con `sqlite3.Connection.backup()`, rotación 7 días, en el arranque del exe. `RotatingFileHandler` en `logging_setup.py` → `%APPDATA%\AIdan\logs\aidan.log` (10 MB × 5).
**Por qué**: 566 trades irreemplazables sin copia; el incidente del 14-jun quedó sin causa por falta de logs y va a repetirse.

### P4 — Decidir la composición de tracks `[DT-5]`
**Qué**: apagar la ejecución direccional de `news` (n=22, −$38,20, PF 0,23) — el track cuyo generador de señal ya se midió con **cero habilidad direccional** (24-jul: Fisher p=0,92, anti-skill vs el drift). No es una decisión de PnL con n chico, es la consecuencia de una medición causal ya cerrada. Poner `smc` y `h1` en observación explícita con umbral de decisión pre-declarado.
**Por qué**: `m15 + structure` ya es rentable (+$31,88, WR 44,7 % > breakeven 41,6 %). Lo que hay que hacer no es encontrar edge nuevo, es **dejar de financiar los tracks que no lo tienen**.
**Nota sobre "mejorar, no sacar"**: entiendo la regla y la comparto para la mayoría de los casos. Pero `news` ya recibió su intento de mejora (v3.47.0, prompt postura-primero) y el propio análisis de ese fix concluyó que *"NO vuelve rentable a news — el edge direccional sigue ~0"*. Mejorar tuvo su turno. Apagar la *ejecución* no borra el track: las alertas se siguen generando y midiendo, y si el fix del prompt muestra discriminación real en la re-medición forward, se reactiva con evidencia.

### P5 — Calibración de Platt sobre `confidence` `[DT-7]`
**Qué**: `tools/fit_calibration.py` — ajusta `P(win) = 1/(1+exp(A·score+B))` sobre los 139 limpios, guarda `{A, B, fit_date, n}` en JSON, y `technical.py` expone `calibrated_p_win` **junto** a `confidence` (sin reemplazarla). Refit mensual sobre ventana móvil, congelado entre refits.
**Por qué**: 2 parámetros es lo único que n=139 banca ([KDnuggets](https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling)). Convierte un número con Brier 0,369 en una probabilidad usable, y **desbloquea el sizing por Kelly fraccionario por track**, que es la mejora de riesgo más grande disponible.
**Verificación**: comparar Brier calibrado vs la constante 0,37 en held-out. Si no baja de 0,23, no se activa. Criterio pre-declarado.

### P6 — Higiene de DB `[DT-6]`
**Qué**: `_connect()` centralizada con `WAL` + `busy_timeout=5000`; reemplazar los 92 `sqlite3.connect`.

### P7 — Arreglar los tests y cubrir el path de ejecución `[DT-8, DT-10]`
**Qué**: (a) los 27 fallos actuales caen casi todos con P1; arreglar los 2 de `test_db.py`. (b) Tests nuevos sobre `mt5_executor.open_position` (idempotencia, dirección de SL/TP, sizing con SL variable) y `compute_adaptive_sl_tp` (los bounds de R:R). Con MT5 mockeado.
**Por qué**: **bloqueante para cuenta real.** Un error de dirección o de lote en demo cuesta pixels; en real cuesta plata.

### P8 — Guard con contador de errores `[DT-9]`
**Qué**: `src/common/guard.py`; reemplazar los `except: pass` de las rutas de decisión; escribir a la tabla `errors` (existe, 0 filas) y mostrar el contador en el dashboard.
**Por qué**: cuatro features murieron en silencio de forma documentada. Esto convierte la clase entera en algo visible.

### P9 — Validación purgada para experimentos offline `[DT-11]`
**Qué**: `tools/cv_purged.py` con purge + embargo; usarlo en cualquier re-intento de ML.
**Por qué**: los splits únicos produjeron AUC 0,75 que era 0,57 ([López de Prado](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)).

### P10 — Unificar los tres loops de scan `[DT-12]`
**Qué**: `src/analyzer/scan_loops.py` con `scan(track_cfg)`.
**Por qué**: los tres son copias; los bugs de M15/H1 vinieron de divergencia. Refactor de riesgo medio → después de P7 (tests primero).

### Tecnologías evaluadas y **descartadas** para este proyecto

Lo digo explícitamente porque parte del valor de una auditoría es cerrar puertas:

- **NautilusTrader / VectorBT / backtrader / Lean**: no. Migrar el motor sería un reescritura completa, y el cuello de botella de AIdan **no es el motor de backtest** — es la selección de entradas y el bucle de aprendizaje. Vale conocer el criterio ([BullAlert 2026](https://bullalert.ai/blog/best-python-backtest-engines-2026/)): VectorBT para triaje rápido de señales, Nautilus cuando necesitás fills realistas y paridad live. Si algún día se hace research masivo de parámetros, VectorBT como *herramienta de research paralela* (no como reemplazo) sería lo primero.
- **MLflow / W&B**: no todavía. Con un modelo de 2 parámetros, un JSON versionado alcanza. Reevaluar si alguna vez hay >5 modelos en producción.
- **Feast (feature store)**: no. Feature stores resuelven skew train/serving entre equipos; acá hay un proceso y `entry_context` ya guarda las features en el momento — que es la parte que un feature store compra.
- **Grafana / ELK**: no. Un dashboard propio + Telegram ya cubren; el gap es logs en disco, no una stack de observabilidad.
- **RL para trading**: no. Con n=139 y edge marginal, RL es el enfoque con peor ratio señal/complejidad disponible.
- **HMM para detección de régimen**: **quizás, y con cautela**. La literatura respalda que evitar operar en regímenes de alta volatilidad mejora el Sharpe ([QuantifiedStrategies](https://www.quantifiedstrategies.com/hidden-markov-model-market-regimes-how-hmm-detects-market-regimes-in-trading-strategies/)). **Pero el proyecto ya midió esto el 14-jun y ninguna celda régimen×trigger pasó el gate**, y el "chop tóxico" del 3-jul se dio vuelta el 17-jul. Un HMM sobre la misma data daría el mismo resultado con más maquinaria. Reevaluar solo con 300+ limpios.

---

## 8. Roadmap en 3 olas

### 🌊 Ola 1 — Semana 1: parar la sangría y tapar los huecos (riesgo ~0)
Nada acá cambia cómo AIdan decide, salvo P4.

| # | Acción | Esfuerzo | Toca el vivo |
|---|---|---|---|
| P1 | Rotar y externalizar credenciales | 1 h | no |
| P3 | Backup diario de la DB + logs rotativos | 2 h | no |
| P2a | Poblar `setup_type` (solo escritura, paso 6 sigue apagado) | 1 h | no |
| P6 | WAL + busy_timeout + `_connect()` | 1 h | no |
| P7a | Arreglar los 27 tests rotos | 2 h | no |
| **P4** | **Decidir composición de tracks (news)** | 1 h | **sí** |
| DT-13 | Declarar deps ML en `requirements.txt` | 15 min | no |

**Resultado esperado**: credenciales seguras, data respaldada, incidentes diagnosticables, suite verde. Y si se toma P4, el período limpio pasa de −$24,73 a un run-rate de +$31,88 sobre la misma ventana.

### 🌊 Ola 2 — Mes 1: cerrar bucles y hacer visible lo invisible

| # | Acción | Esfuerzo |
|---|---|---|
| P8 | Guard + contador de errores en rutas de decisión | 1 día |
| P7b | Tests del path de ejecución (sizing, SL/TP, idempotencia) | 2 días |
| P5 | Calibración de Platt + validación contra Brier constante | 2 días |
| P2b | Con 3-4 sem de `setup_type` limpio: reactivar el paso 6 **si** pasa el gate | 0,5 día |
| — | Sizing Kelly fraccionario **por track**, sobre `calibrated_p_win` | 1 día |
| — | Stop por racha (complemento al daily loss limit) | 0,5 día |

**Criterio de éxito de la ola**: Brier calibrado < 0,23 en held-out, y el bucle setup→WR→confianza cerrado y medible. Si Platt no baja el Brier, **no se activa** — y eso también es un resultado.

### 🌊 Ola 3 — Trimestre 1: estructura y camino a real

| # | Acción | Esfuerzo |
|---|---|---|
| P10 | Unificar los 3 loops de scan (después de tener tests) | 3-4 días |
| P9 | `cv_purged.py` + Deflated Sharpe para experimentos offline | 2 días |
| — | Drift monitoring mensual (PSI/KS sobre `entry_context`) | 1 día |
| — | Lock de concurrencia en el cierre del PM (deuda ya identificada, **bloqueante para real**) | 1 día |
| — | Checklist de cuenta real: PF>1,2 sostenido en 100+ trades por track + suite verde + logs + backup | — |
| — | Reevaluar ML **solo si** hay 300+ limpios y CV purgada da AUC>0,60 robusto | — |

---

## 8-bis. Hallazgo NUEVO: el bug que los logs cazaron a los 60 segundos

Añadido el 31 Jul, después de implementar la Ola 1. Vale la pena porque **valida la inversión en logs** mejor que cualquier argumento: apenas arrancó el exe v3.48.0 con el archivo de log activo, apareció esto en cada ciclo:

```
WARNING db  get_learning_adjustments failed: string indices must be integers, not 'str'
  File "src\common\db.py", line 3037, in get_learning_adjustments
TypeError: string indices must be integers, not 'str'
```

**Diagnóstico (verificado en código y contra la data real):** colisión de tipos entre dos ramas que escriben el mismo dict `adjustments['sl_tp_advice']`.

| Rama | Línea | Qué escribe |
|---|---|---|
| `sl_tp` | `db.py:2948` | `adjustments['sl_tp_advice'][trigger] = rec` → un **string** (`'increase_sl'`) |
| `post_trade` | `db.py:3036-3037` | `setdefault(_trigger, {...})` y después `bucket['sl_recs'].append(...)` → espera un **dict** |

Si una insight de `sl_tp` para el trigger X se procesa antes que una de `post_trade` del mismo X, `setdefault` devuelve el string ya guardado y `bucket['sl_recs']` explota.

**Confirmado en la data de las últimas 48 h:** `sl_tp` escribe string para `h1_structure`; `post_trade` con `widen/tighten` existe para `h1_structure`, `m15_structure` y `structure` → **colisión real en `h1_structure`**. Y como el `try` envuelve el `for` completo, el crash **aborta toda la agregación**: el advice de `m15_structure` y `structure` se pierde también.

**Impacto:** `sl_tp_advice` alimenta `compute_adaptive_sl_tp` en los 5 tracks (`AIdan_TodoEnUno.py:1748, 2063, 2343, 2610, 3393`) — o sea que es la **ruta viva de SL/TP**. Es el octavo mecanismo de aprendizaje roto, y encaja exacto en la "clase de bug" de §1.2: llevaba meses fallando en cada ciclo sin que nadie lo viera, porque el `logger.warning` no iba a ningún archivo.

**NO se arregló en esta pasada, a propósito.** Tres razones:

1. **Cambia el comportamiento vivo.** Hoy la agregación muere y el advice queda vacío; arreglarla hace que empiece a mover SL/TP de verdad. Eso es un cambio significativo en la ruta de trading → necesita OK explícito (regla del proyecto).
2. **Contaminaría las mediciones forward ya agendadas.** La primera semana de agosto hay que medir el tighten de v3.46.0 y el fix de news de v3.47.0. Revivir un ajustador de SL/TP en el medio mezcla dos efectos y arruina las dos lecturas.
3. Es el mismo razonamiento por el que el paso 6 de `dynamic_conf` quedó apagado: revivir un bucle de aprendizaje **y** medir un cambio al mismo tiempo no permite atribuir el resultado.

**Recomendación:** arreglar la colisión de tipos (que la rama `post_trade` no pise un string, y unificar el formato de `sl_tp_advice`) **después** de las lecturas forward de la primera semana de agosto, y activarlo como cambio único y medido. La regla del proyecto de "un cambio a la vez" aplica igual acá.

---

## 9. Lo que está bien y no hay que tocar

Una auditoría que solo lista problemas miente por omisión. Esto está por encima del promedio de proyectos de este tipo:

- **La metodología.** El gate de significancia (`significance.py`) con Wilson CI + binomial, la regla del cutoff −300 s contra lookahead, la insistencia en `mt5_pnl` real sobre outcomes simulados, y el patrón shadow→medir→activar. Ese aparato **funcionó**: rechazó correctamente el hour gate, los entry gates (30 combos), fade-chop tres veces, el sesgo direccional, y cuatro intentos de ML. Vale más que cualquier feature del código.
- **El track record de decisiones evitadas.** Bounce-skip, ML v3.35.0, gates v3.34.0 — tres "arreglos" que habrían empeorado el sistema, frenados por medir antes.
- **La ruta de ejecución.** Sizing, BE/trailing (solo tightening), idempotencia, handoff señal→orden, P&L broker-truth. Verificado línea por línea en auditorías previas y coincide con lo que leí.
- **`entry_context` capturado en el momento.** 0 % faltante en data limpia. Es la razón por la que las mediciones recientes son confiables, y muchos proyectos de este tipo nunca llegan ahí.
- **El fix de `tp_cap` (v3.40.18)**: payoff realizado 1,40. Funcionó.

---

## 10. La pregunta incómoda

Con los números en la mano, la situación es: **AIdan tiene dos tracks rentables (`m15`, `structure`, PF 1,33 y 1,17) y tres que no lo son.** El agregado da PF 0,864 porque los perdedores pesan.

Eso significa que la pregunta "¿cómo mejoro AIdan?" tiene hoy una respuesta más aburrida y más efectiva que cualquier feature nueva: **dejar de operar lo que ya se midió sin edge, y construir el aparato (calibración + sizing por track) que permita ponerle más peso a lo que sí lo tiene.**

Lo que **no** recomiendo es agregar un detector de régimen, un modelo nuevo, o un shadow más. El proyecto ya tiene siete mecanismos de aprendizaje construidos y uno conectado. El cuello de botella no es la falta de ideas — es que las ideas construidas no están enchufadas.

---

*Informe generado el 31 Jul 2026. Mediciones reproducibles: el script de análisis está en el scratchpad de la sesión; los números de §0, §2.3 y §2.4 salen de consultas directas sobre `trade_archive` filtrando `mt5_pnl IS NOT NULL AND created_at >= '2026-06-20'`.*

## Fuentes

- [A Deep Dive into Calibration: Platt Scaling, Isotonic Regression, Temperature Scaling — KDnuggets](https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling)
- [Predicting Good Probabilities With Supervised Learning — Niculescu-Mizil & Caruana, ICML 2005](https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf)
- [How do you calibrate a trading probability? — Alphora](https://alphora.io/learn/how-do-you-calibrate-a-trading-probability/)
- [The 10 Reasons Most Machine Learning Funds Fail — López de Prado (GARP)](https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf)
- [Purged cross-validation — Wikipedia](https://en.wikipedia.org/wiki/Purged_cross-validation)
- [Kelly Criterion: Position Sizing for Algo Traders — Papers With Backtest](https://paperswithbacktest.com/course/kelly-criterion-position-sizing)
- [Why Algorithmic Trading Fails: The Math Behind Losses](https://alexbobes.com/tech/the-brutal-truth-about-algorithmic-trading/)
- [Best Python Backtest Engines in 2026: NautilusTrader vs Backtrader vs VectorBT](https://bullalert.ai/blog/best-python-backtest-engines-2026/)
- [What is data drift in ML, and how to detect and handle it — Evidently AI](https://www.evidentlyai.com/ml-in-production/data-drift)
- [Timeseries Databases Performance — Testing 7 alternatives](https://medium.com/@ev_kozloski/timeseries-databases-performance-testing-7-alternatives-56a3415e6e9e)
- [Hidden Markov Model Market Regimes — QuantifiedStrategies](https://www.quantifiedstrategies.com/hidden-markov-model-market-regimes-how-hmm-detects-market-regimes-in-trading-strategies/)
