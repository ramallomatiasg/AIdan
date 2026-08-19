# RESEARCH_INVESTIGATION.md — investigación exhaustiva + análisis crítico

**Fecha**: 19 Ago 2026 · **Versión viva**: v3.57.2 · **Modo**: investigación web + verificación contra código y DB reales.
**Encargo**: buscar mejoras en (A) generación de señal, (B) ejecución de la orden, (C) lo que otros ya implementaron, (D) arquitectura, (E) ángulos no contemplados — **explícitamente lo que `AUDIT_REPORT.md` (31 jul) y `docs/research_mercado_2026-08-19.md` NO cubrieron**.

> **Cómo leer.** Cada hallazgo trae: fuente (URL), qué propone, **cuán raro o mainstream es**, aplicabilidad a AIdan, esfuerzo, y si el audit ya lo tocó (§).
> Semáforo: 🟢 corrobora algo ya medido · 🟡 idea testeable · 🔴 cierra una puerta · ⚫ **hallazgo de código verificado en esta sesión** (no es research: lo ejecuté).
> **Advertencia de calidad de fuentes**: buena parte del contenido "de trading" en internet es marketing. Marco explícitamente lo que no tiene n / t-stat / metodología. Hay un caso en §A.6 donde una fuente popular **contradice una medición propia de AIdan** — y gana AIdan.

---

## 1. Resumen ejecutivo (10 líneas)

1. **Lo más valioso que encontré no es una técnica nueva: es un mecanismo tuyo que existe y está desconectado.** `src/common/slippage_tracker.py` define `log_fill()` — expected vs actual price, spread al fill — y **no se llama desde ningún lado**; `slippage_log` tiene **0 filas** (verificado). El TCA que PROGRESS.md pone como prioridad #2 y "bloqueante para cuenta real" está **escrito al 70 %**. Es el 9º mecanismo muerto de la familia que ya documentó el audit (§B.1).
2. **Segundo hallazgo de código**: en cuenta **ECN / Market Execution** (ICMarkets Raw), el parámetro `deviation: 50` que AIdan manda en 5 sitios **probablemente lo ignora el servidor**. El control de slippage que el sistema cree tener puede no existir (§B.2).
3. **Frente A**: la línea más fértil y no explorada es la de **features microestructurales derivables de OHLCV + tick_volume** (Roll, Corwin-Schultz, Kyle λ, Amihud, VPIN aproximado) — hay implementación de referencia MT5 publicada en 2026. Son **features, no filtros** ⇒ compatibles con "no bajar frecuencia" (§A.1).
4. **Frente A, puerta que se cierra**: barras alternativas (tick/imbalance/runs bars). Un estudio **sobre EURUSD real** confirma la mejora estadística (kurtosis 14,0 → 5,3) y demuestra que **no se traduce en edge** (AUC 0,42-0,55, p=0,10). No lo intentes (§A.4).
5. **Frente A, corrección al audit**: para calibrar, **beta calibration (3 params) domina a Platt** en la literatura reciente. Platt ya falló su gate el 5-ago (Brier 0,2522 vs 0,2424); repetir *el mismo método* con +60 trades es repetir el experimento. Beta es un método distinto, mismo presupuesto estadístico (§A.7).
6. **Frente B**: **MFE/MAE nunca se guardan**. Sin MFE no se puede responder "¿el TP estaba mal puesto o la entrada estaba mal?" — que es *exactamente* la pregunta abierta desde el 19-jun. Es la instrumentación de mayor ratio del informe (§B.3).
7. **Frente E, top**: existe metodología formal y publicada (2026) para lo que llamaste "shadow book": **Post-Rejection Follow-up Sampling** y la métrica **save-to-miss ratio**. AIdan tira **2.115 skips de `ATR too low`** al log sin medir jamás qué habrían hecho. Es la única forma honesta de saber si `M15_ATR_FLOOR=8` salva o cuesta (§E.1).
8. **Frente E, desbloqueo estructural**: el techo del **lote mínimo 0,01** bloquea Kelly, meta-labeling y el track D1 — aparece 3 veces en tus docs como "depende del capital". **Una cuenta CENT da 100× de granularidad con el mismo dinero.** Es una decisión de cuenta, no de código, y hoy no está contemplada en ningún documento (§E.2).
9. **Frente D**: el salto a event-driven/Kafka/Postgres **no está justificado** y lo confirmo. Lo que sí cambia el día a día es **DuckDB leyendo la SQLite/Parquet para research** (sin migrar la operativa) y la disciplina de reproducibilidad config-hash + Parquet cache que publicó la serie MT5 Blueprint, sin MLflow ni DVC (§D).
10. **Lo que NO recomiendo, con evidencia**: LLM leyendo charts (51 % de acierto direccional en auditoría independiente), RL, HMM, PatchTST/N-BEATS, migrar de motor de backtest. Y bajarle prioridad definitiva a "buscar la familia de patrón correcta".

---

## 2. Frente A — Entrada de señales (signal generation)

### A.1 🟡 Features microestructurales derivables de OHLCV + tick_volume — **la mejor línea nueva**

