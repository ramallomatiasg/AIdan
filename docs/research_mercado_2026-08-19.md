# Research de mercado y método — 19 Ago 2026

Pedido del user: *"research exhaustivo de internet para aprender sobre mercado, formas de
planificación, operaciones típicas, cosas útiles para experimentar y mejorar AIdan"*.

**Cómo leer este documento.** Cada bloque dice de dónde sale el número y, cuando aplica, si el
proyecto ya lo midió por su cuenta. Marco tres estados:

- 🟢 **Corrobora** algo que AIdan ya midió → sube la confianza en la decisión que ya está tomada.
- 🟡 **Idea testeable** → candidata concreta, con el criterio de lectura declarado.
- 🔴 **Contradice** o descarta algo → cierra una puerta y ahorra trabajo.

Y una advertencia de peso: **buena parte del contenido de trading en internet es marketing de
brokers**. Filtré hacia papers, estudios con n y t-stat declarados, y fuentes que publican
resultados negativos. Lo que no tenía números verificables lo dejé afuera o lo marco como tal.

---

## 1. El hallazgo más importante: el edge bruto suele estar DEBAJO del costo

**Fuente:** *Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic
Falsification Study* (Mathias Mesfin, arXiv 2605.04004).

Metodología: **14 familias de señales** intradía sobre **947 días** (2021-2025) en velas de 5
minutos. Criterio de aprobación declarado antes: walk-forward out-of-sample, **t ≥ 2,0**, mínimo
30 trades, positivo **después de 2 puntos de fricción ida-y-vuelta**, y consistencia año a año.

**Resultado: ninguna de las 14 cumplió las condiciones a la vez.** Los retornos brutos cayeron
entre **0,07 y 1,50 puntos por trade**, contra una fricción asumida de **2 puntos**. Es decir: no
es que las señales no tuvieran ninguna información — es que la información valía menos que el
costo de actuar sobre ella.

Las dos excepciones que sí pasaron son informativas por lo que son: **RTH Confluence Signal**
(t=5,83, +15,77 pts, 538 trades) y **London Session Signal B** (t=5,15, +5,77 pts, 289 trades).
Las dos son **confluencia + sesión**, no patrones de velas.

> 🟢 **Corrobora el diagnóstico central de AIdan.** El proyecto ya sabe que la comisión es ~87 %
> del drag y que el ganador medio de m15 es +7,8p contra un breakeven de 40,5 % de WR. Este
> estudio dice que esa relación **es la norma, no la mala suerte de AIdan**: el edge bruto de las
> señales OHLCV intradía vive por debajo de la fricción. Y refuerza la Fase 2 en curso: si el
> detector no pasa el control de entradas aleatorias, la conclusión coincide con las 14 de 14.
>
> 🔴 **Cierra una puerta:** buscar la familia de patrón OHLCV "correcta" en M5/M15 tiene
> antecedente de 14 fracasos sobre 947 días con metodología más estricta que la de AIdan. Si Fase
> 2 sale negativa, **no vale la pena probar una 15ª variante del mismo tipo.**

---

## 2. Meta-labeling: la única técnica de ML que encaja con "no bajar frecuencia"

**Fuente:** López de Prado, *Advances in Financial Machine Learning* (2018), vía
[Papers With Backtest](https://paperswithbacktest.com/course/meta-labeling),
[Hudson & Thames](https://hudsonthames.org/meta-labeling-a-toy-example/),
[Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling).

La idea: **separar el LADO del TAMAÑO**. Un modelo primario decide la dirección; un modelo
secundario decide, para cada señal del primario, si es un verdadero positivo y **con cuánto peso
actuar**. El secundario nunca genera oportunidades ni cambia la dirección.

Dos propiedades que importan acá:

1. *"Los efectos del overfitting son limitados al aplicar meta-labeling, porque el ML no decide
   el lado de la apuesta, solo el tamaño"* — es la técnica **diseñada para muestras chicas**, que
   es exactamente la restricción de AIdan (~139-200 trades limpios).
2. La probabilidad del meta-modelo se puede usar para **sizing continuo**, no para un
   bet/no-bet binario.

> 🟡 **Es el encaje más limpio con la restricción #1 del user.** AIdan tiene ya construido el
> modelo primario (los detectores de estructura) y ya tiene el registro de features en el momento
> (`entry_context`, 0 % faltante en data limpia). Meta-labeling **en su versión de sizing** no
> toca la frecuencia: se toman las mismas señales, con distinto peso.
>
> **Pero hay un bloqueante duro y hay que decirlo:** el lote mínimo del broker es **0,01**, y con
> un balance de ~$639 el sizing al 1 % ya está pegado al piso. **Sizing continuo con lote mínimo
> 0,01 es una perilla de 2 o 3 posiciones, no un continuo.** Es la misma razón por la que el track
> D1 nació en shadow. ⇒ Meta-labeling es la dirección correcta **para cuando el capital lo
> permita**; hoy la mitad de su valor no es realizable.
>
> **Contra que hay que tener presente:** [QuantConnect](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)
> y un [estudio de Lund](https://lup.lub.lu.se/student-papers/record/9120301/file/9120304.pdf)
> documentan que no es bala de plata: si el primario tiene *recall* bajo, no hay recall que
> cambiar por precisión y el secundario solo agrega varianza.

---

## 3. Etiquetado: triple barrera vs horizonte fijo

**Fuentes:** [Papers With Backtest](https://paperswithbacktest.com/course/triple-barrier-method),
[AXLFI](https://axlfi.com/blog/triple-barrier-method), [Sefidian](https://www.sefidian.com/2021/06/26/labeling-financial-data-for-machine-learning/),
[MQL5 Blueprint pt.2](https://www.mql5.com/en/articles/18864).

El problema del horizonte fijo: etiqueta +1/−1 según dónde está el precio después de N velas,
**ignorando el camino**. Una posición que llegó al doble y volvió recibe −1. Y trata a todas las
observaciones igual **sin importar su volatilidad**, así que los retornos esperados de una vela
muerta y de una vela de news pesan lo mismo.

> 🟢 **AIdan ya opera con triple barrera** (SL / TP / expiry) — eso está bien y no hay que
> cambiarlo. Lo que **no** tiene es el etiquetado consistente con eso: `result` es win/loss por
> P&L, y `sl_hit`/`tp_hit` son **tautológicos** (se derivan de `result`+`pips`, ya anotado en
> CLAUDE.md). Lo que falta es registrar **qué barrera se tocó primero**, que es información
> distinta de "ganó o perdió".
>
> 🟡 **Y hay una pieza que sí falta y es barata:** las barreras del proyecto están en **pips
> fijos por track** (m15 SL 15p / TP 60p). La literatura dice escalarlas por volatilidad. Ojo:
> AIdan **ya probó escalar constantes por ATR en el backtest H4/D1 y EMPEORÓ** (PF 1,40 → 1,02).
> ⇒ No es una recomendación libre de riesgo acá; si se prueba, va como cambio único y medido.

---

## 4. Latencia de news — lo verifiqué contra la data de AIdan y cambia el diagnóstico

**Fuente externa:** estudio sobre **993 eventos USD de alto impacto (2022-2025)**, calendario de
ForexFactory, citado en el material de señales intradía. Midió la deriva post-release y la
encontró **enteramente contenida en las velas +1 a +5** — el spike. Desde la vela +6 en adelante,
**todos los horizontes dan t entre 0,14 y 0,69**: no hay tendencia sostenida que capturar. Y data
de mercado 2025: el par mayor promedio completa **~80 % del movimiento en los primeros 3 minutos**.

**Lo medí sobre AIdan** (`tools/measure_news_latency.py`, read-only, 871 alerts direccionales,
6 meses):

| Métrica | Valor |
|---|---|
| Mediana de latencia publicación → detección | **8,9 min** |
| Detectadas dentro de **3 min** (donde ocurre ~80 % del movimiento) | **7,7 %** |
| Detectadas dentro de 25 min (velas +1..+5) | 76,0 % |
| p90 | 437,9 min |
| Tramo fetch → alert (el LLM) | **0,2 min de mediana** — el LLM *no* es el cuello de botella |

**Cómo casi lo reporté mal, y por qué importa.** La primera corrida daba **398 min de mediana** y
descartaba 733 de 871 filas por "negativas". Al revisar *por qué* se descartaban: la mediana de
las negativas era **−172,6 min ≈ −3 h**. `published_at` está en **UTC** y `fetched_at` en **hora
AR**. Corregido (misma conversión que ya hace `db.get_news_fetch_time()`), quedan **0 negativas
sobre 871 filas** y la mediana mensual se mueve entre 7,7 y 14,0 min ⇒ el offset es estable, no un
ajuste ad hoc. El número real es 8,9 min, no 398, y **el error era de signo**: el script inventaba
un problema 45× más grande que el real.

**Lectura honesta del resultado:**

- El LLM tarda 0,2 min. El retraso está en **el feed RSS**, no en el análisis. ⇒ *mejorar el prompt
  no puede arreglar esto*, que es consistente con que v3.47.0 (prompt postura-primero) no moviera
  el edge direccional.
- AIdan entra, típicamente, en la vela **+2** — dentro de la ventana del spike, pero **después de
  que se completó ~80 % del movimiento**. Eso no es "llegar tarde a la tendencia": es comprar la
  cola del spike, o sea **exactamente el "entra en el agotamiento"** que el proyecto ya
  diagnosticó por otra vía el 19-jun. Y explica mecánicamente el hallazgo del 24-jul de que news
  es **anti-skill** contra el drift (hit 53 % vs drift 63 %): entrando después del movimiento, lo
  que queda por capturar es el retroceso.
- **El corte por latencia NO pasa el gate:** `≤3 min` da 60,5 % WR (n=43) contra 51,3 % de
  baseline, pero el **CI95 es [45,6-73,6] y cruza el baseline**. Y corre sobre `alert_result`, no
  sobre `mt5_pnl` de broker. ⇒ **hipótesis con respaldo, no hallazgo.** No se actúa.

> 🟡 **Acción tomada (barata y frecuencia-neutra):** v3.57.0 guarda `news_latency_min` en
> `entry_context` **clasificado en el momento**, para poder medir esto limpio contra `mt5_pnl`
> hacia adelante. Es el patrón que el proyecto ya usa (clasificar al entrar, no reconstruir).
>
> **Qué NO hacer con esto:** poner un filtro "solo news ≤3 min". Bloquearía ~92 % del track sobre
> un hallazgo que no pasa el gate — el error exacto del hour gate y del late-breakout.

---

## 5. Volatilidad: percentil en vez de umbral fijo en pips

**Fuentes:** [QuantMonitor — regime filters](https://quantmonitor.net/how-to-identify-market-regimes-and-filter-strategies-by-trend-and-volatility/),
[TradingView — Volatility Regime Filter (ATR)](https://www.tradingview.com/script/6he9Wwoe-Volatility-Regime-Filter-ATR-based/),
[TradersPost — ATR strategies](https://blog.traderspost.io/article/atr-trading-strategies-guide).

La práctica documentada no es un umbral absoluto: es **rankear el ATR actual contra las últimas
~100 barras y exigir que el percentil esté entre ~20 y ~90**. Abajo del 20 el mercado está dormido;
arriba del 90 es volatilidad errática (news, crashes). Dato de apoyo en índices: **VIX 16-24 da
58 % de WR en ORB vs 48 % con VIX < 13**.

> 🟢 **Corrobora `M15_ATR_FLOOR`** (v3.55.0): que m15 saque 27,8 % de WR con ATR ≤8p y 51,6 % con
> ATR >8p es la misma forma de resultado que el VIX 16-24 vs <13. La perilla apunta al lado
> correcto.
>
> 🟡 **Y señala su defecto de diseño, que ya se está viendo en producción.** El piso de AIdan es
> **fijo en pips**, así que no se autoajusta: en el mercado muerto de agosto `ATR too low` pasó de
> 0 a **2.115 skips** y m15 cayó de 3,11 a 1,29 trades/día (−59 %). **Un piso por percentil
> mantiene elegible una fracción constante de las barras por construcción** — filtra el chop
> relativo sin colapsar la frecuencia en un mes tranquilo. Es la mejor idea concreta que salió de
> este research para la restricción "no bajar frecuencia".
>
> **Criterio a declarar antes de medirlo:** correr el percentil **en shadow contra el piso fijo**
> sobre las mismas velas y comparar (a) cuántas señales habilita cada uno por mes y (b) el WR de
> las que difieren. No cambiar el vivo hasta después de la lectura del ~1 sep del piso fijo:
> superponerlos rompe la atribución.
>
> 🟡 **Techo de ATR**: el percentil >90 es el "ATR ceiling" que está en el backlog de AIdan sin
> medir. Este research le da un umbral de referencia en vez de un número inventado.

---

## 6. Pullback vs breakout — el research coincide con lo que AIdan ya refutó

**Fuentes:** el estudio de falsificación de §1 y material comparativo
([24markets](https://24markets.com/education/trading-breakouts-vs-pullbacks),
[Strike](https://www.strike.money/technical-analysis/pullback-trading)).

La variante de **entrada en pullback** del ORB produjo *"resultados catastróficos"*: **80,7 % de
stop-out** y **−4,44 puntos netos**. Razón dada: una proporción alta de los breakouts aparentes
falla y revierte, lo que hace que esperar el pullback esté sistemáticamente del lado equivocado.
La entrada inmediata a 15 barras dio t=1,50 — **tampoco significativa**.

> 🟢 **Coincide con Fase 2 de AIdan**, que ya refutó el pullback-entry sobre 26 pares ("pullback
> refutado, e invertir tampoco paga", commit `71616eb`). Dos refutaciones independientes, con data
> distinta, en la misma dirección.
>
> 🔴 **Cierra el hilo #1 del checkpoint del 19-jun.** El "fix de fondo = entrar en el pullback de
> la tendencia" figura todavía como la hipótesis principal en las NOTAS. Entre la medición propia
> y esta, **corresponde bajarlo a refutado** y no volver a gastarle ciclos. El diagnóstico de que
> AIdan "entra en el agotamiento" sigue siendo válido; lo que se cae es **que el pullback sea la
> solución**.

---

## 7. Cuánta muestra hace falta, y el costo de buscar parámetros

**Fuentes:** [QuestDB — statistical power](https://questdb.com/glossary/statistical-power-analysis-in-backtesting-models/),
[guía de significancia](https://medium.com/@trading.dude/how-many-trades-are-enough-a-guide-to-statistical-significance-in-backtesting-093c2eac6f05),
Romano & Wolf (2005) para testeo múltiple, y el estudio de ORB citado en §5.

- Mínimo **30 trades** para empezar a inferir, **100+** para métricas confiables.
- **La calidad manda sobre la cantidad**: *"300 trades correlacionados de baja calidad pueden ser
  peores que 80 limpios e independientes"*. La correlación entre trades **reduce el n efectivo**.
- El dato más brutal: de **28,7 millones de configuraciones de ORB probadas, sobrevivió el
  0,51 %** al walk-forward. Una de cada ~200.

> 🟢 **Valida el gate del proyecto y su tamaño.** El n≥25 + Wilson que no cruza el baseline está
> en línea con el estándar, y el track record de rechazos (hour gate, 30 combos de entry gates,
> fade-chop 3×, sesgo direccional, 4 intentos de ML) es precisamente el 99,49 % que hay que tirar.
>
> 🟢 **Y justifica no afinar umbrales sobre la muestra propia**, que es la regla que ya se aplicó
> con `M15_ATR_FLOOR=8` ("el 8 venía pre-declarado desde el 17-jul; buscar el mejor número sería
> overfit"). Con 1-en-200 de supervivencia, buscar el mejor número **es** el modo de fallar.

---

## 8. Decaimiento de estrategias y TCA: separar "empeoró la estrategia" de "empeoró el broker"

**Fuentes:** [KX — drift detection y TCA en vivo](https://kx.com/blog/drift-detections-blind-spot-how-live-tca-insights-help-firms-win-the-race-against-alpha-decay/),
[estudio econométrico de model drift](https://www.globaleconomicnews.au/econometrics/quantifying-algorithmic-decay-an-econometric-approach-to-model-drift-amp-strategy-degradation-in-economic-systems),
[LuxAlgo — edge decay](https://www.luxalgo.com/blog/edge-decay-reoptimize-or-throw-out-strategy/),
[Alphaledger — drift y slippage en MT4/MT5](https://www.alphaledger.ai/news/how-to-spot-strategy-drift-slippage-and-execution-problems-in-mt4-mt5).

- Toda estrategia tiene **vida finita**, con cuatro mecanismos de decaimiento: *crowding, regime
  drift, microestructura y capacidad*.
- **El punto más útil:** el **TCA** (comparar costo esperado vs realizado en casi tiempo real)
  es lo que permite **distinguir drift real del modelo de cambios de liquidez o microestructura**.
  Sin eso, las dos cosas se ven igual: "el sistema empezó a perder".
- Disparadores de revisión que usan: ventanas móviles de **30-50 trades**, y drawdown acercándose
  a **1,5-2×** el máximo realizado previo.
- Al dispararse: reducir allocation, reentrenar, o iniciar baja — no las tres a la vez.

> 🟡 **Hueco concreto de AIdan, y barato.** El proyecto midió una vez un slippage de **11,2 p** en
> un spike (#625) y lo archivó como anécdota. No hay **registro sistemático de costo esperado vs
> realizado**. Con `mt5_pnl` broker-truth ya guardado, falta el otro lado: spread al momento de
> la orden, precio pedido vs precio de fill, comisión. Es un puñado de columnas y convierte
> "AIdan está perdiendo" en "AIdan está perdiendo **y el costo de ejecución explica X de eso**".
> Es especialmente importante **antes de cuenta real**, donde el slippage se paga de verdad.
>
> 🟡 **Stop por racha:** el audit ya lo señaló como el control faltante entre "perdí un trade" y
> "perdí el día". Acá aparece el umbral de referencia (30-50 trades de ventana, 1,5-2× el DD
> previo). AIdan ya tiene un circuito de 3 pérdidas en 2 h; lo que no tiene es la **ventana de
> equity**.

---

## 9. Sizing: Kelly negativo y el techo del lote mínimo

**Fuentes:** [Papers With Backtest — Kelly](https://paperswithbacktest.com/course/kelly-criterion-position-sizing),
[Medium — fixed-fractional / ATR / Kelly-lite](https://medium.com/@ildiveliu/risk-before-returns-position-sizing-frameworks-fixed-fractional-atr-based-kelly-lite-4513f770a82a),
[dangers of full Kelly](https://medium.com/@tmapendembe_28659/the-dangers-of-full-kelly-criterion-why-most-traders-should-use-fractional-kelly-criterion-instead-0338e3bcc705).

- *"Un Kelly negativo significa que la estrategia no tiene edge — ningún tamaño lo arregla."*
- La práctica es **Kelly fraccionario 0,25-0,50×**. Medio Kelly captura ~75 % del crecimiento
  óptimo con mucho menos drawdown; cuarto Kelly ~50 %.
- **La advertencia que aplica directo acá:** si el WR y el R:R salen de una **muestra chica**, el
  Kelly verdadero puede ser **muy inferior** al calculado.

> 🟢 **Corrobora el cálculo del audit** (Kelly global = −0,061 con p=0,381 y b=1,40) y su lectura:
> el 1 % fijo está **enmascarando** que el edge agregado no existe.
>
> 🔴 **Pero baja la prioridad de "Kelly por track", que el audit dejaba como el próximo paso.**
> Dos razones concretas: (a) con n=70 en m15 el Kelly estimado es ruido, y la propia literatura
> avisa que el verdadero puede ser mucho menor; (b) **el lote mínimo 0,01 sobre un balance de
> ~$639 no deja espacio para modular** — el sizing ya está contra el piso. ⇒ Es una mejora que
> **depende del capital**, no del código. Anotarla como bloqueada por cuenta, no como pendiente
> de implementar.

---

## 10. Sesión y liquidez: la única estructura que sobrevivió en §1

**Fuentes:** [NYCServers — London breakout](https://newyorkcityservers.com/blog/london-breakout-strategy),
[tradingstats — ORB sobre 6.142 días](https://tradingstats.net/orb-breakout-strategy-guide/),
[FTMO](https://ftmo.com/en/blog/opening-range-breakout-strategy-how-to-master-the-1530-us-session/).

- De las 2 señales que pasaron en el estudio de falsificación, **una es de sesión de Londres**.
- La apertura de Londres es *"la ventana más consistente para breakouts en forex"*, y el mecanismo
  propuesto es específico: **cuanto más apretado el rango asiático, más explosivo el breakout de
  Londres.**
- Sobre 6.142 días de ES/NQ (2014-2026), el ORB de 30 min da **64,6 %** de continuación en ES y
  **67,0 %** en NQ.

> 🟡 **Idea testeable y frecuencia-neutra: el rango de la sesión asiática como FEATURE de
> contexto**, no como filtro. AIdan ya clasifica sesión y ya demostró (v3.54.1) que su edge de D1
> **no dependía del reloj** — así que la hipótesis no es "operar solo en Londres" sino **"el
> ancho del rango asiático predice la calidad del breakout de Londres"**. Es del mismo tipo que
> el hallazgo de ATR que sí funcionó, y se puede medir sobre el histórico de velas que el proyecto
> ya baja para los backtests.
>
> **Criterio antes de medir:** dividir los breakouts de la sesión Londres/overlap por cuartil de
> rango asiático previo y exigir el gate de siempre (n≥25 por celda, Wilson que no cruce). Con 4
> cuartiles y ~5 trades/día, esto necesita **meses** — mejor medirlo primero **sobre velas
> históricas** (como se hizo con H4/D1), no esperando trades en vivo.

---

## 11. Lo que descarto explícitamente (para cerrar puertas)

| Idea | Por qué NO |
|---|---|
| Buscar la familia de patrón OHLCV correcta en M5/M15 | 14 de 14 familias fallaron sobre 947 días con criterio más estricto (§1) |
| Entrada en pullback como "el fix de fondo" | Refutada por Fase 2 propia **y** por el estudio externo (80,7 % de stop-out) (§6) |
| Optimizar umbrales sobre la muestra propia | 0,51 % de supervivencia en 28,7 M de configuraciones (§7) |
| Kelly por track ahora | Lote mínimo 0,01 sobre $639 no deja modular; n=70 hace ruido el estimador (§9) |
| Meta-labeling para *sizing* hoy | Mismo techo de lote mínimo; queda para cuando el capital lo permita (§2) |
| Escalar todas las constantes por ATR | AIdan ya lo probó en H4/D1 y **empeoró** (PF 1,40 → 1,02) (§3) |
| HMM / detección de régimen sofisticada | Ya descartado en el audit y no aparece evidencia nueva que lo reviva |
| Filtro "solo news ≤3 min" | Bloquearía ~92 % del track sobre un corte que no pasa el gate (§4) |

---

## 12. Ranking de lo accionable (por evidencia ÷ esfuerzo)

| # | Qué | Estado de la evidencia | Frecuencia | Esfuerzo |
|---|---|---|---|---|
| 1 | **Piso de ATR por PERCENTIL** en vez de pips fijos | 🟢 corrobora + resuelve un defecto ya visible en producción (−59 % de frecuencia en agosto) | **la protege** | bajo |
| 2 | **TCA: costo esperado vs realizado** (spread al enviar, pedido vs fill, comisión) | 🟡 práctica estándar; separa drift de microestructura | neutra | bajo |
| 3 | **`news_latency_min` limpio → medir contra `mt5_pnl`** | 🟡 hipótesis con respaldo, gate no pasado | neutra | **ya hecho en v3.57.0** |
| 4 | **Rango asiático como feature del breakout de Londres**, medido sobre velas históricas | 🟡 la única estructura que sobrevivió en §1 | neutra | medio |
| 5 | **Stop por ventana de equity** (30-50 trades, 1,5-2× DD previo) | 🟡 umbrales de referencia + hueco ya señalado por el audit | reduce (solo en drawdown) | bajo |
| 6 | **Techo de ATR (percentil >90)** | 🟡 backlog viejo, ahora con umbral de referencia | reduce algo | bajo |
| 7 | Registrar **qué barrera se tocó primero** (no tautológico) | 🟢 mejora el etiquetado sin tocar decisiones | neutra | bajo |
| 8 | Meta-labeling como **capa de confianza** (no de sizing) | 🟡 diseñado para muestra chica | neutra | alto |

**Lo primero que haría: el #1.** Es el único de la lista que ataca un problema que ya está
ocurriendo (m15 perdió el 59 % de su frecuencia en un mes tranquilo por un umbral que no se
autoajusta), tiene corroboración externa e interna, y **protege** la frecuencia en vez de
recortarla. El #2 es el que hay que tener **antes** de cuenta real.

---

## Fuentes

- [Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study — arXiv 2605.04004](https://arxiv.org/abs/2605.04004)
- [Meta-Labeling: How to Size Bets with ML — Papers With Backtest](https://paperswithbacktest.com/course/meta-labeling)
- [Why Meta-Labeling Is Not a Silver Bullet — QuantConnect](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/)
- [Evaluating the Effect of Meta-Labeling on an Equity Market Neutral Strategy — Lund University](https://lup.lub.lu.se/student-papers/record/9120301/file/9120304.pdf)
- [Meta Labeling (A Toy Example) — Hudson & Thames](https://hudsonthames.org/meta-labeling-a-toy-example/)
- [Meta-Labeling — Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling)
- [Triple-Barrier Method Explained — Papers With Backtest](https://paperswithbacktest.com/course/triple-barrier-method)
- [The Triple Barrier Method: A Better Way to Label Trades Than Using a Fixed Horizon — AXLFI](https://axlfi.com/blog/triple-barrier-method)
- [Labeling financial data for Machine Learning — Sefidian Academy](https://www.sefidian.com/2021/06/26/labeling-financial-data-for-machine-learning/)
- [MetaTrader 5 Machine Learning Blueprint (Part 2): Labeling Financial Data — MQL5](https://www.mql5.com/en/articles/18864)
- [Market Regime Filter: SMA + ATR Rules — QuantMonitor](https://quantmonitor.net/how-to-identify-market-regimes-and-filter-strategies-by-trend-and-volatility/)
- [Volatility Regime Filter (ATR based) — TradingView](https://www.tradingview.com/script/6he9Wwoe-Volatility-Regime-Filter-ATR-based/)
- [ATR Trading Strategies Guide — TradersPost](https://blog.traderspost.io/article/atr-trading-strategies-guide)
- [Trading Breakouts vs. Pullbacks — 24markets](https://24markets.com/education/trading-breakouts-vs-pullbacks)
- [Pullback Trading: Causes, Identification, Strategies — Strike](https://www.strike.money/technical-analysis/pullback-trading)
- [Statistical Power Analysis in Backtesting Models — QuestDB](https://questdb.com/glossary/statistical-power-analysis-in-backtesting-models/)
- [How Many Trades Are Enough? A Guide to Statistical Significance in Backtesting](https://medium.com/@trading.dude/how-many-trades-are-enough-a-guide-to-statistical-significance-in-backtesting-093c2eac6f05)
- [How Long Should You Test a Trading Strategy? — DayTrading.com](https://www.daytrading.com/how-long-test-trading-strategy)
- [Drift Detection's Blind Spot: Live TCA Insights vs Alpha Decay — KX](https://kx.com/blog/drift-detections-blind-spot-how-live-tca-insights-help-firms-win-the-race-against-alpha-decay/)
- [Quantifying Algorithmic Decay: Model Drift & Strategy Degradation](https://www.globaleconomicnews.au/econometrics/quantifying-algorithmic-decay-an-econometric-approach-to-model-drift-amp-strategy-degradation-in-economic-systems)
- [Edge Decay: Reoptimize or Throw Out Your Strategy — LuxAlgo](https://www.luxalgo.com/blog/edge-decay-reoptimize-or-throw-out-strategy/)
- [How to Spot Strategy Drift, Slippage, and Execution Problems in MT4/MT5 — Alphaledger](https://www.alphaledger.ai/news/how-to-spot-strategy-drift-slippage-and-execution-problems-in-mt4-mt5)
- [Execution Insights Through Transaction Cost Analysis (TCA) — Talos](https://www.talos.com/insights/execution-insights-through-transaction-cost-analysis-tca-benchmarks-and-slippage)
- [Understanding Transaction Costs: Spreads, Commissions and Account Structures on MT5 — TechLabari](https://techlabari.com/understanding-transaction-costs-spreads-commissions-and-account-structures-on-mt5/)
- [Kelly Criterion: Position Sizing for Algo Traders — Papers With Backtest](https://paperswithbacktest.com/course/kelly-criterion-position-sizing)
- [Risk Before Returns: Position Sizing Frameworks — Medium](https://medium.com/@ildiveliu/risk-before-returns-position-sizing-frameworks-fixed-fractional-atr-based-kelly-lite-4513f770a82a)
- [The Dangers of Full Kelly Criterion — Medium](https://medium.com/@tmapendembe_28659/the-dangers-of-full-kelly-criterion-why-most-traders-should-use-fractional-kelly-criterion-instead-0338e3bcc705)
- [London Breakout Strategy: How to Trade the Session Open — NYCServers](https://newyorkcityservers.com/blog/london-breakout-strategy)
- [Opening Range Breakout (ORB) Strategy: 6,142 Days of ES & NQ — TradingStats](https://tradingstats.net/orb-breakout-strategy-guide/)
- [Opening Range Breakout Strategy: How to Master the 15:30 US Session — FTMO](https://ftmo.com/en/blog/opening-range-breakout-strategy-how-to-master-the-1530-us-session/)