**Fuentes**:
- [Feature Engineering for ML (Part 6): Microstructural Features in MQL5](https://www.mql5.com/en/articles/22734)
- [Feature Engineering for ML (Part 5): Microstructural Features in Python](https://www.mql5.com/en/articles/22733)
- [Market Microstructure in MQL5 (Part 6): Order Flow](https://www.mql5.com/en/articles/22939)
- [MT5-OrderFlow-Footprint-Engine (GitHub)](https://github.com/Vandoriz/MT5-OrderFlow-Footprint-Engine)

**Qué proponen.** Siete features por vela **solo con OHLCV**: Roll spread y Roll impact (covarianza serial de cambios de precio), Corwin-Schultz spread y sigma (pares de high-low adyacentes), **Kyle's lambda** (pendiente OLS de Δprecio contra volumen firmado), **Amihud ILLIQ** (|retorno| / volumen), Hasbrouck lambda. Y por separado, **VPIN aproximado**: se estima el split comprador/vendedor por dónde cierra la vela dentro de su rango (tick rule) × tick_volume.

**Rareza**: los estimadores son **académicos clásicos** (Roll 1984, Kyle 1985, Amihud 2002, Corwin-Schultz 2012) — mainstream en institucional, **raros en retail forex**. La implementación MT5 es de junio 2026, o sea nueva.

**Aplicabilidad a AIdan: ALTA, y por la razón correcta.** Tu restricción #1 es *no bajar frecuencia*. Estos son **features de contexto**, no gates: entran en `entry_context` clasificados en el momento (el patrón que ya usás y que hace confiables tus mediciones), no bloquean nada. Con eso, dentro de 4-6 semanas podés preguntar cosas que hoy son inrespondibles: *¿los perdedores de m15 entran con Amihud alto (mercado ilíquido) o con Kyle λ alto (mucho impacto por unidad de flujo)?*

**Límite honesto y explícito** (lo dice la propia fuente): `CopyTickVolume()` de MT5 devuelve **cuenta de cambios de precio, no de trades**. Eso degrada los estimadores de λ de *cardinales* a *ordinales* — sirven para "régimen alto/bajo", no para medir impacto en dólares. Y el estudio VPIN citado reporta un rango de 0,45-0,62 con elevaciones de 6 % en estrés: **"weak but directionally correct"**, textual, y advierte que no debe leerse como probabilidad calibrada. ⇒ **Úsalos como features de régimen, nunca como probabilidad.**

**Esfuerzo**: bajo-medio. Son ~80 líneas de numpy sobre las velas que `price_feed` ya baja. Riesgo sobre el vivo: **cero** si solo se escriben a `entry_context`.

**¿Lo tocó el audit?** No. El audit §2.1 auditó `dynamic_conf` pero no propuso features nuevas; §3.2 dijo "no aprendas P(win) desde features" — que sigue siendo cierto **para el modelo**, pero no impide **registrar** features para diagnóstico.

---

### A.2 🟡 Detección de régimen sin HMM: change-point y tests de quiebre estructural

**Fuentes**:
- [Feature Engineering for ML (Part 9): Structural Break Tests in Python](https://www.mql5.com/en/articles/23158)
- [Change-Point Detection in Financial Time Series Using PELT (ACM, 2025)](https://dl.acm.org/doi/10.1145/3773365.3773532)
- [Bayesian Online Changepoint Detection in Python](https://sesen.ai/blog/bayesian-online-changepoint-detection)
- [Bayesian Autoregressive Online Change-Point Detection with Time-Varying Parameters (arXiv 2407.16376)](https://arxiv.org/pdf/2407.16376)

**Qué proponen.** El audit descartó HMM (§7) con buen argumento. Pero hay una familia distinta que **no es un modelo latente entrenado**, sino **estadísticos calculables por vela**:
- **CUSUM Chu-Stinchcombe-White**: score de "excedente sobre el valor crítico".
- **SADF** (Supremum ADF): un score continuo de **explosividad** — negativo = mean-reverting, ~0 = random walk, positivo = explosivo.
- Chow-type DF, QADF/CADF (variantes robustas a outliers).
- **BOCPD**: mantiene una distribución sobre "hace cuánto empezó el régimen actual", actualizable en tiempo constante por observación — apto para loop vivo.

El autor de la serie MT5 lo plantea como **selector de régimen**: mean-reversion en régimen estable, trend-following en fase explosiva, exposición reducida en la zona de raíz unitaria.

**Rareza**: SADF/CUSUM son López de Prado, **conocidos en quant**, casi inexistentes en retail forex. BOCPD es mainstream en ML, raro en trading retail.

**Aplicabilidad: MEDIA-ALTA, con una advertencia grande.** El atractivo es que **SADF es un escalar continuo por vela**, o sea el mismo formato que `avg_range_pips` — se guarda en `entry_context` y listo. Y responde con un número a la pregunta que AIdan viene contestando con reglas ad hoc ("¿esto es chop o tendencia?").

**La advertencia**: AIdan **ya midió régimen × trigger el 14-jun y ninguna celda pasó el gate**, y el "chop tóxico" del 3-jul se dio vuelta el 17-jul. Un SADF sobre la misma data puede dar el mismo resultado con más maquinaria — que es exactamente lo que el audit dijo del HMM. **La diferencia defendible**: SADF/CUSUM son **deterministas y sin entrenamiento**, así que el riesgo de overfit es estructuralmente menor que un HMM ajustado. ⇒ Registrar sí; **usar para decidir, no antes de 100+ trades con el campo poblado**.

**Esfuerzo**: medio (SADF con ventanas expandidas es O(n²) ingenuo — hay que cachear). `ruptures` (PELT) es pip-installable pero es **offline/batch**: sirve para research, no para el loop.

**¿Audit?** §7 descartó HMM. Esta familia no aparece.

---

### A.3 🟡 Kaufman Efficiency Ratio / Choppiness Index — la versión barata de A.2

**Fuentes**: [Kaufman Efficiency Ratio — LuxAlgo](https://www.luxalgo.com/library/concept/kaufman-efficiency-ratio/) · [Efficiency Ratio Strategy — QuantifiedStrategies](https://www.quantifiedstrategies.com/efficiency-ratio/) · [KER — StrategyQuant](https://strategyquant.com/codebase/kaufmans-efficiency-ratio-ker/)

**Qué propone.** ER = |cambio neto en N| / Σ|cambios barra a barra|. Cerca de 1 = movimiento limpio; cerca de 0 = todo ida y vuelta. Choppiness Index hace lo mismo con true range (ve el rango intrabar, ER solo ve cierres). Umbral típico de "tendencia persistente": ER > 0,3-0,4.

**Rareza**: **mainstream** (Kaufman, 1995). Que sea viejo no lo hace malo — lo hace barato.

**Aplicabilidad: ALTA como feature.** Es literalmente **5 líneas** y mide exactamente lo que AIdan intenta capturar con `M15_ATR_FLOOR`: la diferencia es que **ATR mide cuánto se movió, ER mide si el movimiento fue a algún lado**. Un mercado de agosto con ATR bajo *y* ER alto es un drift limpio (operable); ATR bajo *y* ER bajo es chop (que es lo que estás tratando de evitar). **Eso separa los dos casos que hoy el piso de ATR mete en la misma bolsa** — y es la crítica exacta que ya se le hizo al piso fijo (perdió 59 % de frecuencia en agosto).

**Contra**: sin evidencia numérica publicada específica de forex intradía en las fuentes que encontré (las páginas son didácticas, no estudios con n). ⇒ 🟡, no 🟢.

**Esfuerzo**: trivial. **Candidato #1 para meter en `entry_context` esta semana**, junto con el percentil de ATR que ya está rankeado #1 en `research_mercado`.

---

### A.4 🔴 Barras alternativas (tick / imbalance / runs bars) — **PUERTA CERRADA con evidencia EURUSD**

**Fuente**: [Beyond the Clock (Part 4): Efficacy of Bars on Trending and Mean-Reversion Strategies — MQL5](https://www.mql5.com/en/articles/23310) · contexto: [Information-Driven Bars — QuantStrategy.io](https://quantstrategy.io/blog/information-driven-bars-moving-beyond-time-based-financial/)

**Qué dice.** Cuatro familias de barras (time, tick, tick-imbalance, tick-runs) sobre **EURUSD 2022-2023**, con RSI, Bollinger y ADX/DI.

| Resultado | Valor |
|---|---|
| Exceso de kurtosis, time bars | 14,0 |
| Exceso de kurtosis, tick / tick-runs | ~5,3 (−56 %) |
| AUC out-of-sample, todas las celdas | 0,42–0,55 |
| Media por familia | time 0,47 · tick 0,50 · imbalance 0,51 · runs 0,49 |
| Mejor celda (tick + RSI) | 0,550 |
| Test de permutación | **p = 0,10 — no significativo** |

Conclusión textual del autor: *"Better-conditioned returns are a property of the sampling; they do not automatically become a property of a strategy."*

**Por qué importa acá.** López de Prado y todo el retail que lo cita repiten "dejá de usar time bars". Es la recomendación #1 de AFML y suena a mejora estructural gratis. **Es falsa para este caso de uso, y está medida en tu propio par.** Nota adicional del estudio: en FX solo-cotizaciones, **seis de las variantes volumen/dólar de AFML colapsan a tick bars** porque no hay volumen real. AIdan usa `tick_volume`, que es cuenta de cambios de precio (mismo problema).

**Veredicto: NO hacer.** Y agregar a la tabla de "descartado con fundamento" de `research_mercado` §11.

**¿Audit?** No aparece. Es una puerta que estaba abierta.

---

### A.5 🟡 Conformal prediction — abstención calibrada, pero ojo con la fuente

**Fuentes**: [Exploring Conformal Forecasting of Financial Time Series — MQL5](https://www.mql5.com/en/articles/18324) · [Conformal Prediction for Reliable Stock Selections (PMLR 2025)](https://proceedings.mlr.press/v266/kaya25a.html) · [Drift-Aware Spectral Conformal Prediction for Non-Exchangeable Streaming Data (arXiv 2606.15953)](https://arxiv.org/pdf/2606.15953) · [MAPIE en mercados financieros](https://www.tildee.com/harnessing-conformal-forecasting-in-financial-markets-quantifying-uncertainty-and-managing-risk-with-mapie/)

**Qué propone.** En vez de "P(win) = 0,62", devolver un **conjunto de predicción** con cobertura garantizada: `{Buy}` = confianza alta → tamaño completo; `{Buy, Sell}` = ambigüedad → tamaño reducido; `{}` (vacío) = incertidumbre extrema → no operar. La garantía es finita-muestra y **libre de distribución**.

**Rareza**: **muy de moda en ML (2023-2025), casi inexistente en retail trading.** Es el "ángulo no contemplado" más legítimo del frente A.

**Aplicabilidad: MEDIA. Y acá viene el análisis crítico.** El artículo MT5 reporta **"92-96 % de accuracy sobre data filtrada"** en EURUSD 2017-2025. **Ese número no es creíble como está** y hay que decirlo: (a) es accuracy *sobre el subconjunto que el meta-modelo aceptó* (6.715 de 29.663 = 22,6 %) — o sea, accuracy condicionada a la abstención, que no es comparable con nada; (b) no reporta el WR del comparador ni PnL neto de fricción; (c) el propio autor admite que la **exchangeability se viola en mercados no estacionarios**, que es la hipótesis de la que cuelga toda la garantía. Aplicá tu propio gate: **sin n, sin CI y sin broker-truth, es marketing técnico, no evidencia.**

**Lo que sí sobrevive del concepto**: la **abstención explícita como salida de tercer tipo**. Hoy AIdan tiene binario opera/no-opera. Un conjunto `{Buy, Sell}` no significa "no operar" — significa **"operar con menos tamaño"**, que es frecuencia-neutro. **Pero eso vuelve a chocar contra el lote mínimo 0,01** (§E.2). ⇒ **Conformal es dirección correcta, bloqueada por el mismo cuello que meta-labeling y Kelly.** No es prioridad hoy.

**Esfuerzo**: medio (MAPIE es pip-install, pero requiere un clasificador base — que AIdan no tiene y ya refutó 4 veces).

---

### A.6 🔴 Confluencia multi-timeframe "cuantificada" — **fuente popular refutada por tus propios datos**

**Fuentes**: [MTF Alignment & Confluence Scoring — LuxAlgo](https://www.luxalgo.com/library/concept/mtf-alignment-and-confluence-scoring/) · [Multi Timeframe Analysis — ShopForexEA](https://shopforexea.com/multi-timeframe-analysis/)

**Lo que circula.** "Un estudio de FXCM sobre 10.000 trades: los que tenían confirmación multi-frame ganaron 62 % vs 45 % de frame único"; "backtests en TradingView muestran 20-30 % de mejora de WR cuando tres timeframes alinean"; "MTFA corta trades perdedores hasta 40 %".

**Análisis crítico — esto hay que rechazarlo, y es importante que quede escrito.**
1. **No hay estudio citable.** No encontré el paper de FXCM, ni n, ni CI, ni período, ni metodología. La página que lo afirma es un sitio que vende EAs.
2. **Contradice frontalmente una medición propia de AIdan.** Checkpoint del 19-jun: *"todo alineado = PEOR (bias-fresh 23 % WR vs baseline 36)"*, con la explicación mecánica de que la alineación total marca **agotamiento**, no confirmación. Y el paso 8 de `dynamic_conf` fue **neutralizado a propósito en v3.7.0** exactamente por esto (audit §2.1).
3. **Es la falacia de siempre**: la confluencia perfecta es rara *y* tardía. Cuando 4 timeframes coinciden, el movimiento ya ocurrió.

**Veredicto: 🔴 no implementar "confluence score" naive.** El único ángulo que sobrevive es el **opuesto**: usar el grado de alineación como proxy de *agotamiento*, no de calidad — y eso AIdan ya lo midió y ya lo neutralizó. **Cerrado.**

**Valor de haberlo buscado**: sirve como ejemplo de por qué el filtro de fuentes importa. Si alguien trae "62 % vs 45 %" en una sesión futura, esto es la respuesta.

---

### A.7 🟡 Calibración: **beta calibration** en lugar de Platt — corrección técnica al audit

**Fuentes**: [Beta vs Platt vs Isotonic — MetricGate](https://metricgate.com/blogs/beta-calibration-vs-platt-vs-isotonic/) · [An introduction to calibration (part II) — Abzu](https://www.abzu.ai/data-science/calibration-introduction-part-2/) · [Classifier Calibration: a survey (arXiv 2112.10327)](https://arxiv.org/pdf/2112.10327) · [Classifier Calibration at Scale (arXiv 2601.19944)](https://arxiv.org/pdf/2601.19944) · [MT5 Blueprint Part 12: Probability Calibration](https://www.mql5.com/en/articles/21938)

**El estado del arte que el audit no incorporó.** El audit §3.2 planteó la elección como **Platt (2 params) vs isotónica (~k bins)** y eligió Platt por presupuesto de muestra. Correcto en 2005; incompleto en 2026. **Beta calibration** (Kull, Silva Filho & Flach) tiene **3 parámetros** (dos de forma + uno de localización) y:
- Asume dos distribuciones Beta en vez de dos normales con **igual varianza** — que es el supuesto de Platt y es el que se rompe cuando los scores están sesgados.
- Admite mapas **inverse-sigmoid y la identidad**, así que **puede no hacer nada** si el score ya está calibrado. Platt no puede: siempre deforma.
- Cita textual de la comparativa: *"beta calibration is the safe default for most binary classifiers; it dominates Platt and matches isotonic with one-twentieth the variance"*.
- La literatura documenta que **Platt entrega probabilidades subóptimas — incluso peores que el score crudo — cuando la distribución de scores es muy asimétrica.**

**Por qué esto importa concretamente acá.** El 5-ago Platt **falló su gate** (Brier 0,2522 vs constante 0,2424) y PROGRESS.md §5 concluye: "corresponde en 3-4 semanas". **Pero repetir Platt con +60 trades es correr el mismo experimento.** Y la distribución de `confidence` de AIdan **es exactamente el caso patológico**: está apilada en 60-90 con ceiling en 80, o sea fuertemente asimétrica y truncada. Hay una hipótesis específica y contrastable: **Platt no falló porque no haya señal de ranking, falló porque su forma funcional no encaja con esa distribución.** Beta la puede encajar.

**Contrapunto honesto**: el MT5 Blueprint Part 12 recomienda **Platt por debajo de ~200 observaciones** e isotónica por encima; beta no lo evalúa. Con n≈200 limpios, beta (3 params) sigue estando dentro del presupuesto — 66 obs/parámetro — pero **es un parámetro más de libertad y el gate tiene que ser el mismo o más duro**.

**Recomendación operativa**: cuando llegue el turno (3-4 semanas), correr **beta y Platt en la misma corrida, con el gate declarado antes** (Brier held-out < 0,2424, ambos comparados contra la constante), y quedarse con el que pase — **o con ninguno**. `tools/calibrate_confidence.py` ya tiene el andamiaje: es agregar una función.

**Esfuerzo**: bajo (`betacal` en PyPI, o 15 líneas: regresión logística sobre `[log(p), log(1−p)]`).

---

### A.8 🔴/🟡 Modelos de secuencia (PatchTST, N-BEATS, TCN) y auto-features (tsfresh)

**Fuentes**: [PatchTST — EmergentMind](https://www.emergentmind.com/topics/patchtst) · [tsfresh (GitHub)](https://github.com/blue-yonder/tsfresh) · [tsfresh paper — Neurocomputing](https://www.sciencedirect.com/science/article/pii/S0925231218304843) · [Bake off redux (arXiv 2304.13029)](https://arxiv.org/pdf/2304.13029)

**Estado**: PatchTST/N-BEATS/TCN dominan benchmarks de **forecasting de series largas y multivariadas** (electricidad, tráfico, ~10⁴-10⁶ observaciones). AIdan tiene **~200 trades limpios etiquetados**. tsfresh genera **794 features** por defecto con selección por tests de hipótesis (FRESH).

**Veredicto: 🔴 no.** Y el argumento no es "es complicado", es aritmético: el workflow del 31-may ya refutó LR/RF/XGB/HistGB a n=276 con AUC real 0,44-0,48, y **el hallazgo clave fue que `confidence` sola daba AUC ~0,59, mejor que los modelos completos**. Meter 794 features de tsfresh sobre 200 filas es la definición de sobreajuste; los propios foros de tsfresh advierten de eso. PatchTST sobre 200 etiquetas no es una opción seria.

**Lo único rescatable (🟡)**: tsfresh **como herramienta de research offline, una sola vez**, sobre **velas** (no trades) — donde sí hay 10⁵-10⁶ observaciones — para ver si alguna transformación de la serie tiene relación con la excursión posterior. Es el mismo molde que usaste en Fase 1/2 (medir sobre velas, no esperar trades). Prioridad baja; el riesgo de p-hacking con 794 features es enorme y **necesitaría el control de entradas aleatorias que ya usás en Fase 2**.

---

### A.9 🟡 Volatilidad: GARCH y volatilidad realizada

**Fuentes**: [Intraday FX Volatility-Curve Forecasting with Functional GARCH (arXiv 2311.18477)](https://arxiv.org/html/2311.18477v3) · [Forecasting Realized Volatility with Time Series Foundation Models (arXiv 2607.05291)](https://arxiv.org/pdf/2607.05291) · [Volatility Modeling — NordVarg](https://nordvarg.com/blog/volatility-modeling-garch)

**Qué aporta.** La aplicación práctica que la literatura destaca no es predecir dirección sino **ajustar distancia de stop, tamaño y elección de estrategia según el régimen de volatilidad previsto**. Los modelos GARCH multiplicativos con componente intradía capturan el patrón diario en U del FX.

**Aplicabilidad: BAJA-MEDIA hoy.** Razón: el paso de "predecir σ mejor" a "ganar plata" pasa por **modular el tamaño**, y eso está bloqueado por el lote mínimo (§E.2). Además AIdan ya usa ATR, que es un estimador crudo pero funcional de lo mismo, y **ya midió que escalar constantes por ATR EMPEORÓ** en H4/D1 (PF 1,40 → 1,02).

**Lo barato que sí sirve**: sustituir "ATR en pips" por **percentil de ATR contra las últimas ~100 barras** — que ya es el item #1 del ranking de `research_mercado`. GARCH es la versión cara de eso. **No lo persigas.**

---

## 3. Frente B — Entrada de operaciones (execution)

### B.1 ⚫🔴 **`log_fill()` existe y no se llama. `slippage_log` = 0 filas.**

**Verificado en esta sesión, no es research**:
```
grep -rn "log_fill" --include=*.py .   →  solo la definición en src/common/slippage_tracker.py:35
sqlite: select count(*) from slippage_log  →  0
```
El módulo `src/common/slippage_tracker.py` tiene el docstring *"Persiste cada fill: expected_price (orden) vs actual_price (fill) y spread real"*, crea la tabla `slippage_log` con las columnas correctas (`expected_price`, `actual_price`, `slippage_pips`, `spread_pips`), y **nadie invoca `log_fill()`**. Lo único que se usa del módulo es `is_spread_acceptable` (en `AIdan_TodoEnUno.py:1137`) y `get_slippage_stats` (dashboard, `main.py:1712`) — que lee una tabla vacía.

**Esto es exactamente el patrón que el audit §2.5 catalogó**: mecanismo construido, no enchufado. Es el **noveno**. Y es el más caro de los nueve, porque:
- PROGRESS.md §7 pone TCA como prioridad **#2** y **"bloqueante antes de cuenta real"**.
- `research_mercado` §8 dice que el TCA es *"lo único que distingue 'la estrategia empeoró' de 'la ejecución empeoró'"*.
- El incidente #625 (11,2 pips de slippage en un spike) quedó como **anécdota** porque no había registro sistemático.

**Fix**: llamar a `log_fill()` en `open_position()` con `request['price']` vs `result.price` y el spread leído en ese instante. **Es una línea más un import.** Y como `mt5_executor.py` ya recibe el `result` del `order_send`, el dato está ahí y se está tirando.

**Referencia externa para el modelo de costo completo**: [MT5 Blueprint Part 14 — Transaction Cost Modeling](https://www.mql5.com/en/articles/22372) (usa `CopySpread()` para la distribución histórica de spread, lee swap y comisión, exporta a CSV y convierte todo a retornos fraccionales) y el script [TransactionCostCollector](https://www.mql5.com/en/code/73173). Nota de esa fuente que aplica: **el slippage no se puede medir desde velas históricas, solo desde registros de ejecución en vivo o demo** — que es precisamente lo que `log_fill()` haría y no hace. Referencia de magnitud: 0,3-0,7 pips para orden a mercado en un mayor con liquidez normal.

**Prioridad: #1 del informe.** Esfuerzo: ~1 hora. Riesgo sobre el vivo: nulo (solo escribe).

---

### B.2 ⚫🟡 El `deviation: 50` puede ser decorativo en cuenta ECN

**Fuentes**: [Order execution modes by price and volume — MQL5 Book](https://www.mql5.com/en/book/automation/experts/experts_execution_filling) · [How to Set Slippage in MT5 — foro MQL5](https://www.mql5.com/en/forum/446038) · [Symbol trading conditions and execution modes](https://www.mql5.com/en/book/automation/symbols/symbols_execution_filling)

**Lo que dice la fuente, textual en sustancia**: el `deviation` máximo **solo se puede fijar si el bróker soporta "Instant Execution"** en ese símbolo, lo que típicamente ocurre en cuentas *dealing desk*. En cuentas **NDD / STP / ECN** el modo es **"Market Execution"**, que **no soporta limitar la desviación**: se acepta el precio que ofrezca el mercado.

**Estado en AIdan (verificado)**: `mt5_executor.py` manda `"deviation": 50` con el comentario `# points ... = 5 pips tolerance` en **4 sitios** (líneas 451, 739, 1003, 1063), y usa `ORDER_FILLING_IOC` para mercado con fallback a FOK/RETURN (líneas 437-464). La cuenta es **ICMarkets Raw Spread**, que es ECN.

**Implicancia**: la "tolerancia de 5 pips" que el código documenta **probablemente no existe**, y el slippage de 11,2 pips de #625 es consistente con eso (si el deviation funcionara, esa orden debería haber sido rechazada, no llenada 11 pips peor).

**Qué hacer** — y esto no es un cambio, es una **verificación**, que es lo correcto según tu principio rector:
```python
mt5.symbol_info("EURUSD").trade_exemode   # SYMBOL_TRADE_EXECUTION_MARKET / _INSTANT / _REQUEST / _EXCHANGE
mt5.symbol_info("EURUSD").filling_mode    # bitmask de fillings soportados
```
Si devuelve `MARKET`, entonces: (a) el comentario del código miente y hay que corregirlo; (b) **el único control de slippage disponible es no mandar la orden cuando el spread/volatilidad están mal** — o sea el `is_spread_acceptable` que ya existe, que pasa a ser **el** mecanismo, no un extra; (c) el TCA de B.1 pasa de "deseable" a **imprescindible**, porque es la única visibilidad que queda.

**Esfuerzo**: 10 minutos de verificación. **Es de las cosas más baratas y más importantes del informe antes de cuenta real.**

---

### B.3 🟡 **MFE / MAE — la instrumentación que falta para responder la pregunta abierta desde el 19-jun**

**Fuentes**: [MAE y MFE explicados — QuantifiedStrategies](https://www.quantifiedstrategies.com/maximum-adverse-excursion-and-maximum-favorable-excursion/) · [MFE & MAE: Complete Guide — TradesViz](https://www.tradesviz.com/blog/mfe-mae-charts/) · [MAE and MFE: How to Read Trade Excursion Data](https://traderssecondbrain.com/guides/mae-mfe-analysis)

**Qué es.** MAE = máxima pérdida no realizada que soportó el trade. MFE = máximo beneficio no realizado alcanzado. Concepto de John Sweeney, **mainstream en trading profesional**, ausente en AIdan.

**El uso que importa acá**: la métrica **MFE capture ratio = PnL realizado / MFE**. Y los dos patrones que la literatura marca como los más caros:
- *MFE grande, PnL chico* → tuviste el movimiento y no lo retuviste ⇒ **problema de SALIDA**.
- *MFE grande, PnL negativo* → estuviste arriba y lo convertiste en pérdida ⇒ **problema de GESTIÓN**.
- *MFE ≈ 0 y MAE inmediato* → **problema de ENTRADA**.

**Por qué esto es el hallazgo de instrumentación #1 del frente B.** La pregunta central de AIdan desde el 19-jun es *"¿entra mal, o gestiona mal?"*, y se contestó con proxies: `hwm_pips` del position manager (solo existe para los trades que el PM tocó), `max(0, pips)` como cota inferior en el backfill (limitación que el propio `backfill_directional_lessons.py` declara), y el criterio de `directional_lessons` (*"nunca se puso a favor <20 % del TP"*) que **es una aproximación de MFE construida a mano porque MFE no existe**.

**Con MFE/MAE reales, tres cosas hoy inrespondibles se vuelven una query**:
1. ¿El `tp_cap` está mal? → distribución de MFE de los ganadores contra el TP nominal.
2. ¿El BE de h1 corta ganadores? → es literalmente el criterio (c) del checkpoint del 22-ago, hoy planeado con un JOIN frágil sobre `position_manager_log`.
3. ¿`news` entra en el agotamiento? → MFE ≈ 0 con MAE inmediato lo prueba o lo refuta directamente.

**Cómo obtenerlo sin tocar la decisión**: el position manager ya corre cada 15 s y ya lee el precio. Guardar `running_max_favorable` / `running_max_adverse` por posición y persistirlos en `trade_archive` al cerrar. **Resolución de 15 s es más que suficiente** para trades de 15-180 min. Alternativa exacta y retroactiva: reconstruir con velas M1 de MT5 entre `created_at` y el cierre — pero eso es reconstrucción, y tu propia regla dice que la medición limpia se clasifica **en el momento**. ⇒ hacerlo forward.

**Esfuerzo**: bajo-medio (2 columnas + actualización en el loop del PM). **Riesgo sobre la decisión: cero.**

**¿Audit?** No aparece en ninguno de los dos documentos. Es un hueco real.

---

### B.4 🟡 Trailing: Chandelier Exit vs BE fijo

**Fuentes**: [ATR Trailing Stop Guide: Chandelier Exit — StratBase](https://stratbase.ai/en/blog/average-true-range-trailing-stop) · [Chandelier Exit Strategy — QuantifiedStrategies](https://www.quantifiedstrategies.com/chandelier-exit-strategy/) · [Volatility-Adjusted Stop Losses — Volatility Box](https://volatilitybox.com/research/volatility-adjusted-stop-losses/) · [Chandelier Exit — StockCharts](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit)

**Qué propone.** Stop anclado al **máximo alcanzado desde la entrada** menos k×ATR (típico 22 períodos, k=3). Nunca afloja. Se ensancha si la volatilidad sube (evita salidas prematuras en news) y se aprieta si baja.

**Números reportados** (⚠️ **no son forex ni intradía**): BTC/USDT 2020-2024 con entrada EMA-cross → Chandelier PF 1,61 vs trailing fijo 10 % PF 1,28 vs 5 % PF 1,09. S&P500 swing 2020-2024 → mejor expectancy por trade ($0,81) y menor max DD (10,2 %); el stop fijo tuvo mejor R:R (2,7:1) pero **el peor WR (38,2 %) porque el ruido lo tocaba constantemente**.

**Aplicabilidad: MEDIA, y con una advertencia que pesa.** AIdan **ya probó escalar constantes por ATR en H4/D1 y empeoró** (PF 1,40 → 1,02). Además el BE de h1 (v3.52.0) está **en medición hasta el ~22 ago**: meter un trailing nuevo ahora rompe la atribución, que es exactamente lo que tu metodología prohíbe.

**Lo que sí es interesante y encaja con tu diagnóstico**: la fuente dice que el stop fijo tuvo **el peor WR porque el ruido lo clipeaba**. AIdan tiene **SL fijo por track** (m15 15p, h1 40p — el audit §"revisión del cerebro" #2 demostró que el `max(floor, min(cap, ATR*0.8))` hace que el floor domine siempre ⇒ **el SL "adaptativo" es fijo**). Eso es la misma patología. **Pero el sizing de AIdan es riesgo$/(SL×10)**, así que ensanchar el SL no cuesta dólares, cuesta **lote** — y con lote mínimo 0,01 el margen es nulo. Otra vez el mismo cuello.

**Veredicto**: anotarlo para **después del 22-ago y del 1-sep**, como cambio único, y **solo si MFE/MAE (B.3) muestran que los ganadores efectivamente retroceden antes de cerrar**. Sin ese dato, es adivinar.

---

### B.5 🟢/🔴 Salidas parciales (scaling out) y re-entrada

**Fuentes**: [Scaling Out vs All-In All-Out — QuantStrategy.io](https://quantstrategy.io/blog/scaling-out-vs-all-in-all-out-a-data-driven-backtesting/) · [Should you EVER take Partial Profits? — Dave Mabe](https://davemabe.com/should-you-ever-take-partials) · [Assessing Stop-Loss and Re-Entry Strategies — Klement (Semantic Scholar)](https://www.semanticscholar.org/paper/Assessing-Stop-Loss-and-Re-Entry-Strategies-Klement/92428c679f6d1cc97d2e66d34087cadf90b69e5a) · [Optimal Stop-Loss and Take-Profit Parameterization for Autonomous Trading Agent Swarm (arXiv 2604.27150)](https://arxiv.org/pdf/2604.27150)

**Lo que dice la evidencia**: scaling out **mejora el Sharpe** (suaviza la curva) pero **baja el beneficio total** en mercados con tendencia; *"casi todas las estrategias dan menos beneficio total al incluir salidas parciales"*. Sobre re-entrada: el valor del stop-loss **solo se puede evaluar junto con la regla de re-entrada**, y el beneficio es fuertemente dependiente del régimen (mejor en bear secular que en bull).

**🔴 Veredicto para AIdan: NO, y por una razón dura y concreta.** Scaling out requiere **partir la posición**. Con lote mínimo 0,01, "salir de la mitad" **no existe**. La única forma es abrir 2 posiciones de 0,01 — lo que **duplica la comisión**, y la comisión ya es ~87 % del drag. Es el mismo argumento que mató al straddle de calendar (*"ojo doble comisión = problema #1"*). **Puerta cerrada por microestructura de la cuenta, no por falta de evidencia.**

**🟡 Lo que sí queda vivo**: la re-entrada. AIdan **ya tiene el fenómeno medido al revés** — el cooldown de 5 min post-pérdida pasó el gate (n=74, WR 24 % vs 38 %, p=0,010). O sea: **AIdan ya sabe que su re-entrada inmediata es mala**. La literatura dice que re-entrada + stop deben evaluarse juntos. ⇒ nada nuevo que hacer; **el hallazgo externo corrobora el cooldown**. 🟢

---

### B.6 🟡 Signal half-life — el marco que le falta al retry de ejecución

**Fuentes**: [Signal Half-Life: The Missing Piece in Most Trading Systems — OpenAlgo](https://blog.openalgo.in/signal-half-life-the-missing-piece-in-most-trading-systems-24824b102799) · [Signal Decay Analysis — MicroAlphas](https://microalphas.com/signal-decay-patterns/) · [Alpha Decay — Mark Best](https://markrbest.github.io/alpha-decay/) · [Signal Decay and Alpha Erosion — Foxholm](https://foxholm.com/q/concepts/signal-decay/)

**Qué propone.** Toda señal tiene una **vida media**: el tiempo en que se pierde la mitad de su edge. Rangos citados: momentum intradía / breakout continuation **minutos a horas**; señales de microestructura (order flow, bid-ask) **segundos a minutos, persistencia casi nula**; algunos hallazgos intradía rinden mejor con holds de 30-60 min y **caen fuerte después de 3 h**. Regla central: **el horizonte de trading debe igualar la vida media de la señal.**

**Rareza**: concepto **mainstream institucional**, prácticamente ausente en retail.

**Aplicabilidad a AIdan: ALTA y muy concreta.** Tenés dos casos ya documentados donde esto es la explicación:
1. **El retry de ejecución mandó a mercado una señal de 27 minutos** (#625, 11-jun) dentro de un spike, y fue la peor pérdida del día. En las NOTAS quedó como "candidato a medir: WR de fills tardíos vs inmediatos". **Este marco le da nombre y umbral.**
2. **News entra en la vela +2 con mediana de 8,9 min**, después de que se completó ~80 % del movimiento (medido el 19-ago). Eso **es** vida media agotada.

**Qué hacer, barato y frecuencia-neutro**: guardar `signal_age_at_fill_min` en `entry_context` (created_at → momento del `order_send`). Ya tenés los dos timestamps; **falta la resta y la columna**. Con eso, en 4-6 semanas se contesta con broker-truth si el fill tardío es tóxico — y si lo es, **el fix no es un filtro: es un TTL** (la señal caduca y se descarta, no se bloquea una familia). Un TTL **no baja la frecuencia de señales**, baja la frecuencia de **fills malos**; es la distinción que importa para tu restricción #1.

⚠️ Matiz honesto: técnicamente sí reduce trades ejecutados. Pero reduce **solo los que ya llegaban tarde**, que es una subpoblación identificable y pre-declarable, no una familia entera. Y la evidencia para activarlo tiene que pasar el gate igual.

---

### B.7 🟢 Spread filter en la entrada

**Fuentes**: [How Smart Trade Filters Improve EA Performance — MQL5 Blogs](https://www.mql5.com/en/blogs/post/770891) · [How to Disable Trading When Spread Is Too Wide — EarnForex](https://www.earnforex.com/guides/how-to-disable-trading-when-spread-is-too-wide/) · [Max spread (points) — AlgoTradingSpace](https://platform.algotradingspace.com/help/robots/glossary/entry-protections/max-spread-points/)

**Qué dice**: el spread es el factor más ignorado del trading automatizado; los practicantes evitan spreads anchos para intradía y los toleran solo en swing donde el spread es fracción chica del movimiento esperado.

**🟢 AIdan ya lo tiene** (`is_spread_acceptable`, `AIdan_TodoEnUno.py:1137`). **Pero no lo mide**: `spread_pips` es una columna de `slippage_log`, que tiene 0 filas (B.1). ⇒ No sabés cuántas señales bloquea, ni si el umbral está bien. **Se resuelve con el mismo fix de B.1.** Y con `CopySpread()` (o el histórico de ticks) se puede reconstruir la distribución de spread por hora y ver si el umbral actual es razonable o si está cortando la sesión asiática entera.

---

### B.8 🔴 TWAP / VWAP / iceberg / smart order routing

**Fuentes**: [AI Execution Trading: Beating Slippage in 2025 — PickMyTrade](https://blog.pickmytrade.trade/ai-execution-trading-slippage-reduction-2025/) · [How to Deal With Slippage — HedgeNordic](https://hedgenordic.com/2025/05/how-to-deal-with-slippage/) · [The Negative Drift of a Limit Order Fill (arXiv 2407.16527)](https://arxiv.org/pdf/2407.16527) · [Slippage and Market Impact Estimation — QuestDB](https://questdb.com/glossary/slippage-and-market-impact-estimation/)

**Veredicto: 🔴 no aplica, y vale decir por qué para cerrarlo.** TWAP/VWAP/iceberg existen para **minimizar impacto de mercado** al ejecutar tamaño grande. AIdan opera **0,01 lotes = 1.000 unidades** en el par más líquido del planeta. **Impacto de mercado = 0.** No hay nada que trocear.

**Lo único transferible** es el paper de arXiv sobre el *drift negativo del fill de una orden límite*: una orden límite que se llena incurre en una penalidad **cercana a ½ tick** por selección adversa — te llenan cuando el mercado va en tu contra. Eso **corrobora exactamente** la decisión de v3.53.4 de apagar la orden límite (36/36 rechazadas, "sesgo adverso estructural"). 🟢 Buena confirmación externa de una decisión que se tomó por otra vía.

---

## 4. Frente C — Lo que otros ya implementaron

### C.1 La serie MQL5 "MetaTrader 5 Machine Learning Blueprint" — **el recurso más alineado que encontré**

**Índice parcial verificado**: [Part 1: Data Leakage and Timestamp Fixes](https://www.mql5.com/en/articles/17520) · [Part 2: Labeling Financial Data](https://www.mql5.com/en/articles/18864) · [Part 6: Production-Grade Caching](https://www.mql5.com/en/articles/20302) · [Part 7: From Scattered Experiments to Reproducible Results](https://www.mql5.com/en/articles/20451) · [Part 10: Bet Sizing](https://www.mql5.com/en/articles/21824) · [Part 12: Probability Calibration](https://www.mql5.com/en/articles/21938) · [Part 14: Transaction Cost Modeling](https://www.mql5.com/en/articles/22372) · [Part 17: CPCV Backtesting — Tick-Level Evidence](https://www.mql5.com/en/articles/21954) · Parts 8/9 (Bayesian HPO con purged CV), 11 (Kelly), 18 (sequential bootstrap), 19 (bagging regimes).

**Por qué importa**: es AFML **implementado sobre MT5 + Python**, publicado 2025-2026, con código. Es la referencia externa que más se parece a AIdan en stack y en restricciones. Nadie más publica esto.

**Lo aprovechable, en orden**:
- **Part 14 (TCA)** → el modelo de costo para B.1.
- **Part 12 (calibración)** → gate y métricas (Brier + ECE + MCE + reliability diagram con CI bootstrap). AIdan hoy usa solo Brier; **ECE y MCE agregan información real** sobre *dónde* falla la calibración, no solo cuánto.
- **Part 17 (CPCV)** → **Combinatorial Purged CV**, un paso más allá del purged CV que el audit §3.3 propuso (P9, `cv_purged.py`, todavía sin hacer). CPCV genera múltiples caminos de backtest en vez de uno ⇒ da una **distribución** de Sharpe, no un número. Es el antídoto directo al modo de fallo que el proyecto sufrió 4 veces (split único → AUC 0,75 → 0,57).
- **Part 10 (bet sizing)** → la fórmula `signal = 2·Φ(z) − 1` con `z = (p − 1/K)/√(p(1−p))`, y sobre todo el **problema de concurrencia**: si 10 señales activas se dimensionan cada una al 10 %, la exposición total es 100 % **sin que nadie lo haya decidido**. AIdan tiene **max 4 posiciones** y sizing 1 % por trade ⇒ hasta 4 % simultáneo, decidido implícitamente. No es urgente, pero es un agujero conceptual real.

### C.2 Frameworks y repos: qué mirar y qué no

**Fuentes**: [awesome-systematic-trading (paperswithbacktest)](https://github.com/paperswithbacktest/awesome-systematic-trading) · [awesome-systematic-trading (wangzhe3224)](https://github.com/wangzhe3224/awesome-systematic-trading) · [best-of-algorithmic-trading](https://github.com/merovinh/best-of-algorithmic-trading) · [The Python Backtesting Landscape 2026](https://python.financial/) · [nautilus_trader](https://github.com/nautechsystems/nautilus_trader) · [pysystemtrade](https://qoppac.blogspot.com/)

| Proyecto | Qué es | Veredicto AIdan |
|---|---|---|
| **pysystemtrade** (Carver) | Motor sistemático de futuros, con la teoría de forecasts / vol targeting / diversification multipliers | 🟡 **No para migrar — para robar ideas** (§C.3). Es el repo con la teoría de portfolio más aplicable |
| **NautilusTrader** | Motor event-driven Rust, paridad backtest/live | 🔴 Ya descartado (audit §7). Confirmo: reescritura total |
| **VectorBT (PRO)** | Vectorizado, millones de trades/seg | 🟡 Solo como **herramienta de research paralela** (audit ya lo dijo). Único caso: barrido masivo de parámetros sobre velas |
| **backtesting.py** | Simple, `init()`/`next()`, reporte HTML en segundos | 🟡 El más razonable si alguna vez querés un segundo motor para **contrastar** tus tools propias. Bajo costo de entrada |
| **QLib** (Microsoft) | Plataforma AI-quant | 🔴 Orientada a equities cross-sectional. No aplica a un par |
| **LEAN / QuantConnect** | Ciclo completo | 🔴 No: no soporta tu bróker/stack sin reescribir |
| **freqtrade / jesse / hummingbot** | Cripto | 🔴 Ya descartados; además cripto ≠ FX en microestructura y costos |

**Nota crítica sobre "bots open source que ganan"**: busqué específicamente repos con resultados en vivo documentados. **No encontré ninguno creíble.** Los que publican equity curves no publican metodología; los que publican metodología (Carver) publican Sharpe ~0,5-1,0 con **45 instrumentos** — o sea, el rendimiento viene de **diversificación**, no de una señal buena. Esto es un dato en sí mismo y conecta con §E.3.

### C.3 🟡 Carver: forecasts continuos, diversification multiplier, vol targeting

**Fuentes**: [This Blog is Systematic (qoppac)](https://qoppac.blogspot.com/2024/) · [Estimated forecast scalars](https://qoppac.blogspot.com/2016/01/pysystemtrader-estimated-forecast.html) · [Correlations, Weights, Multipliers](https://qoppac.blogspot.com/2016/01/correlations-weights-multipliers.html) · [Diversification and small account size](https://qoppac.blogspot.com/2016/03/diversification-and-small-account-size.html) · [Systematic Trading 3 — 7 Circles](https://the7circles.uk/systematic-trading-3-frameworks-and-forecasts/)

**Las tres ideas transferibles**:
1. **Separación estricta**: regla de trading (dirección) / dimensionamiento / objetivo de volatilidad. AIdan **ya tiene esta separación** de facto (detector → `sl_pips` → riesgo 1 %). 🟢
2. **Forecast continuo en vez de binario**, combinado por **promedio ponderado** entre reglas, escalado por un **forecast diversification multiplier** (cap 2,5) y con el forecast final **capado a 20**. Traducido a AIdan: en vez de "m15 dice CALL con conf 78" y "structure dice CALL con conf 71" como dos trades independientes, un **forecast combinado**. 🟡 Interesante, pero **choca con el lote mínimo otra vez**: un forecast continuo sin poder modular el tamaño es un binario disfrazado.
3. **El post específicamente sobre cuentas chicas** ("Diversification and small account size") es el que más aplica: Carver aborda de frente el problema de que **con poco capital no podés diversificar ni modular**. Vale leerlo antes de tomar cualquier decisión de sizing.

---

## 5. Frente D — Arquitectura

### D.1 🔴 Event-driven core (Kafka / Redis Streams / NATS / Redpanda)

**Fuentes**: [nautilus_trader](https://github.com/nautechsystems/nautilus_trader) (usa Redis como message bus opcional) · [next-gen-algo-trading-bot](https://github.com/studiogangster/next-gen-algo-trading-bot) · [awesome-systematic-trading](https://github.com/wangzhe3224/awesome-systematic-trading)

**Veredicto: 🔴 no, y con argumento cuantitativo.** Un bus de eventos compra: (a) desacoplar productores/consumidores a distinto ritmo, (b) replay determinista, (c) escalar horizontalmente. AIdan tiene **1 productor de velas, ~5 threads, 1 símbolo, ~7 trades/día, y un loop de 10 s sobre velas de 5 min (30× de sobre-muestreo)**. Ninguna de las tres razones aplica.

**Lo que sí vale la pena de la idea, sin la infraestructura**: **(b), el replay determinista.** Hoy no se puede reproducir una decisión pasada. Pero eso se compra con **un log de decisión append-only** (`decision_log`: timestamp, velas usadas, features, gates evaluados, veredicto), no con Kafka. Es una tabla más y resuelve el 80 % del beneficio al 2 % del costo. 🟡

### D.2 🟡 SQLite → DuckDB **para research, no para operar**

**Fuentes**: [DuckDB vs SQLite — DataCamp](https://www.datacamp.com/blog/duckdb-vs-sqlite-complete-database-comparison) · [DuckDB vs SQLite — MotherDuck](https://motherduck.com/learn/duckdb-vs-sqlite-databases/) · [Embedded Databases in 2026 — Kestra](https://kestra.io/blogs/embedded-databases)

**Confirmo la recomendación del audit §5.3 y la afino.** SQLite a 14 MB / 609 trades no es un problema y no lo va a ser. Postgres/Timescale = complejidad sin beneficio.

**Lo nuevo**: DuckDB puede **leer la base SQLite directamente** (extensión `sqlite_scanner`) y consultar Parquet sin importar nada. Traducción práctica: tus tools de análisis (`measure_*`, scorers) podrían correr consultas analíticas — GROUP BY sobre `trade_archive` × `entry_context` × velas — **sin migrar nada y sin tocar la DB operativa**. Y cuando aparezcan datos de velas históricas masivos (Fase 2 usó 500k velas × 21 pares), Parquet + DuckDB es el formato correcto en vez de JSON.

**Esfuerzo**: bajo (`pip install duckdb`, no toca producción). **Valor**: medio. **Riesgo**: nulo.

### D.3 🟡 Reproducibilidad: config-hash + Parquet cache, **sin MLflow ni DVC**

**Fuente**: [MT5 Blueprint Part 7 — From Scattered Experiments to Reproducible Results](https://www.mql5.com/en/articles/20451)

**Lo interesante es que un practicante con el mismo stack evaluó las herramientas y las descartó**, igual que el audit. Su sistema usa **solo librerías estándar**: config JSON como única fuente de verdad → **hash de config** que identifica cada variante → árbol de directorios `estrategia/símbolo/rango/hash` → **cache Parquet** de features procesadas → grafo de dependencias que distingue cambios "pesados" (recarga datos) de "livianos" (reusa features) → **tracking de contaminación temporal** para que el cache no filtre futuro → generación automática de reportes al terminar.

**Aplicabilidad a AIdan**: 🟢 corrobora "no MLflow/DVC" (audit §7). 🟡 **Lo accionable**: tus tools de medición hoy imprimen a stdout y el resultado vive en el CLAUDE.md escrito a mano. Un `runs/<fecha>_<hash>/` con el JSON de config + el JSON de resultados haría que **las mediciones sean re-corribles y comparables** sin depender de que alguien las transcriba. Es la deuda que hace que "re-medir el ~1 sep" sea trabajo manual cada vez.

### D.4 🟡 Observabilidad minimalista

**Fuentes**: [10 Textual/Rich Dashboards](https://medium.com/@Nexumo_/10-textual-rich-dashboards-that-replace-spreadsheets-5bad588ca263) · [Streamlit para dashboards de monitoreo en tiempo real](https://medium.com/@hadiyolworld007/streamlit-for-realtime-api-monitoring-dashboards-2d986fca7450) · [OpenTelemetry vs Prometheus — SigNoz](https://signoz.io/blog/opentelemetry-vs-prometheus/)

**Veredicto: 🔴 no cambiar de stack.** Ya tenés dashboard FastAPI + Telegram + logs rotativos (v3.48.0). Grafana/ELK/OTel siguen sin justificarse en un proceso único.

**El único hueco real que queda** (y el audit lo señaló en P8, sin hacer): **contadores**. La tabla `errors` existe con **0 filas**. 189 `except` mudos. Lo que falta no es una UI nueva, es **un número que suba** cuando algo se cae en silencio. `errors` + un panel de "contadores por sitio" en el dashboard que ya existe. 🟡 Prioridad media-alta, esfuerzo bajo.

**Streamlit**: 🟡 lo único donde ganaría es en **post-mortem interactivo** (scatter de MFE/MAE, filtros por track/hora/régimen). Pero ya tenés `what_if_simulator.html`. **No duplicar.**

---

## 6. Frente E — Ángulos forzados

### E.1 🟡🔥 **Shadow book formalizado: Post-Rejection Follow-up Sampling y el save-to-miss ratio**

**Fuentes**:
- [Post-Rejection Follow-up Sampling: A Methodology for Counterfactual Outcome Measurement in Algorithmic DEX Trading (arXiv 2606.08228)](https://arxiv.org/pdf/2606.08228)
- [Outcome-Classified Precision Auditing of Filter Rules: Evidence from 2,400 Rejection Events (arXiv 2607.02830)](https://arxiv.org/pdf/2607.02830)
- [RED-2400: A Public Benchmark of Algorithmically-Rejected Trading Events with Outcome Labels (arXiv 2605.12151)](https://arxiv.org/pdf/2605.12151)

**Qué proponen.** Una metodología con nombre para exactamente lo que pediste. Un subsistema dedicado muestrea, a cadencia configurable y sobre un horizonte de seguimiento, **el precio de cada señal RECHAZADA** — no la ejecuta, la observa. Con eso se computan:
- **Save-to-miss ratio**: cuántos rechazos evitaron una pérdida real por cada rechazo que se perdió una ganancia. Reportan 3,7:1 (interpretación conservadora de dos niveles) y 14,8:1 (cinco niveles) sobre 13 días.
- **Precisión por filtro individual**: cada filtro activo evaluado por separado — *"every active filter individually net-positive on that criterion"*.
- Y el punto metodológico central, textual en sustancia: esto es **medición contrafactual, no una afirmación in-sample sobre la calidad del filtro**.

**Rareza**: **muy raro.** Es de 2026, es de DEX/Solana, y no lo hace prácticamente nadie en retail forex. Es el hallazgo más "no contemplado" del informe.

**Por qué AIdan lo necesita, específicamente.** El proyecto tiene una asimetría estructural: **mide con rigor lo que ejecuta y no mide nada de lo que bloquea.** Ejemplos concretos, todos tuyos:
- `M15_ATR_FLOOR=8` genera **2.115 skips de `ATR too low`** en 11 días. El costo (−74 % de frecuencia) está estimado; **el beneficio no está medido en absoluto** — solo inferido de un bucket histórico cuyo lado bueno "es frágil" (2 días aportan casi todo).
- El castigo por nivel flojo logueó **3 DROP en 11 días** — y la conclusión del 16-ago fue "no se toca la perilla, n=9". Con PRFS, esos 3 DROP tendrían outcome contrafactual.
- Los gates de `min_confidence` dentro de los detectores rechazan sin dejar rastro.
- `blocked_setups`, `active_meta_filters`: bloquean a ciegas.

**Y hay un precedente propio que prueba que funciona**: `shadow_strategies` (1.751 filas) hace justo esto para el meta-optimizer. **La infraestructura conceptual ya existe** — falta aplicarla a los skips de los detectores, que es donde hoy se decide en silencio.

**Cómo implementarlo sin tocar la decisión**: tabla `rejected_signals` (timestamp, track, razón del rechazo, dirección propuesta, precio, SL/TP que habría tenido). Un job que a las N velas rellene el outcome usando el mismo motor de excursión que ya tenés en `score_d1_shadow.py` (que **no re-simula SL/TP**, mide excursión favorable y adversa — la técnica correcta y ya escrita). Salida: **save-to-miss ratio por filtro**, mensual.

**Esfuerzo**: medio (1 tabla + 1 hook por punto de rechazo + reusar el scorer). **Riesgo**: cero, solo escribe.
**Impacto**: convierte cada filtro de AIdan de acto de fe en número. Y es la única forma honesta de defender —o de tirar— `M15_ATR_FLOOR=8` el 1 de septiembre.

---

### E.2 🟡🔥 **Cuenta CENT: el desbloqueo del cuello que aparece 3 veces en tus documentos**

**Fuentes**: [MT5 Cent accounts explainer — PrimeXBT Partners](https://intercom.help/partners-help-center/en/articles/16294374-mt5-cent-accounts-campaign-explainer-for-partners) · [The Complete Guide to Cent Account — WikiBit](https://blog.wikibit.com/cent-account) · [MetaTrader 5 Lot Size Explained — Headway](https://hw.online/faq/metatrader-5-lot-size-explained-a-comprehensive-guide/)

**El problema, en tus propias palabras.** El lote mínimo 0,01 sobre ~$639 bloquea, textualmente:
- **Kelly por track** — *"el lote mínimo 0,01 sobre un balance de ~$639 no deja espacio para modular"* (`research_mercado` §9).
- **Meta-labeling para sizing** — *"sizing continuo con lote mínimo 0,01 es una perilla de 2 o 3 posiciones, no un continuo"* (§2).
- **El track D1** — *"no se puede respetar el 1 % con SL de 82p en una cuenta de $639"* (una de las dos razones por las que nació en shadow).

Y en los tres casos la conclusión fue la misma: *"depende del CAPITAL, no del código"*. **Eso es falso, o al menos incompleto.**

**Qué es una cuenta cent.** El balance se denomina en centavos: **1 lote en cuenta cent = 0,01 lotes en cuenta estándar**. Un depósito de $10 se muestra como 1.000 USC. Con el mismo dinero real, **el lote mínimo efectivo se divide por 100**.

**Traducción directa a AIdan**: los $639 pasan a comportarse como **$63.900 a efectos de granularidad**. El sizing 1 % con SL de 82p **se puede respetar**. Kelly fraccionario por track **se vuelve computable**. Meta-labeling recupera **la mitad de su valor que hoy no es realizable**. Las salidas parciales (§B.5) dejan de ser imposibles. **Cuatro bloqueos, un cambio de cuenta.**

**Análisis crítico — lo que hay que verificar antes de entusiasmarse** (y es material, no cosmético):
1. **¿ICMarkets ofrece cuenta cent?** No me consta. Varios brókers sí (Exness, RoboForex, FBS, Headway…). **Cambiar de bróker cambia el spread, la comisión y la microestructura de fills** — o sea, invalida parte del track record. Eso es un costo real.
2. **La comisión no escala igual.** Las cuentas cent suelen tener spread más ancho y a veces no ofrecen Raw. Con la comisión siendo ~87 % del drag, **una cuenta cent con peores costos podría empeorar todo**. Hay que comparar costo por trade, no granularidad.
3. **Muchas cuentas cent son "cuentas para principiantes"** con ejecución peor (dealing desk, requotes). Eso cambiaría §B.2 — para mejor (habría `deviation` real) o para mucho peor.
4. **Es demo.** Nada impide **abrir una demo cent en paralelo** y correr AIdan ahí en modo espejo por unas semanas para validar que el sizing variable hace lo que se espera, sin tocar la cuenta actual.

**Recomendación**: no migrar. **Investigar y, si el costo por trade es comparable, abrir una demo cent como banco de pruebas de sizing.** Es el único camino que destraba tres líneas de mejora simultáneamente, y hoy no está escrito en ningún documento del proyecto.

---

### E.3 🟡 Diversificación de instrumentos: la palanca que **sube** la frecuencia

**Fuentes**: [Carver — Diversification and small account size](https://qoppac.blogspot.com/2016/03/diversification-and-small-account-size.html) · [A Few Notes on Systematic Trading — CXO Advisory](https://www.cxoadvisory.com/big-ideas/a-few-notes-on-systematic-trading/) · [Systematic Trading 3 — 7 Circles](https://the7circles.uk/systematic-trading-3-frameworks-and-forecasts/)

**El argumento.** Carver corre **~45 instrumentos**; AHL y Winton, cientos. Su tesis central es que el Sharpe realista de una regla individual **rara vez supera 1,0**, y que lo que produce un sistema viable no es una señal mejor sino **la suma de muchas señales mediocres poco correlacionadas**. La diversificación tiene tres ejes: instrumentos, reglas y velocidades.

**Por qué esto encaja con AIdan mejor que casi todo lo demás.** Tu restricción #1 es **no bajar frecuencia**, y todo el catálogo de mejoras del último mes son **filtros** (piso de ATR, castigo por nivel, gates) — cosas que la recortan. Agregar instrumentos es lo **único** que va en la dirección contraria: **más trades, del mismo detector, sobre datos independientes**.

Y hay un argumento estadístico específico para tu situación: **el cuello de botella declarado del proyecto es la muestra** (~7 trades/día, "n=25 tomaría ~9 meses"). Tres pares descorrelacionados **triplican la tasa de acumulación de evidencia**. Los experimentos que hoy tardan 9 meses tardarían 3.

**Y la evidencia ya existe, medida por vos**: Fase 1 y Fase 2 corrieron `detect_structure_signals` sobre **21-26 pares**. Ya sabés que el detector es portable. El resultado de Fase 2 (en curso) es **exactamente** el que dice si esto vale.

**Los contras, sin maquillar**:
1. **116 hardcodes de EUR/USD** (audit §1.6) + 29 constantes `* 10000` que rompen con JPY. No es trivial: es el ítem DT-14 con score 0,4 y esfuerzo 5.
2. **Correlación real**: EUR/USD, GBP/USD y AUD/USD comparten el factor USD. La diversificación efectiva es mucho menor que el conteo de pares. Elegir pares poco correlacionados es un problema en sí.
3. **Margen y max 4 posiciones**: con $639 y lote mínimo 0,01, más pares = más exposición simultánea. **Se vuelve viable con E.2**, no antes.
4. Si Fase 2 sale negativa, **replicar un detector sin edge en 3 pares es perder 3× más rápido**. La secuencia importa: Fase 2 primero.

**Veredicto**: 🟡 **no ahora, pero es la respuesta estratégica correcta a "no bajar frecuencia"** y merece estar en el roadmap explícitamente, condicionada al resultado de Fase 2 y a E.2.

---

### E.4 🔴 LLM leyendo el chart / razonando la señal antes de decidir

**Fuentes**:
- [Stop Using Vision LLMs to Read Trading Charts — 4 modelos, 2 vendors, 40 señales reales (gist, abr 2026)](https://gist.github.com/roman-rr/c1cd675f7c35b68ae5ac281c30080166)
- [Do VLMs Truly "Read" Candlesticks? A Multi-Scale Benchmark (arXiv 2604.12659)](https://arxiv.org/html/2604.12659v1)
- [StockBench: Can LLM Agents Trade Stocks Profitably in Real-World Markets? (arXiv 2510.02209)](https://arxiv.org/html/2510.02209v1)
- [Agent Trading Arena: numerical understanding in LLM agents (arXiv 2502.17967)](https://arxiv.org/html/2502.17967v2)
- [GPT-5 corrected GPT-4V's chart reading errors, not prompting (arXiv 2510.06782)](https://arxiv.org/html/2510.06782v1)

**Los números, que son demoledores**:

| Estudio | Resultado |
|---|---|
| Auditoría de producción (4 modelos, 2 vendors, 40 señales reales) | **51 % de acierto direccional**, **1 patrón identificado de 215**, **100 % de sesgo long en Gemini**. *"No frontier vision LLM cleared production gates"* |
| VLM candlestick benchmark | Los multimodales SOTA *"siguen fallando en la percepción geométrica fina requerida para identificar patrones de forma confiable"* |
| StockBench (4 meses, top-20 DJIA) | La mayoría de los agentes LLM **no le gana a equal-weight buy-and-hold (0,4 %)**. Mejores: Kimi-K2 1,9 %, Qwen3-235B 2,4 %. GPT-5: **0,3 %**. GPT-OSS-120B: **−0,9 %** |
| StockBench, escala | Los modelos **grandes** aguantan; **GPT-OSS-120B se degrada severamente** al crecer la complejidad |
| Trading questions con indicadores técnicos desde OHLCV crudo | Los LLM con RAG rinden **sistemáticamente peor** en esas preguntas |

**Veredicto para AIdan: 🔴 NO, y la conclusión es más fuerte que "no vale la pena".**

Razonamiento en tres pasos:
1. **El techo está medido y es ~50 % direccional** incluso para modelos frontier con visión.
2. **AIdan tiene un Qwen 7B local.** El modelo *más chico* de StockBench que aún funcionaba era de 120B — y **daba retorno negativo**. Un 7B está dos órdenes de magnitud por debajo del punto donde la evidencia empieza a ser ambigua.
3. **Ya tenés la medición interna que lo confirma**, y es la más relevante de todas: el A/B de v3.53.7 mostró que el 7B pone `entry_quality='good'` en el **93 % de los perdedores**, y `timing_assessment` constante en el 100 % (`measure_post_trade_value.py`, 11-ago). **Ese modelo no discrimina ni mirando el resultado.** Pedirle que prediga es estrictamente más difícil que pedirle que juzgue lo ya ocurrido — y en lo segundo ya falló.

**Lo que sí sobrevive, y v3.57.2 ya lo hizo bien**: el LLM como **generador de texto sobre una comparación numérica que hizo el código**, con lista cerrada de valores y verificación de adherencia. Esa es la única arquitectura defendible con un 7B: **el código decide, el modelo redacta y clasifica contra una lista cerrada**. Está bien resuelto; no lo expandas hacia predicción.

**Un matiz honesto**: StockBench reporta que GPT-4o con input visual **mejoró de 33,65 % a 47,70 % de retorno** en un estudio distinto. No lo tomo como contra-evidencia: es equity, horizonte de 10 días, modelo frontier, y un solo estudio contra tres negativos con metodología más adversarial.

---

### E.5 🟡 "Psicología de trading" aplicada a bots — sobrevive **una** cosa, y ya la tenés

**Fuentes**: [Reducing Drawdown: 7 Risk-Management Techniques — Tradetron](https://tradetron.tech/blog/reducing-drawdown-7-risk-management-techniques-for-algo-traders) · [Avoid Overtrading — LuxAlgo](https://www.luxalgo.com/blog/avoid-overtrading-stay-disciplined/) · [Risk Management in Algo Trading 2026 — AlgoBulls](https://algobulls.com/blog/algo-trading/risk-management) · [Hour-Aware Adaptive Risk Management for Autonomous Trading (arXiv 2606.08232)](https://arxiv.org/pdf/2606.08232)

**Análisis crítico primero.** Buena parte de la "psicología aplicada a bots" es **transferencia inválida**: un bot no siente FOMO ni hace revenge trading. Lo que sí existe es el **isomorfismo mecánico**: el humano re-entra tras perder por emoción; el bot re-entra tras perder porque su regla no tiene memoria del resultado anterior. **El efecto observable es el mismo aunque la causa sea distinta.**

**Y AIdan ya midió su propio caso**: cooldown 5 min post-pérdida, n=74, WR 24 % vs 38 %, p=0,010, sostenido 4/5 quincenas, con frontera nítida a ~5 min. **Eso es "revenge trading" mecánico, medido y ya arreglado.** 🟢 La literatura corrobora, no aporta.

**Lo que queda como hueco real**: los **drawdown limits multinivel**. La práctica documentada es límites en **varios niveles** (diario / semanal / mensual / máximo) con respuestas graduadas: reducir tamaño → pausar → apagar hasta revisión manual. AIdan tiene **daily loss limit (−$30)** y **kill switch**, y **nada en el medio** — hueco que el audit §2.2 ya señaló y que `research_mercado` §8 cuantificó (ventanas de 30-50 trades, DD acercándose a 1,5-2× el máximo previo).

**Veredicto**: 🟡 **stop por ventana de equity**, esfuerzo bajo. **Pero reduce frecuencia** (solo en drawdown), o sea que choca con la restricción #1 y **es decisión del user**, no mía. Lo dejo propuesto, no recomendado.

**El paper de arXiv sobre "hour-aware adaptive risk management"** (multiplicadores de riesgo por hora) es 🔴: AIdan **ya removió el hour gate por ruido** y el 14-jun rechazó "hora 11h AR" por CI que cruza. Mismo error, otro nombre.

---

### E.6 🟡 Kelly fraccionario — estado real

Cubierto en audit §2.2 y `research_mercado` §9. **No repito, solo actualizo con lo nuevo**: [MT5 Blueprint Part 10](https://www.mql5.com/en/articles/21824) aporta la forma concreta `signal = 2·Φ(z) − 1` y, más útil, el **problema de concurrencia**: sin promediar señales activas, N posiciones simultáneas producen exposición N× **sin decisión explícita**. AIdan permite 4 ⇒ 4 % de riesgo simultáneo no decidido. **Ojo con esto en cuenta real.** Y sigue bloqueado por E.2.

---

## 7. Se nos escapa — rankeado por (impacto × confianza) ÷ esfuerzo

| # | Qué se nos escapa | Impacto | Confianza en el hallazgo | Esfuerzo | ¿Baja frecuencia? |
|---|---|---|---|---|---|
| **1** | **`log_fill()` está escrito y no se llama; `slippage_log` = 0 filas.** El TCA que es "bloqueante para cuenta real" está hecho al 70 % y desconectado | **Muy alto** | **Verificado ejecutando** | **~1 h** | No |
| **2** | **MFE/MAE nunca se guardan.** Sin ellos, "¿entra mal o gestiona mal?" — la pregunta central desde el 19-jun — se responde con proxies frágiles | **Muy alto** | Alta (concepto mainstream + hueco verificado) | Bajo-medio | No |
| **3** | **El `deviation: 50` probablemente no hace nada en ECN/Market Execution.** El control de slippage que el código documenta puede no existir | Alto | Alta (doc oficial MQL5) — **falta 1 verificación de 10 min** | **10 min** | No |
| **4** | **Shadow book formalizado (PRFS + save-to-miss ratio).** 2.115 skips de ATR sin un solo outcome medido. Todo filtro de AIdan es hoy un acto de fe | **Muy alto** | Alta (metodología publicada 2026 + infraestructura propia ya existe en `shadow_strategies`) | Medio | No |
| **5** | **Cuenta CENT = 100× de granularidad de lote.** Destraba Kelly + meta-labeling + track D1 + salidas parciales, los cuatro cuellos que se cerraron como "depende del capital" | **Muy alto si funciona** | **Media** — depende de que exista con costos comparables (verificable) | Bajo investigarlo, alto migrar | No (sube) |
| **6** | **`signal_age_at_fill_min`.** El retry ejecuta señales viejas a mercado (#625, 27 min). "Signal half-life" da el marco; los dos timestamps ya existen | Alto | Media-alta (marco sólido + caso propio documentado) | **Muy bajo** | Marginal |
| **7** | **Beta calibration ≠ Platt.** Platt falló su gate el 5-ago; repetirlo es repetir el experimento. Beta domina a Platt cuando los scores son asimétricos — que es el caso de `confidence` | Medio-alto | Media-alta (literatura clara; hipótesis específica) | Bajo | No |
| **8** | **Features microestructurales desde OHLCV** (Roll, Corwin-Schultz, Kyle λ, Amihud, VPIN aprox.). Features, no filtros | Medio | Media (implementación publicada; valor predictivo no reportado) | Bajo-medio | No |
| **9** | **Kaufman Efficiency Ratio** como acompañante del piso de ATR: separa "poco movimiento" de "movimiento sin dirección" — los dos casos que el piso fijo confunde | Medio | Media (mainstream, sin estudio FX citable) | **Trivial** | No |
| **10** | **Diversificación de instrumentos.** La única palanca que **sube** frecuencia y triplica la tasa de acumulación de evidencia. Bloqueada por 116 hardcodes, por E.2 y por el resultado de Fase 2 | **Alto a largo plazo** | Media (teoría sólida; correlación USD la limita) | **Alto** | No (sube) |

**Y dos puertas que este informe CIERRA** (valor negativo, que también cuenta):
- **Barras alternativas (tick/imbalance/runs)**: medido sobre EURUSD real — mejora la kurtosis 56 % y **no da edge** (AUC 0,42-0,55, p=0,10). No lo intentes.
- **LLM leyendo charts / razonando la señal**: 51 % direccional en auditoría independiente; el modelo más chico que "funciona" en StockBench es 120B y da −0,9 %. Con un 7B que ya falla al juzgar trades cerrados (93 % de perdedores etiquetados `good`), es imposible.
- Bonus: **confluencia multi-timeframe "cuantificada"** — la fuente popular no tiene estudio citable y **contradice tu propia medición del 19-jun**. Rechazada.

---

## 8. Roadmap sugerido — las 5 mejores oportunidades

> **Restricciones respetadas**: no bajar frecuencia · un cambio a la vez · nada que contamine las lecturas ya agendadas (22 ago BE de h1 · 28 ago news · 1 sep ATR floor + castigo por nivel · 15 sep D1). **Los cinco items de abajo son de INSTRUMENTACIÓN o VERIFICACIÓN — ninguno cambia una decisión de trading**, así que **ninguno contamina esas lecturas**. Eso es deliberado.

### 🥇 1 — Enchufar `log_fill()` + verificar el modo de ejecución (TCA real) ✅ HECHO 19-ago (v3.58.0; confirmado `trade_exemode=MARKET` → deviation ignorado)
**Qué**: llamar a `log_fill(strategy_id, request['price'], result.price, direction, spread_pips)` en `open_position()` y en el path del retry. En paralelo, imprimir `symbol_info().trade_exemode` y `filling_mode` una vez y dejarlo escrito.
**Por qué primero**: (a) es el mecanismo que PROGRESS.md pone como #2 y "bloqueante antes de cuenta real"; (b) **ya está escrito** — el costo es un import; (c) sin él no se puede distinguir "la estrategia empeoró" de "la ejecución empeoró", que es la ambigüedad que hace irresolubles la mitad de los debates del proyecto; (d) si `trade_exemode == MARKET`, hay que corregir un comentario del código que hoy afirma una tolerancia de 5 pips que no existe.
**Criterio de lectura (declarar antes)**: a las 4 semanas, distribución de `slippage_pips` por hora y por track. Comparar el costo realizado contra el esperado. **Si la mediana de slippage supera ~0,7 pips** (referencia de la fuente MT5 para un mayor en liquidez normal), la ejecución es un problema material y no un ruido.
**Esfuerzo**: 1-2 h. **Riesgo**: nulo.

### 🥈 2 — MFE / MAE en `trade_archive` ✅ HECHO 19-ago (v3.58.1 + bugfix de unidades en el fallback de `get_trade_excursion`)
**Qué**: el position manager (que ya corre cada 15 s y ya lee precio) mantiene `max_favorable_pips` / `max_adverse_pips` por posición; se persisten al cerrar.
**Por qué**: es la instrumentación que convierte tres preguntas abiertas en queries — el criterio (c) del checkpoint del 22-ago (¿el BE corta ganadores?) pasa de un JOIN frágil sobre `position_manager_log` a una columna; el diagnóstico "entra en el agotamiento" pasa de inferencia a medición; y el `tp_cap` se puede evaluar contra la excursión real en vez de contra el nominal. Además **elimina la limitación declarada** de `backfill_directional_lessons.py` (usa `max(0, pips)` como cota inferior de MFE y admite que puede generar falsos positivos).
**Criterio**: no hay gate — es instrumentación. La primera lectura útil es a n≈40 trades cerrados con las columnas pobladas.
**Esfuerzo**: medio (medio día). **Riesgo**: bajo — solo lectura de precio + escritura al cerrar. **No toca la decisión de cierre.**

### 🥉 3 — `rejected_signals` + save-to-miss ratio (el shadow book) ✅ HECHO 19-ago (v3.58.1; scorer `tools/score_rejected_signals.py`)
**Qué**: tabla que registra cada rechazo (track, razón, dirección, precio, SL/TP hipotético) + job que rellena la excursión a N velas con el motor que ya existe en `score_d1_shadow.py`. Empezar por **un solo punto de rechazo: `ATR too low` de m15**, que es el que más volumen tiene y el que tiene lectura agendada el 1-sep.
**Por qué**: hoy **el 100 % de los filtros de AIdan se justifican con evidencia histórica in-sample y ninguno con outcome contrafactual**. Es la asimetría estructural del proyecto: rigor absoluto en lo que ejecuta, cero visibilidad en lo que bloquea. Y hay un caso urgente: `M15_ATR_FLOOR=8` cuesta el 74 % de la frecuencia de m15 y su beneficio se apoya en un bucket cuyo lado bueno la revisión adversarial calificó de **frágil** (2 días aportan casi todo).
**Criterio (declarar antes)**: a las 4-6 semanas, **save-to-miss ratio del filtro de ATR**. Si es < 1,0 (bloquea más ganadores que perdedores), el piso está mal puesto **con independencia de lo que diga el bucket histórico**. Si es > 2,0, está bien y se puede dejar de discutir.
**Esfuerzo**: medio (1-2 días). **Riesgo**: nulo. **Ojo**: no superponer la conclusión a la lectura del 1-sep; esto **aporta** a esa lectura, no la reemplaza.

### 4 — `signal_age_at_fill_min` + Kaufman Efficiency Ratio en `entry_context` ✅ HECHO 19-ago (v3.58.1)
**Qué**: dos campos nuevos, clasificados en el momento, sin efecto sobre nada. `signal_age = order_send_ts − created_at`; `efficiency_ratio` = |Δneto N| / Σ|Δbarra| sobre las últimas 20 velas del TF del track.
**Por qué juntos**: ambos son ~10 líneas, ambos son features puras, y ambos atacan huecos ya identificados. El primero le pone número al fenómeno del retry (#625) con el marco de *signal half-life*. El segundo separa "mercado muerto" de "mercado que va y viene" — los dos casos que `M15_ATR_FLOOR` mete en la misma bolsa, y que explican por qué agosto costó 59 % de frecuencia.
**Criterio**: ninguno todavía — se acumulan y se leen dentro de 6-8 semanas contra `mt5_pnl`, con el gate de siempre.
**Esfuerzo**: 2-3 h. **Riesgo**: nulo (`entry_context` es un JSON, agregar claves no rompe consumidores).
**Nota de secuencia**: `entry_context` es el vehículo correcto y ya probado (`news_latency_min` entró así en v3.57.0). Meter todo lo de instrumentación por ese canal mantiene la propiedad de "clasificado al entrar, no reconstruido".

### 5 — Investigar (no migrar) la cuenta CENT ✅ HECHO 19-ago — **DESCARTADA** (gate de costo: +25 a +90% por trade; cent+raw no existe; ver `docs/research_cuenta_cent_2026-08-19.md`)
**Qué**: una tarde de research: ¿ICMarkets ofrece cent? Si no, ¿qué brókers la ofrecen con **spread + comisión comparables a Raw**? Comparar **costo total por trade**, no granularidad. Si hay candidato viable, **abrir una demo cent en paralelo** y espejar AIdan ahí con sizing variable, sin tocar la cuenta actual.
**Por qué**: es el único item que **destraba cuatro líneas a la vez** (Kelly por track, meta-labeling para sizing, track D1 fuera de shadow, salidas parciales) — cuatro cosas que los documentos del proyecto cerraron con "depende del capital, no del código". Depende del **tipo de cuenta**, que sí es una decisión disponible hoy.
**Criterio de descarte pre-declarado**: si el costo por trade de la mejor cuenta cent disponible es **>20 % peor** que el actual, se descarta y se anota como cerrado — con la comisión siendo ~87 % del drag, la granularidad no compra nada si el costo sube.
**Esfuerzo**: 3-4 h de investigación. **Riesgo**: cero (es research). **Decisión de migrar: tuya, no mía.**

---

### Lo que deliberadamente NO está en el roadmap, y por qué

| Idea | Por qué no |
|---|---|
| Beta calibration | Buena, pero **el turno es en 3-4 semanas** (PROGRESS.md §5) y hacerlo ahora es calibrar sin `setup_type` limpio acumulado. Va **junto** a Platt cuando toque, no antes |
| Chandelier / trailing por ATR | Contamina la lectura del BE de h1 del 22-ago. Y sin MFE/MAE (item 2) no hay forma de saber si el problema existe |
| Features microestructurales | Correctas pero de segundo orden. Primero medir la ejecución (1) y la excursión (2); si esos dos explican la pérdida, las features no hacen falta |
| Percentil de ATR | Ya es el #1 de `research_mercado`. **Lo mantengo ahí, no lo dupliqué acá.** Pero: se lee **después** del 1-sep, y el item 3 de este roadmap le da la evidencia contrafactual que hoy le falta |
| Stop por ventana de equity | **Reduce frecuencia.** Choca con la restricción #1 ⇒ es tu decisión, no una recomendación mía |
| Cualquier cosa con LLM prediciendo | Cerrado en §E.4 con 5 fuentes y una medición propia |
| Diversificación de pares | Correcta a largo plazo, bloqueada por Fase 2 + E.2 + 116 hardcodes. **Al roadmap del trimestre, no al del ciclo** |

---

## Fuentes

**Microestructura y features (frente A)**
- [Feature Engineering for ML (Part 5): Microstructural Features in Python — MQL5](https://www.mql5.com/en/articles/22733)
- [Feature Engineering for ML (Part 6): Microstructural Features in MQL5](https://www.mql5.com/en/articles/22734)
- [Feature Engineering for ML (Part 9): Structural Break Tests in Python — MQL5](https://www.mql5.com/en/articles/23158)
- [Feature Engineering for ML (Part 1): Fractional Differentiation — MQL5](https://www.mql5.com/en/articles/22014)
- [Feature Engineering for ML (Part 2): Fixed-Width Fractional Differentiation in MQL5](https://www.mql5.com/en/articles/22015)
- [Market Microstructure in MQL5 (Part 5): Microstructure Noise](https://www.mql5.com/en/articles/22938)
- [Market Microstructure in MQL5 (Part 6): Order Flow](https://www.mql5.com/en/articles/22939)
- [MT5-OrderFlow-Footprint-Engine — GitHub](https://github.com/Vandoriz/MT5-OrderFlow-Footprint-Engine)
- [Beyond the Clock (Part 4): Efficacy of Bars on Trending and Mean-Reversion Strategies — MQL5](https://www.mql5.com/en/articles/23310)
- [Information Driven Bars — QuantStrategy.io](https://quantstrategy.io/blog/information-driven-bars-moving-beyond-time-based-financial/)
- [Advanced candlesticks: tick, dollar, volume, imbalance bars — Sefidian](https://www.sefidian.com/2021/06/12/introduction-to-advanced-candlesticks-in-finance-tick-bars-dollar-bars-volume-bars-and-imbalance-bars/)

**Régimen y change-point**
- [Change-Point Detection in Financial Time Series Using PELT — ACM 2025](https://dl.acm.org/doi/10.1145/3773365.3773532)
- [Bayesian Online Changepoint Detection in Python — Sesen](https://sesen.ai/blog/bayesian-online-changepoint-detection)
- [Changepoint Detection: Finding Regime Shifts in Financial Data — Sesen](https://sesen.ai/blog/changepoint-detection-regime-shifts)
- [Bayesian Autoregressive Online Change-Point Detection (arXiv 2407.16376)](https://arxiv.org/pdf/2407.16376)
- [Online learning of order flow and market impact with Bayesian change-point detection — SNS](https://ricerca.sns.it/retrieve/7bc5e659-ed02-4124-9739-c07e31aa06db/Online%20learning%20of%20order%20flow%20and%20market%20impact%20with%20Bayesian%20change-point%20detection%20methods.pdf)
- [Kaufman Efficiency Ratio — LuxAlgo](https://www.luxalgo.com/library/concept/kaufman-efficiency-ratio/)
- [Efficiency Ratio Strategy — QuantifiedStrategies](https://www.quantifiedstrategies.com/efficiency-ratio/)
- [Kaufman's Efficiency Ratio (KER) — StrategyQuant](https://strategyquant.com/codebase/kaufmans-efficiency-ratio-ker/)
- [Hurst Exponent Applications: From Regime Analysis to Arbitrage — Harbourfront](https://blog.harbourfronts.com/2024/12/01/hurst-exponent-applications-from-regime-analysis-to-arbitrage/)
- [Patterns in the Chaos: The Moving Hurst Indicator — MDPI JRFM 2024](https://www.mdpi.com/1911-8074/17/9/390)
- [Intraday FX Volatility-Curve Forecasting with Functional GARCH (arXiv 2311.18477)](https://arxiv.org/html/2311.18477v3)
- [Forecasting Realized Volatility with Time Series Foundation Models (arXiv 2607.05291)](https://arxiv.org/pdf/2607.05291)

**Calibración e incertidumbre**
- [Beta vs Platt vs Isotonic Calibration — MetricGate](https://metricgate.com/blogs/beta-calibration-vs-platt-vs-isotonic/)
- [An introduction to calibration (part II): Platt, isotonic, beta — Abzu](https://www.abzu.ai/data-science/calibration-introduction-part-2/)
- [Classifier Calibration: a survey (arXiv 2112.10327)](https://arxiv.org/pdf/2112.10327)
- [Classifier Calibration at Scale: model-agnostic post-hoc methods (arXiv 2601.19944)](https://arxiv.org/pdf/2601.19944)
- [Using Platt's scaling for calibration after undersampling — limitations (arXiv 2410.18144)](https://arxiv.org/pdf/2410.18144)
- [MT5 ML Blueprint (Part 12): Probability Calibration](https://www.mql5.com/en/articles/21938)
- [Exploring Conformal Forecasting of Financial Time Series — MQL5](https://www.mql5.com/en/articles/18324)
- [Conformal Prediction for Reliable Stock Selections — PMLR 2025](https://proceedings.mlr.press/v266/kaya25a.html)
- [Drift-Aware Spectral Conformal Prediction for Non-Exchangeable Streaming Data (arXiv 2606.15953)](https://arxiv.org/pdf/2606.15953)
- [Harnessing Conformal Forecasting in Financial Markets with MAPIE — Tildee](https://www.tildee.com/harnessing-conformal-forecasting-in-financial-markets-quantifying-uncertainty-and-managing-risk-with-mapie/)

**Ejecución, costos y salidas (frente B)**
- [MT5 ML Blueprint (Part 14): Transaction Cost Modeling for Triple-Barrier Labels](https://www.mql5.com/en/articles/22372)
- [TransactionCostCollector — Broker Cost Profiling Script (MQL5 Code Base)](https://www.mql5.com/en/code/73173)
- [Order execution modes by price and volume — MQL5 Book](https://www.mql5.com/en/book/automation/experts/experts_execution_filling)
- [Symbol trading conditions and order execution modes — MQL5 Book](https://www.mql5.com/en/book/automation/symbols/symbols_execution_filling)
- [How to Set Slippage in MT5 — foro MQL5](https://www.mql5.com/en/forum/446038)
- [The Negative Drift of a Limit Order Fill (arXiv 2407.16527)](https://arxiv.org/pdf/2407.16527)
- [Slippage and Market Impact Estimation — QuestDB](https://questdb.com/glossary/slippage-and-market-impact-estimation/)
- [AI Execution Trading: Beating Slippage in 2025 — PickMyTrade](https://blog.pickmytrade.trade/ai-execution-trading-slippage-reduction-2025/)
- [How to Deal With Slippage — HedgeNordic](https://hedgenordic.com/2025/05/how-to-deal-with-slippage/)
- [MAE y MFE explicados — QuantifiedStrategies](https://www.quantifiedstrategies.com/maximum-adverse-excursion-and-maximum-favorable-excursion/)
- [MFE & MAE: The Complete Guide — TradesViz](https://www.tradesviz.com/blog/mfe-mae-charts/)
- [MAE and MFE: How to Read Trade Excursion Data — Trader's Second Brain](https://traderssecondbrain.com/guides/mae-mfe-analysis)
- [ATR Trailing Stop Guide: Chandelier Exit — StratBase](https://stratbase.ai/en/blog/average-true-range-trailing-stop)
- [Chandelier Exit Strategy — QuantifiedStrategies](https://www.quantifiedstrategies.com/chandelier-exit-strategy/)
- [Volatility-Adjusted Stop Losses: ATR, Chandelier, Keltner — Volatility Box](https://volatilitybox.com/research/volatility-adjusted-stop-losses/)
- [Chandelier Exit — StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit)
- [Scaling Out vs All-In All-Out: backtesting comparison — QuantStrategy.io](https://quantstrategy.io/blog/scaling-out-vs-all-in-all-out-a-data-driven-backtesting/)
- [Should you EVER take Partial Profits? — Dave Mabe](https://davemabe.com/should-you-ever-take-partials)
- [Assessing Stop-Loss and Re-Entry Strategies — Klement](https://www.semanticscholar.org/paper/Assessing-Stop-Loss-and-Re-Entry-Strategies-Klement/92428c679f6d1cc97d2e66d34087cadf90b69e5a)
- [Optimal Stop-Loss and Take-Profit Parameterization for Autonomous Trading Agent Swarm (arXiv 2604.27150)](https://arxiv.org/pdf/2604.27150)
- [How Smart Trade Filters Improve EA Performance — MQL5 Blogs](https://www.mql5.com/en/blogs/post/770891)
- [How to Disable Trading When Spread Is Too Wide — EarnForex](https://www.earnforex.com/guides/how-to-disable-trading-when-spread-is-too-wide/)
- [Signal Half-Life: The Missing Piece in Most Trading Systems — OpenAlgo](https://blog.openalgo.in/signal-half-life-the-missing-piece-in-most-trading-systems-24824b102799)
- [Signal Decay Analysis: Understanding Alpha Lifecycles — MicroAlphas](https://microalphas.com/signal-decay-patterns/)
- [Alpha Decay — Mark Best](https://markrbest.github.io/alpha-decay/)
- [Signal Decay and Alpha Erosion — Foxholm](https://foxholm.com/q/concepts/signal-decay/)

**Shadow book / contrafactual (frente E)**
- [Post-Rejection Follow-up Sampling: Counterfactual Outcome Measurement in Algorithmic DEX Trading (arXiv 2606.08228)](https://arxiv.org/pdf/2606.08228)
- [Outcome-Classified Precision Auditing of Filter Rules: 2,400 Rejection Events (arXiv 2607.02830)](https://arxiv.org/pdf/2607.02830)
- [RED-2400: Public Benchmark of Algorithmically-Rejected Trading Events (arXiv 2605.12151)](https://arxiv.org/pdf/2605.12151)

**LLM y trading (frente E)**
- [Stop Using Vision LLMs to Read Trading Charts — auditoría de 4 modelos / 40 señales](https://gist.github.com/roman-rr/c1cd675f7c35b68ae5ac281c30080166)
- [Do VLMs Truly "Read" Candlesticks? Multi-Scale Benchmark (arXiv 2604.12659)](https://arxiv.org/html/2604.12659v1)
- [StockBench: Can LLM Agents Trade Stocks Profitably? (arXiv 2510.02209)](https://arxiv.org/html/2510.02209v1)
- [Agent Trading Arena: Numerical Understanding in LLM-Based Agents (arXiv 2502.17967)](https://arxiv.org/html/2502.17967v2)
- [GPT-5 Corrected GPT-4V's Chart Reading Errors, Not Prompting (arXiv 2510.06782)](https://arxiv.org/html/2510.06782v1)
- [TrustTrade: Human-Inspired Selective Consensus in LLM Trading Agents (arXiv 2603.22567)](https://arxiv.org/pdf/2603.22567)

**Arquitectura, sizing y portfolio (frentes C y D)**
- [MT5 ML Blueprint (Part 1): Data Leakage and Timestamp Fixes](https://www.mql5.com/en/articles/17520)
- [MT5 ML Blueprint (Part 6): Production-Grade Caching System](https://www.mql5.com/en/articles/20302)
- [MT5 ML Blueprint (Part 7): From Scattered Experiments to Reproducible Results](https://www.mql5.com/en/articles/20451)
- [MT5 ML Blueprint (Part 10): Bet Sizing for Financial Machine Learning](https://www.mql5.com/en/articles/21824)
- [MT5 ML Blueprint (Part 17): CPCV Backtesting — Tick-Level Evidence](https://www.mql5.com/en/articles/21954)
- [awesome-systematic-trading — paperswithbacktest](https://github.com/paperswithbacktest/awesome-systematic-trading)
- [awesome-systematic-trading — wangzhe3224](https://github.com/wangzhe3224/awesome-systematic-trading)
- [best-of-algorithmic-trading](https://github.com/merovinh/best-of-algorithmic-trading)
- [nautilus_trader — GitHub](https://github.com/nautechsystems/nautilus_trader)
- [The Python Backtesting Landscape (2026)](https://python.financial/)
- [This Blog is Systematic — Rob Carver](https://qoppac.blogspot.com/2024/)
- [Diversification and small account size — Carver](https://qoppac.blogspot.com/2016/03/diversification-and-small-account-size.html)
- [pysystemtrade: Estimated forecast scalars — Carver](https://qoppac.blogspot.com/2016/01/pysystemtrader-estimated-forecast.html)
- [Correlations, Weights, Multipliers (pysystemtrade) — Carver](https://qoppac.blogspot.com/2016/01/correlations-weights-multipliers.html)
- [Systematic Trading 3 — Frameworks and Forecasts — 7 Circles](https://the7circles.uk/systematic-trading-3-frameworks-and-forecasts/)
- [A Few Notes on Systematic Trading — CXO Advisory](https://www.cxoadvisory.com/big-ideas/a-few-notes-on-systematic-trading/)
- [So You Want to Start a Trading Business — Robot Wealth](https://robotwealth.com/so-you-want-to-start-a-trading-business/)
- [Run Your Trading Like a Business — Robot Wealth](https://robotwealth.com/run-trading-like-a-business-not-a-board-game/)
- [DuckDB vs SQLite: Complete Comparison — DataCamp](https://www.datacamp.com/blog/duckdb-vs-sqlite-complete-database-comparison)
- [DuckDB vs SQLite — MotherDuck](https://motherduck.com/learn/duckdb-vs-sqlite-databases/)
- [Embedded Databases in 2026: DuckDB, SQLite, Polars, chDB — Kestra](https://kestra.io/blogs/embedded-databases)
- [OpenTelemetry vs Prometheus — SigNoz](https://signoz.io/blog/opentelemetry-vs-prometheus/)
- [10 Textual/Rich Dashboards That Replace Spreadsheets](https://medium.com/@Nexumo_/10-textual-rich-dashboards-that-replace-spreadsheets-5bad588ca263)
- [MT5 Cent accounts — explainer](https://intercom.help/partners-help-center/en/articles/16294374-mt5-cent-accounts-campaign-explainer-for-partners)
- [The Complete Guide to Cent Account — WikiBit](https://blog.wikibit.com/cent-account)
- [MetaTrader 5 Lot Size Explained — Headway](https://hw.online/faq/metatrader-5-lot-size-explained-a-comprehensive-guide/)
- [Reducing Drawdown: 7 Risk-Management Techniques — Tradetron](https://tradetron.tech/blog/reducing-drawdown-7-risk-management-techniques-for-algo-traders)
- [Avoid Overtrading: Stay Disciplined — LuxAlgo](https://www.luxalgo.com/blog/avoid-overtrading-stay-disciplined/)
- [Risk Management in Algo Trading — AlgoBulls 2026](https://algobulls.com/blog/algo-trading/risk-management)
- [Hour-Aware Adaptive Risk Management for Autonomous Trading (arXiv 2606.08232)](https://arxiv.org/pdf/2606.08232)
- [tsfresh — GitHub](https://github.com/blue-yonder/tsfresh)
- [tsfresh: Time Series FeatuRe Extraction on basis of Scalable Hypothesis tests — Neurocomputing](https://www.sciencedirect.com/science/article/pii/S0925231218304843)
- [Bake off redux: review of recent time series classification algorithms (arXiv 2304.13029)](https://arxiv.org/pdf/2304.13029)
- [MTF Alignment & Confluence Scoring — LuxAlgo](https://www.luxalgo.com/library/concept/mtf-alignment-and-confluence-scoring/)

---

*Documento generado el 19 Ago 2026. Los tres hallazgos marcados ⚫ (`log_fill` desconectado, `slippage_log` vacío, `deviation` en cuenta ECN) se verificaron ejecutando `grep` sobre el repo y consultas de solo lectura sobre `financial_news.db`. **No se modificó código, no se tocó la DB, no se hicieron commits.***
