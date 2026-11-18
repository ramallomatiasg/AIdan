# Registro de propuestas de mejora — AIdan

**Por qué existe (9 Oct 2026, pedido del user):** la rutina semanal venía cerrando con "nada pasa el gate"
y eso NO es un resultado completo. El user pidió todo el empeño en proponer: cambios sobre lo
implementado, combinaciones, o propuestas nuevas (como se hizo con el Setup 1 de Leo). Y dijo, con
razón, que tampoco confía ciegamente en mis pruebas. Este archivo es la cola: **cada semana entra
al menos una propuesta nueva y se EJECUTA la primera de la cola** (criterio declarado antes → tool
read-only → resultado acá). Si no pasa, la siguiente. La cola nunca queda vacía.

Reglas: nada se aplica a producción desde acá (sigue el OK del user + shadow). Antes de agregar
una idea, `grep` en `docs/historial_notas.md` y `docs/research_mercado_2026-08-19.md` §11.

## Cola (orden de ejecución)

| # | Propuesta | Tipo | Por qué puede funcionar | Costo | Estado |
|---|---|---|---|---|---|
| P0 | **Control POSITIVO del arnés.** Inyectar un edge conocido (look-ahead de 1 vela, o señal = signo del retorno futuro) en `backtest_fase2.py` y `backtest_fase4_planes.py` y exigir que reporten PASA con CI claro. | Validación de mis pruebas | Todos los backtests (Fases 2-6) dieron NO PASA. Un arnés que solo sabe decir "no" no está verificado. Si no detecta un edge sintético, **todos los NO PASA anteriores quedan en duda** y se re-miden. | ~medio día | ✅ **HECHO 9-oct: el arnés SÍ detecta edge** (ver abajo) |
| P1 | **Misma lógica, otro instrumento: XAUUSD, USTEC, DE40, US30 en M15/H1.** Correr el detector de `structure` (arnés Fase 2, `--symbols`) y los planes de Fase 4 sobre oro e índices. | Cambio de instrumento | Screen del 9-oct (abajo): en EURUSD el costo de un trade es **~15% del rango mediano de una vela M15**; en oro 1,5%, USTEC 2,3%, DE40 1,5%. El research dijo que lo que falla es el supuesto "scalping intradía con esta fricción" — esta es la salida más barata: 6-10x menos fricción por el mismo movimiento relativo. Nunca medido acá (0 menciones de XAU/oro en docs). | 1 día (cache de velas nuevo) | ❌ **NO PASA 10-oct** (`structure`): peor que el azar también en oro/índices (ver abajo). Cerrado para `structure`; la parte "planes de Fase 4" pasa a P9 |
| P2 | **Trend following clásico H4/D1: canal Donchian 20/55 con stop ATR y trailing (turtle)**, 20 pares + oro + índices, con swap. | Nueva lógica | H4 solo se probó con el detector de structure (refutado); Donchian nunca. Horizonte largo = costo chico frente al movimiento (c/ATR D1 ≈ 1%). Choca con lote mínimo como D1, pero primero saber si hay edge. | 1 día | ❌ **NO PASA 16-oct**: −0,23R/trade, PEOR que el azar (ver abajo). Cerrado turtle D1/H4 en FX |
| P3 | **Rango asiático → ruptura de Londres** (orden en los extremos del rango 00-07 UTC, SL al otro lado, TP 1-2× rango). | Nueva lógica | Rankeada en el research del 19-ago, nunca medida acá. Es confluencia + sesión, las dos cosas que sobrevivieron en el estudio de falsificación. | medio día | ❌ **NO PASA 17-oct**: −0,031R/trade, 4/20 pares; le gana al azar pero no al costo (ver abajo). Cerrado |
| P4 | **Lead-lag de la cesta USD:** cuando GBPUSD/AUDUSD/NZDUSD ya se movieron X·ATR en M5 y EURUSD no, operar el "catch-up". | Nueva lógica | El cache `.cache_fase2/M5_500000` tiene 26 pares alineados. Nunca medido. | 1 día | ❌ **NO PASA 22-oct**: bruto +0,13p contra 0,80p de costo, 0/4 objetivos (ver abajo). Cerrado |
| P5 | **Compresión → expansión en D1: inside bar / NR7 breakout** con stop en el otro extremo. | Nueva lógica | Nunca medido. Barato con las velas D1 que ya hay. | medio día | ❌ **NO PASA 22-oct**: −0,10R, no mejor que el azar, 2/20 pares (ver abajo). Cerrado |
| P6 | **Volumen de ticks como filtro de la ruptura** (spike de `tick_volume` vs mediana 20 barras). | Cambio sobre lo implementado | Backlog #4 desde mayo, nunca medido. Se mide como celda del arnés Fase 2, no en vivo. | medio día | en cola, **baja prioridad** (22-oct): filtra `structure`, que es peor que el azar en todo instrumento (Fase 2, P1); un filtro solo puede recortar, no crear información. ❌ **NO PASA 23-oct**: −0,82p; elige mejor que el azar pero sigue en pérdida |
| P7 | **Leo: pedirle su diario REAL de operaciones** (fecha, par, entrada, SL, TP, resultado) + Setup 2. | Método externo | Si Leo es rentable, sus trades reales son la verdad contra la que comparar la traducción, mejor que el audit visual. Pendiente de su respuesta al artifact. | 0 (depende de él) | esperando a Leo |
| P8 | **Combinar lo implementado: calendar play + canal rápido de news (v3.65.0)** = operar el dato con número a T+15-60 s, dirección por sorpresa, TP en la excursión mediana a +3 min medida por el shadow. | Combinación | Solo tiene sentido si el shadow de calendar play junta n≥25 (hoy 1 fila, por horario). | 0 hasta tener data | bloqueada por muestra |
| P9 | **A1 (reversión a 2σ, Fase 3b) en oro e índices**, con el mismo arnés en pseudo-pips de P1 (`.cache_p1/M15`). | Misma lógica, otro instrumento + combinar lo medido | A1 fue la ÚNICA señal que le ganó al azar (~+0,5p bruto sobre el control) y murió por costo (0,9p+spread en FX). En oro/índices el costo medido en P1 es **0,20-0,28 pseudo-pips** ⇒ el mismo +0,5 sobre el azar podría quedar neto positivo. A diferencia de `structure`, acá hay información probada; falta saber si sobrevive a otro instrumento. | medio día (cache ya bajado) | ❌ **NO PASA 22-oct** (4/5: CI cruza cero; el neto es la deriva alcista de los índices), ver abajo. Cerrado A1 en oro/índices |
| P10 | **Fade del canal Donchian D1 (reversión de mediano plazo), probado SOLO en los 6 pares reservados.** Corto cuando el cierre rompe el máximo de 20 días, largo al revés; misma ejecución/stop/salida que P2 invertidas. | Hipótesis nacida de un NO PASA, test fuera de muestra | P2 dio que entrar con la ruptura de 20 días es **peor que el azar** (−0,23R vs control −0,14R, 16/20 pares negativos, las 2 mitades) con costo de solo 0,016R ⇒ el bruto negativo es información, no fricción. Distinto de lo refutado: fade-chop y L1 eran intradía (M5) con costo ~15% del rango; acá el costo es ~1% del movimiento. Como la idea sale de mirar los 20 pares, **se declara antes y se mide únicamente en los 6 reservados** (nunca mirados) ⇒ out-of-sample limpio. | medio día (tool de P2 + flag) | ❌ **NO PASA 22-oct** (4/5: CI cruza cero), ver abajo. Cerrado Donchian D1 en FX en cualquier dirección |
| P11 | **Carry con filtro de tendencia (D1/semanal):** mantener el lado del par que COBRA swap solo cuando la tendencia D1/60d va en la misma dirección; rebalanceo semanal, 20 pares. | Paper (Menkhoff et al. 2012; Lustig-Verdelhan) | Es la única familia de FX con premio documentado que NO es de precio intradía: el retorno viene del diferencial de tasas, no de adivinar la dirección, y el horizonte largo deja el costo en ~1% del movimiento. Nunca medido acá (0 menciones de carry en docs). **Límite de data a resolver ANTES de declarar:** el `spec.json` del cache trae el swap ACTUAL, no el histórico ⇒ usarlo para 2020-26 sería look-ahead (en 2020-21 las tasas estaban en ~0). Hace falta una tabla mensual de tasas de política (Fed/BCE/BoE/BoJ/RBA/RBNZ/BoC/SNB, pública) para reconstruir el swap mes a mes. | 1 día (tabla de tasas + tool) | ❌ **NO PASA 23-oct**: +0,004%/semana (cero); la tendencia le resta al carry. Ver abajo |
| P12 | **Drift pre-FOMC (Lucca & Moench 2015) en índices:** largo US500/USTEC/DE40 desde el cierre del día anterior al anuncio hasta 14:00 ET del día del FOMC (antes del dato); descriptivo en USD (EURUSD). | Paper + otro instrumento | Es el único efecto de calendario documentado que ocurre ANTES del dato (no hay que reaccionar rápido, que es donde news perdió) y vive en índices, donde el costo medido en P1 es 0,2-0,3 pp. Nunca medido acá (0 menciones de FOMC/Lucca en docs). **Ojo:** la literatura posterior (2016+) reporta que el efecto se debilitó tras publicarse ⇒ prior bajo, y con ~8 reuniones/año hay ~50 eventos en 2020-26 ⇒ el gate tiene que ser por evento, no por vela. Necesita la tabla de fechas FOMC (pública) y `.cache_p1/M15`. | medio día | ❌ **NO PASA 23-oct** (4/5: no le gana a la misma ventana en días normales), ver abajo |
| P13 | **A1 como OPCIÓN BINARIA** (acierto de dirección a 15 min, sin importar el tamaño). | Otro producto (pedido del user: "¿otro broker, tipo IQ Option?") | En binaria el pago no depende del tamaño del movimiento ⇒ una señal que acierta seguido por poco (A1) es la que mejor encaja. | medio día | ⚠️ **PASA el criterio 23-oct pero es ARTEFACTO**: el diagnóstico adversarial lo reduce a ~52,1-52,6% en horario líquido (empate con payout 90%). Ver abajo. **Shadow en vivo P13b armado 23-oct** (Deriv, desde el 26-oct) |
| P14 | **Carry SOLO (sin tendencia), solo en los 6 reservados.** | Hipótesis nacida de P11, fuera de muestra | En P11 el carry solo dio +0,037%/semana y la tendencia restaba. | 1 h | ❌ **NO PASA 23-oct**: +0,001%/semana; el swap gana y el precio se lo come |
| P15 | **Carry de funding en cripto (delta-neutral): comprar spot y vender el perpetuo** cuando el funding promedio de 7 días supera un umbral; BTC/ETH/SOL. | Otro mercado, premio estructural | Los apalancados en largo PAGAN funding a los cortos: la ganancia no depende de adivinar el precio (como el carry de FX, pero el premio cripto es mucho mayor). Data pública y gratis (historial de funding de Binance/Bybit/Hyperliquid), testnets para el shadow. Riesgos: funding negativo en mercados bajistas, riesgo de exchange, liquidación de la pata corta. | 1 día (bajar historial + tool) | ✅ **PASA 23-oct (primera de la línea), también fuera de muestra**: +4,8%/año sobre el capital (reservados +5,8%), pero 2025-26 casi cero. Ver abajo |
| P16 | **Prima de volatilidad (vender volatilidad) con filtro de contango del VIX**: estar corto de volatilidad (proxy: ETF SVXY) solo cuando VIX < VIX3M. | Otro mercado, premio estructural | La volatilidad implícita suele estar por encima de la realizada: quien vende el "seguro" cobra un premio documentado. Data diaria gratis (VIX, VIX3M, SVXY). Riesgo de cola (feb-2018, mar-2020): el filtro de contango es lo que se mide. Paper trading en Alpaca o IBKR. | medio día | ❌ **NO PASA 23-oct**: CAGR +28,6% pero caída máx 55% y Sharpe 0,80, peores que comprar SPY (34%, 0,95). Ver abajo |
| P17 | **Deriva post-resultados (PEAD) en acciones de EE.UU.**: comprar tras una sorpresa positiva de ganancias, mantener ~20-60 días. | Otro mercado, anomalía documentada | arXiv 2512.00280 (2025): ~0,43%/mes de alfa, solo en sorpresas positivas. Comisión cero en brokers como Alpaca (con API de paper trading). Falta una fuente gratis de fechas y sorpresas de resultados. | 1-2 días | ❌ **NO PASA 24-oct**: +0,48%/20 días sobre SPY, pero el control (mismas acciones, día al azar) da +0,38% con p95 +0,61%, y la cola NEGATIVA sube igual (+0,47%) ⇒ es la deriva de las ganadoras de hoy, no la sorpresa. Ver abajo |
| P18 | **Sesgo favorito-longshot en mercados de predicción (Polymarket/Kalshi)**: comprar el resultado favorito (precio ≥ 0,90) cerca del cierre. | Otro mercado, sesgo conductual | En apuestas está documentado que los longshots se sobrepagan; en Polymarket sin verificar. Data pública de mercados resueltos. Descartado del mismo rubro: el arbitraje de latencia en los mercados cripto de 15 min (lo cerraron con fees dinámicos en 2026) y el market making (selección adversa; el market maker interno de Kalshi no es rentable). | 1 día | ❌ **NO PASA 28-oct** (Kalshi, no Polymarket: DNS): n=664 eventos, −13,99%/apuesta neto, CI [−17,4, −11,1]; el favorito acierta 86% contra 93% del precio ⇒ en Kalshi el sesgo va al REVÉS. Ver abajo |
| P19 | **Shadow en papel del carry de funding (P15)**: cada 8 h, con el funding y los precios públicos de Binance en vivo, registrar qué haría la regla congelada de P15 (entrar/salir, funding cobrado, costo) en una base propia; sin órdenes. | Siguiente paso de lo único que pasó | P15 es la única idea de la línea que pasó, también fuera de muestra, pero 2025-26 rindió casi cero. Antes de cualquier plata hay que ver si el premio sigue vivo HOY y si la ejecución (base spot-perpetuo al entrar) se parece a la del backtest. Mismo esquema que el shadow P13b (proceso propio + tarea). | medio día | 🧪 **SHADOW ARMADO 27-oct** (`tools/shadow_funding.py`, criterio `docs/p19_shadow_funding_criterio.md`): lectura a 90 días (~25-ene), decisión a 180 (~25-abr). **+ libro Hyperliquid desde el 4-nov** (enmienda 1 = P21-A, OK del user): lectura ~2-feb, decisión ~3-may. Ver abajo |
| P20 | **Cash-and-carry con futuros TRIMESTRALES de cripto** (comprar spot + vender el futuro con vencimiento de Binance, BTC/ETH, mantener hasta el vencimiento) cuando la base anualizada supera la tasa libre + costo. | Misma lógica que P15, otro instrumento | Mismo premio que P15 (lo pagan los apalancados en largo) pero **se fija al entrar**: la base pactada no cambia con el régimen día a día, que es justo lo que hizo caer a P15 en 2025-26. Al vencimiento converge al spot ⇒ el resultado se conoce al entrar salvo costos. Data pública (velas de los contratos de entrega de Binance, `dapi`/`fapi` con vencimiento). Nunca medido acá. | 1 día | ❌ **NO PASA 30-oct**: +2,81%/año sobre el capital contra tasa libre 3,40%; 2025 +2,8% y 2026 +0,4%, también debajo ⇒ no arregla lo que hizo caer a P15. Ver abajo. Cerrado |
| P21 | **Carry de funding (P15) en Hyperliquid y en el diferencial entre exchanges** (mismo motor y reglas congeladas de P15; variante: cobrar el funding del exchange que más paga y cubrir en el que menos). | Misma lógica, otro instrumento/venue | P15 es lo único que pasó, y cayó en 2025-26 en Binance. Hyperliquid liquida funding cada HORA y suele pagar más que Binance (otro público, más apalancado); el diferencial entre exchanges es un premio distinto del nivel. API pública (`api.hyperliquid.xyz`, resuelve desde esta red) con historial de funding. Nunca medido acá (P15 solo usó Binance). | medio día | ✅ **A PASA 31-oct, también fuera de muestra** (+6,2%/año sobre el capital vs tasa libre 4,6%, ~2,5× Binance en el mismo período); **B (diferencial) NO PASA** (+3,3%). Pero 2025-26 vuelve a quedar debajo de la tasa libre. Ver abajo |
| P22 | **Loop de hipótesis con IA sobre datos que AIdan no mira** (posicionamiento COT, tasas, bonos, VIX, dólar, petróleo; 7 monedas, 1999 →): la IA (Groq) propone con lista cerrada, el arnés prueba descubrimiento 1999-2014 → reserva 2015 → shadow hacia adelante, y TODO lo probado vuelve como memoria. Familias cerradas tras 3 fallos, espejos y duplicados rechazados. | Pedido del user (28-oct): que AIdan aprenda de todo y se pula solo | Aprende de 25 años de datos y no de 7 trades/día; mira más que precio. | 1 día | 🧪 **ARMADO 28-oct**: 4 vueltas, 31 hipótesis, 0 pasan el descubrimiento (ver abajo) |
| P21 | **¿Un broker más barato salva algo?** Fusion Zero (USD 4,50 ida y vuelta) contra IC (USD 7), sobre todo lo ya medido. | Pedido del user (28-oct) | Si el problema fuera el costo, bajar 1/3 la comisión daría vuelta lo que estaba cerca. | medio día | ❌ **NO PASA 28-oct**: ver abajo |
| P23 | **A1 en EUR/USD con entrada LÍMITE (maker)**: poner la orden en la banda de 2σ en vez de entrar a mercado, con Fusion. | Cambio de ejecución sobre lo único con información | Con Fusion A1 en EUR/USD queda en +0,08 pips (cero). Entrar con límite ahorra el spread y entra en mejor precio, pero sufre selección adversa (solo se llena cuando el precio sigue en contra): hay que medirlo con velas de 1 minuto o ticks, no con M15. | 1 día | ❌ **NO PASA 3-nov**: −0,43p por operación llenada; el límite se llena justo en las que salen mal (selección adversa: las no llenadas habrían dado +6,9p a mercado). Ver abajo. Cerrado A1 en EUR/USD por ejecución |
| P24 | **Prima nocturna en índices (overnight drift)**: largo US30/USTEC/DE40 del cierre de la sesión de contado a la apertura siguiente, neto de spread y del swap REAL de MT5; descriptivo: el tramo intradía (apertura → cierre). | Paper + otro instrumento | Lou, Polk & Skouras (2019) y Cliff, Cooper & Gulen (2008): en EE.UU. casi todo el retorno de las acciones se gana de noche y el intradía rinde ~0. No adivina dirección intradía (lo refutado acá) y vive en índices, donde el costo medido en P1 es 0,2-0,3 pp. El riesgo es el swap del CFD (se cobra justo por la noche que se mantiene). Data ya bajada (`.cache_p1/M15`). Nunca medido acá. | medio día | ❌ **NO PASA 5-nov**: bruto +0,03 a +0,06%/noche, pero el swap del CFD (~0,027%/noche) se lo come y la ventana no le gana a cualquier otra de la misma duración (deriva alcista). Ver abajo. Cerrado |
| P25 | **Cambio de mes en índices (turn-of-the-month)**: largo US500/US30/USTEC/DE40 del cierre del último día hábil del mes al cierre del 3er día hábil del mes siguiente, neto de spread y swap REAL de MT5; control = misma ventana de 4 días en fechas al azar del mismo año. | Paper + otro instrumento | Ariel (1987), Lakonishok-Smidt (1988), McConnell-Xu (2008): en EE.UU. casi todo el retorno mensual de las acciones se concentra en esa ventana (flujos de sueldos y fondos). Distinto de Fase 5 (rebalanceo de FX fin de mes) y de P12 (pre-FOMC). No adivina dirección intradía y vive en índices (costo 0,2-0,3 pp). Prior medio: efecto publicado hace décadas, puede estar arbitrado. ~80 meses en 2020-26 ⇒ gate por evento. | medio día | ❌ **NO PASA 6-nov** (3/5): la ventana sube +0,38% en bruto contra ~0 del control, pero con 76 meses es ruido (CI cruza cero, no supera el p95) y el swap le saca 0,15. Ver abajo. Cerrado |
| P26 | **Valor en FX (PPP): mensual, largo las monedas más baratas y corto las más caras** según el tipo de cambio REAL (con IPC) contra su promedio de 5 años; G10 contra USD, 1999 →, descubrimiento 1999-2014 / reserva 2015 →. | Paper | Asness-Moskowitz-Pedersen (2013, "Value and Momentum Everywhere") y Menkhoff et al. (2017, "Currency Value"): el valor es el tercer premio clásico del FX junto a carry y momentum, y es el único de los tres que este proyecto nunca midió (carry: P11/P14; momentum: Fase 4 E4 y el loop P22). Horizonte de meses ⇒ el costo es despreciable; no adivina dirección intradía. Data gratis: tipos de cambio e IPC mensuales de FRED, que `hyp_data.py` ya baja. Se puede sumar como feature `value_5y_z` al catálogo de P22 en vez de tool aparte. | medio día | ❌ **NO PASA 7-nov** (2/5): −0,58%/año neto, peor que ordenar al azar (p50 −0,02%/mes, p95 +0,18); solo precio ~0. Ver abajo. Cerrado |
| P27 | **Juez LLM con contexto completo sobre cada señal de AIdan** (TAKE/VETO viendo velas D1→M5, niveles y ATR, sin fechas ni etiquetas de AIdan), probado sobre los 300 trades reales más recientes; `gpt-oss:20b` local. | Pedido del user (4-nov): que la IA decida razonando como juez | La 1ra prueba (shadow trader) no fue justa: veía 10 datos de M5 y repetía las etiquetas de tendencia de AIdan (100% de sus razones). Juzgar señales con contexto es otra pregunta. Placebo con velas de otro trade. | 1 día + ~15 h de cómputo | ❌ **P27 NO PASA 4-nov**: TAKE −$0,58 vs VETO −$0,42 por trade (no separa) y el placebo separa igual o mejor. **P27b (calendario) y P27c (memoria) tampoco pasan** ⇒ P28 no se arma. Ver abajo |
| P28 | **LLM operador:** con el mismo contexto de P27 (velas D1→M5, calendario, memoria) el LLM GENERA el plan completo (dirección, entrada, SL, TP y tamaño dentro de límites fijos en código: riesgo máx por trade, pérdida diaria, kill switch, posiciones), primero sobre trades pasados y en papel, con criterio declarado y placebo. | Pedido del user (4-nov): que el LLM decida cómo operar y cuánto | Juzgar una operación armada es más fácil que armarla: solo tiene sentido si P27/P27b/P27c separan. | 1 día | ❌ **No se arma** (4-nov): P27, P27b y P27c no pasaron |
| P29 | **Screen de información:** antes de armar estrategias, medir qué dato anticipa el retorno (IC fuera de muestra, placebo, costo real) sobre FX 20 años, índices/oro 2020-26 y cripto. | Pedido del user (4-nov): "estamos atacando el problema que no es" | Ver `docs/fuentes_de_ventaja_2026-11-04.md`. | 1 día | ✅ **HECHO 4-nov**: 1 de 138 celdas de dirección pasa (DE40 hora del día, 4 h); la volatilidad es predecible en 30 de 33. Ver abajo |
| P30 | **Estacionalidad horaria en índices europeos, fuera de muestra:** misma medición de P29 F1 en STOXX50, FR40 y UK100 M15 (nunca mirados) + el mapa de horas de DE40 aplicado tal cual a STOXX50. | Lo único que pasó P29 | Si es un flujo real (apertura/cierre europeos), tiene que aparecer en los otros índices de la misma sesión. Necesita bajar M15 de MT5 con AIdan cerrado (sábado). | medio día | ❌ **NO PASA 9-nov**: el mapa de horas de DE40 aplicado a STOXX50 y F40 en 2017-2020 (antes de cualquier dato de DE40) da neto −6,9 y −6,4 bps, sin información (IC debajo del placebo). El pase de P29 era el azar esperable de 138 celdas. Ver abajo. Cerrado |
| P31 | **Volatilidad esperada vs costo en los trades de AIdan:** en los 300 trades reales, ¿el movimiento esperado al entrar (R1, la única info confiable del gráfico) dividido el costo separa ganadoras de perdedoras? | P29: la vol es predecible (IC 0,15-0,44) y AIdan opera con pisos fijos en pips | No da dirección; puede evitar operar cuando el movimiento no cubre el costo (generaliza el piso de ATR de m15, que sí funcionó). | medio día | ❌ **NO PASA 4-nov** (3/5): va en la dirección esperada en las dos mitades pero no es significativo, y lo que queda sigue perdiendo. Ver abajo |
| P32 | **Vencimiento trimestral (triple witching) en índices:** largo/corto US30/USTEC/DE40 en la semana del 3er viernes de mar/jun/sep/dic contra la semana siguiente (la literatura dice: deriva a favor antes del vencimiento por cobertura de opciones y reversión después); control = semanas normales del mismo año. | Flujo forzado (escalera B) | Los dealers de opciones tienen que deshacer coberturas en fecha fija; es un flujo que no depende del gráfico. Distinto de P12 (FOMC), P25 (cambio de mes) y Fase 5 (fin de mes FX). Prior bajo-medio: ~25 vencimientos en 2020-26 ⇒ gate por evento, poca potencia; si n no alcanza para el criterio, decirlo y no forzarlo. Data ya bajada (`.cache_p1/M15`). | medio día | ❌ **NO PASA 10-nov**: −0,15%/evento en US30+USTEC (n=52), CI cruza cero, debajo del control; la semana siguiente sube en vez de revertir. Ver abajo. Cerrado |
| P33 | **Pre-feriado en índices de EE.UU. (Ariel 1990; Kim-Park 1994)**: largo US30/USTEC del cierre del contado del penúltimo día hábil antes de un feriado de la NYSE al cierre del último día hábil antes del feriado (1 día), neto de spread y swap real; control = mismo día de la semana al azar del mismo año. | Flujo de calendario (escalera B) | Es la otra anomalía de calendario clásica, distinta del cambio de mes (P25) y de la noche (P24). Dura 1 día ⇒ paga 1 sola noche de swap, que fue lo que mató a P24 y le restó a P25. ~9 feriados/año ⇒ ~55 eventos 2020-26: n chico, gate por evento. Prior bajo-medio (publicado hace décadas). Data ya bajada (`.cache_p1/M15`), arnés de P25. | 2 h | ❌ **NO PASA 11-nov**: por feriado +0,10% neto pero CI [−0,07, +0,28] cruza cero y no supera al control (un día cualquiera del mismo año); US30 ≈ 0. Ver abajo. Cerrado |
| P34 | **Efecto Gotobi en USD/JPY (fixing de Tokio):** largo USDJPY de 00:00 a 00:55 UTC (antes del fixing de las 9:55 de Tokio) los días gotobi (día del mes múltiplo de 5, o el hábil anterior si cae en finde) y descriptivo corto de 00:55 a 03:00; control = misma ventana en días no gotobi del mismo año. | Flujo forzado (escalera B) | Ito & Yamada (2017, *Puzzles in the Tokyo fixing*) y Bessho et al.: los importadores japoneses compran dólares en el fixing de los días de pago (5, 10, 15, 20, 25, fin de mes) y el USDJPY sube antes. Es un flujo de calendario que no mira el gráfico, en un par con spread ~0,1-0,3p, y nunca se midió acá (0 menciones de gotobi/Tokio en docs). Prior medio-bajo: publicado, puede estar arbitrado. ~70 días gotobi/año ⇒ ~450 eventos 2020-26, n suficiente. Data ya bajada (`.cache_fase2/M5_500000/USDJPY`). | medio día | ❌ **NO PASA 11-nov**: la ventana sube +0,85p bruto los días gotobi, pero sube lo mismo (+0,97p) cualquier otro día; neto −0,29p y negativo desde 2024. Ver abajo. Cerrado |
| P35 | **Demanda de cobertura al cierre de EE.UU. (Baltussen, Da, Lammers & Martens 2021, *JFE*):** si el índice va fuerte en el día (retorno desde el cierre anterior hasta 30 min antes del cierre del contado, en el quintil extremo del descubrimiento), seguir esa dirección en US30/USTEC durante los últimos 30 min; una operación por día, neto de spread; control = mismo tramo con el signo de un día al azar. | Flujo forzado (escalera B) | Los dealers cortos de gamma (opciones) y los ETF apalancados TIENEN que comprar al final de los días de suba y vender en los de baja, por mandato y a hora fija: es un flujo con mecanismo, no un patrón de gráfico. Una sola operación de 30 min por día, sin swap, en índices (costo ~0,4 bps). Ojo: queda en el borde de lo cerrado (E, intradía) ⇒ se acepta solo porque la regla es fija y viene del paper, sin parámetros propios; si no pasa no se buscan variantes. Data ya bajada (`.cache_p1/M15`). | medio día | ❌ **NO PASA 11-nov**: −3,9 bps por día en la reserva, CI [−6,3, −1,3] debajo de cero; el último tramo REVIERTE en vez de seguir al día (2020-26). Ver abajo. Cerrado |
| P36 | **Flujos diarios de los ETF de bitcoin al contado (EE.UU., desde ene-2024) → retorno de BTC del día siguiente:** si la entrada neta del día (dato público, publicado después del cierre de EE.UU.) está en el tercio alto del descubrimiento, largo BTC perpetuo de la apertura de Asia a 24 h; tercio bajo, corto; neto de comisión y funding real de Binance; placebo = flujos de otro día. | Flujo / información (escalera B-C) | Es plata que entra o sale por mandato de compra de acciones del ETF, y el dato llega con horas de demora respecto del precio: si el mercado no lo absorbió todo, el día siguiente lo muestra. No es patrón de gráfico y nunca se midió acá (0 menciones de ETF/flujos). Riesgo: ~470 días hábiles ⇒ n medio; el dato puede estar ya en el precio (los creadores de mercado compran durante el día). Falta confirmar una fuente gratis con el histórico diario por ETF (p.ej. farside) accesible desde esta red. | 1 día | ❌ **NO PASA 11-nov** (3/5): reserva +0,15%/día, CI [−0,09, +0,40] cruza cero, y el descubrimiento perdía (−0,16%); el flujo sigue al precio del mismo día (Spearman +0,41) y casi no anticipa el siguiente (+0,04). Ver abajo. Cerrado |
| P37 | **Emisión de stablecoins → retorno de BTC (Griffin & Shams 2020; Lyons & Viswanath-Natraj 2023):** si el cambio de 7 días de la oferta total de USDT+USDC (dato público diario, DefiLlama) está en el tercio alto del descubrimiento, largo BTC perpetuo 7 días; tercio bajo, afuera (descriptivo: corto); neto de comisión y funding real de Binance; placebo = la misma serie desplazada. | Flujo / información (escalera B-C) | Emitir stablecoins es plata nueva que entra al mercado cripto para comprar: es un flujo con mecanismo, se publica on-chain y no sale del gráfico. Nunca se midió acá (0 menciones de stablecoin/emisión). Riesgo: la emisión puede SEGUIR al precio en vez de anticiparlo (causalidad inversa) ⇒ el placebo desplazado y el control de momentum de BTC deciden. Semanas solapadas ⇒ n efectivo ~300 desde 2020: una observación por semana. Data gratis sin clave (DefiLlama + Binance público). | medio día | ❌ **NO PASA 11-nov**: con el umbral de 2020-22 solo 8 semanas en la reserva (n≥40 exigido) y la emisión sigue al precio (Spearman con la semana previa +0,24, con la siguiente +0,09). Ver abajo. Cerrado |
| P38 | **Reversión después del fixing de Tokio, fuera de muestra:** corto el cruce con yen de 00:55 a 03:00 UTC los días gotobi, en **EURJPY y AUDJPY** (nunca mirados), con control = misma ventana en días no gotobi y costo real. | Flujo forzado (escalera B), descriptivo pre-declarado de P34 | En P34 el tramo posterior al fixing (declarado como descriptivo antes de medir) dio +2,68p neto en USDJPY. Puede ser el rebote del flujo del fixing o una caída del dólar en esa hora todos los días: el control lo separa. Se prueba SOLO en pares no mirados para que no sea pescar en P34. Prior bajo. | 2 h | ❌ **NO PASA 12-nov** (5/6): neto +2,16p, CI [+0,48, +3,87], le gana al control, pero n=594 < 600 (AUDJPY solo tiene velas desde 2025). El efecto vive casi entero en el **fin de mes** (EURJPY +10,3p vs +1,0p el resto) ⇒ entra P44 solo en los JPY reservados. Ver abajo |
| P39 | **Prima de volatilidad en cripto (Deribit):** vender volatilidad a 30 días de BTC cuando el DVOL (volatilidad implícita pública de Deribit) supera a la realizada de los 30 días previos; medido como varianza implícita − realizada de los 30 días siguientes (proxy de un straddle/varianza vendida), neto de un costo de opciones conservador, con el riesgo de cola reportado (peor mes, caída máxima). | Premio por riesgo (escalera A) | Es el mismo seguro que se vende en P16, pero en cripto la implícita suele estar muy por encima de la realizada (los apalancados compran protección y calls). No adivina dirección. Data pública sin clave (`get_volatility_index_data`, BTC desde 2021) + precio de Binance. Automatizable en Deribit si pasa. Riesgo: colas (mar-2020 queda afuera del DVOL). | medio día | ⚠️ **PASA el criterio 12-nov (BTC 5/5 y ETH fuera de muestra 5/5)**: +6,4 puntos de vol por mes neto, pero casi todo en 2021-23; reserva +1,5 con CI que cruza cero y **2025-26 negativo** en los dos; el DVOL sobrestima lo que cobra un straddle real. No es un hallazgo todavía. **🧪 SHADOW P39b ARMADO 13-nov** (OK del user): `tools/shadow_vol_deribit.py`, tarea `aidan-shadow-vol`; diagnóstico ~13-dic, decisión ~13-nov-2027. Ver abajo |
| P40 | **Tendencia semanal en cripto (time-series momentum):** cada lunes, largo el perpetuo de cada una de las 10 monedas del cache de P15 si su retorno de 4 semanas es positivo, afuera si no; neto de comisión y funding real; descubrimiento 2020-22 / reserva 2023-26 y monedas reservadas de P15 (ADA, LINK, LTC, AVAX) como fuera de muestra. | Premio por riesgo / flujos (escalera A-B) | En FX el TSMOM semanal murió por costo (Fase 4 E4); en cripto el movimiento semanal es 10-20 veces el costo y la literatura (Liu-Tsyvinski 2021) reporta momentum de series de tiempo. Data ya bajada (`.cache_p15`). Automatizable. Riesgo: es sobre todo exposición a la suba de cripto ⇒ el control es "siempre largo". | 2 h | ❌ **NO PASA 12-nov** (3/5): reserva +0,79%/semana con CI que cruza cero y Sharpe 0,99, apenas sobre siempre largo (0,88) y **debajo del placebo** (p95 1,10) ⇒ elegir semanas al azar con la misma exposición rinde igual. Baja la caída máxima (42% vs 90%) pero eso lo hace cualquier regla que esté afuera la mitad del tiempo. Ver abajo |
| P41 | **Funding extremo como señal contraria:** cuando el funding promedio de 3 días de BTC/ETH está en el decil alto del descubrimiento (largos apalancados apiñados), corto el perpetuo 7 días (cobra el funding); decil bajo, largo. Reserva 2023-26 y monedas reservadas de P15. | Información / flujo forzado (escalera B-C) | Si los apalancados están apiñados, las liquidaciones fuerzan ventas: es un flujo con mecanismo, distinto de cobrar el funding (P15), que es delta-neutral. Data ya bajada. Prior medio-bajo. | 2 h | ❌ **NO PASA 14-nov**: −1,34% por operación en la reserva (CI bajo cero); el corto con funding alto pierde (ver abajo). Cerrado |
| P42 | **Prima de Coinbase (demanda de EE.UU.) → BTC del día siguiente:** diferencia diaria entre el precio de BTC-USD en Coinbase y BTCUSDT en Binance (corregida por USDT/USD); tercio alto ⇒ largo 24 h, bajo ⇒ corto; neto de costo y funding; placebo desplazado. | Información (escalera C) | La prima mide compradores institucionales de EE.UU. que el precio de Binance todavía no tiene. API pública de Coinbase y Binance, sin clave. Riesgo: como P36, puede ser solo el reflejo del precio del mismo día ⇒ el placebo y la correlación con el día previo deciden. | medio día | ❌ **NO PASA 14-nov**: reserva +0,19%/día pero CI toca cero y el descubrimiento pierde (ver abajo). Cerrado |
| P43 | **Vencimiento mensual de opciones de Deribit (último viernes, 08:00 UTC):** retorno absoluto y dirección de BTC en las 48 h previas vs posteriores al vencimiento, contra los mismos tramos en viernes normales; si la volatilidad baja antes y sube después (cobertura de dealers), vender volatilidad antes / estar afuera. | Flujo forzado (escalera B) | Los dealers cubren gamma a hora fija; en índices el vencimiento (P32) no dio nada, pero en BTC el mercado de opciones pesa mucho más frente al contado. Velas 1 h públicas de Binance. Prior bajo. | 2 h | ❌ **NO PASA 14-nov**: la vol post/pre sube 7,5% más que un viernes normal, CI cruza cero (ver abajo). Cerrado |
| P44 | **Gotobi de FIN DE MES en el fixing de Tokio, solo en los JPY reservados:** corto CHFJPY y NZDJPY de 00:55 a 03:00 UTC el último día hábil del mes, comisión real + spread; control = misma ventana el resto de los días hábiles; costo pesimista +0,3p. | Flujo forzado (escalera B), fuera de muestra de P38 | En P38 el corto después del fixing le ganó claramente al control (+2,16p neto, CI sobre cero) pero casi todo venía del fin de mes (EURJPY +10,3p vs +1,0p). Como la idea sale de mirar EURJPY/AUDJPY/USDJPY, se mide **solo** en los 2 JPY reservados de Fase 4 (nunca abiertos). Automatizable (una orden por mes por par). Ojo: ~80 eventos por par en 6,7 años ⇒ el gate tiene que ser por evento y n mínimo realista; verificar ANTES el largo del cache (lo que falló en P38). | 2 h | ❌ **NO PASA 14-nov**: juntos +3,89p neto CI [+0,49, +7,14] y 5/6 criterios, pero NZDJPY −1,36p (falla "cada par > 0"). Ver abajo |
| P45 | **Carry de funding de Hyperliquid (P21-A) en las otras monedas líquidas de HL, reglas congeladas:** el mismo motor y umbrales de P21-A sobre las ~15 monedas con más volumen de HL que no estaban en P21 (lista fijada por volumen ANTES de mirar el funding). | Premio por riesgo (escalera A), robustez de lo único que pasó | P21-A pasó también fuera de muestra (+6,2%/año sobre el capital) pero con pocas monedas y 2025-26 debajo de la tasa libre. Si el premio es estructural tiene que aparecer en monedas nunca usadas; si no aparece, el pase era de 2-3 monedas. API pública de HL, sin clave. Automatizable (es lo que ya corre en papel en P19). | medio día | ✅ **PASA 16-nov** (+7,3%/año, CI [+5,5, +9,4], 14/15 monedas > 0) pero 2025-26 en +2,7-2,8%, debajo de la tasa libre, igual que P15/P21. Ver abajo |
| P46 | **Nowcast de inflación de la Fed de Cleveland contra el consenso, antes del CPI de EE.UU.:** si el nowcast del CPI m/m supera al consenso, largo USD (corto EURUSD) del cierre del día previo hasta 15 min ANTES del dato; al revés si queda debajo; control = misma ventana en días sin CPI. | Información que el precio no tiene (escalera C) | Knotek & Zaman (2017-2023): el nowcast de Cleveland le gana al consenso de analistas. No necesita velocidad (se posiciona antes, cerrando antes del dato: no repite el #969). Página pública. **Riesgo de datos a resolver antes de declarar:** historia del consenso (FF solo da la semana actual) y del nowcast tal como se veía cada día (vintage). Si no hay vintage gratis, se descarta. ~12 eventos/año ⇒ muestra chica. | 1 día | ❌ **NO PASA 16-nov**: −14,3p netos por operación (n=39); el nowcast acertó el signo de la sorpresa solo 9/25. Ver abajo |
| P47 | **Inclusión en el S&P 500 (flujo forzado de fondos índice):** largo la acción agregada desde el día después del ANUNCIO hasta el cierre previo a la inclusión efectiva; contra el S&P 500 y contra acciones del mismo sector y tamaño; 2015-2026 con fechas públicas (Wikipedia) y precios diarios gratuitos. | Flujo forzado (escalera B) | Los fondos índice TIENEN que comprar al cierre de la fecha efectiva; el precio sube entre anuncio y fecha. Greenwood & Sammon (2022) muestran que el efecto se achicó mucho ⇒ prior bajo, pero se mide la ventana anuncio→efectiva, que es la que todavía se cita. Automatizable con un broker de acciones de comisión cero (paper en Alpaca). | 1 día | en cola, **sin datos** (16-nov): no hay fuente gratis de fechas de ANUNCIO (Wikipedia solo trae la fecha efectiva). Se hace si aparece una |
| P48 | **Carry de funding de P15 con ETH en staking (stETH/wstETH en vez de ETH spot):** misma regla congelada de P15 en ETH, pero la pata larga es stETH ⇒ cobra funding + rendimiento de staking; se mide con el APR histórico de Lido (DefiLlama, público) y el descuento stETH/ETH (Curve) como riesgo, incluido jun-2022. | Premio por riesgo (escalera A), combinación sobre lo único que pasó | P15 cayó a casi cero en 2025-26 porque el funding bajó; el staking agrega ~3%/año que NO depende del funding. Riesgo declarado: el descuento de stETH en jun-2022 (−5%) puede comerse años de premio. Automatizable igual que P19. | medio día | ⚠️ **INVÁLIDA por datos 16-nov**: el cociente diario stETH/ETH de DefiLlama tiene ruido de ±10% (imposible); el NO PASA no vale. Reemplazada por P52 (WBETH de Binance) |
| P49 | **Desbloqueos grandes de tokens (oferta forzada):** corto el perpetuo de Binance desde 7 días antes hasta el día de un desbloqueo ≥ 1% de la oferta circulante; control = mismas monedas en ventanas sin desbloqueo; neto de costo y funding real; 2022 → con el calendario histórico de emisiones de DefiLlama. | Flujo forzado (escalera B) | Los receptores del desbloqueo (fondos, equipo) venden o se cubren antes; el mercado lo sabe por calendario pero el corto paga poco. Riesgo de datos: que DefiLlama no tenga la historia de emisiones gratis o con fechas tal como se conocían ⇒ si no, se descarta antes de declarar. | 1 día | ❌ **NO PASA 17-nov**: +0,86% por evento pero CI agrupado por semana [−1,5, +3,2] y la 1ra mitad negativa. Ver abajo |
| P50 | **Préstamo de stablecoins vs letras del Tesoro:** rendimiento histórico de prestar USDC/USDT (Aave v3 Ethereum, DefiLlama yields, público) contra la letra a 3 meses (FRED), neto de gas y con los episodios de estrés (depeg de USDC mar-2023) como riesgo de cola; descriptivo: Binance Simple Earn. | Premio por riesgo (escalera A) | Es la versión más simple del premio que pagan los apalancados de cripto (son los que toman prestado); no requiere adivinar precio. Criterio: premio neto sobre la letra > 0 en la reserva (2024 →) con el peor episodio dentro de un límite declarado. Prior medio; útil para el capital chico del user. | medio día | ❌ **NO PASA 16-nov**: en 2023 prestar en Aave pagó 2,1%/año MENOS que la letra. Ver abajo |
| P51 | **Cierre del gap de apertura semanal en FX:** si el lunes abre con gap > 0,5·ATR(D1) contra el cierre del viernes, operar hacia el cierre del viernes entrando a la 1ra vela M5 con spread normal (NO la de apertura: en Fase 4 la vela de apertura semanal tenía spread medio 16p), salida al tocar el cierre del viernes o a las 24 h; 20 pares de `.cache_fase2/M5_500000`, comisión + spread real, control = misma entrada/salida en lunes sin gap. | Liquidez/flujo (escalera B), nunca medido | El gap del domingo nace con liquidez mínima (pocos bancos abiertos) y la lore de traders dice que "se cierra"; nunca se midió acá (grep `gap`: 0 en registro e historial). Riesgo declarado: el spread ancho del arranque y que el gap sea información (noticias del finde) y no ruido. ~350 lunes por par. | medio día | ❌ **NO PASA 17-nov** (inválido por costo): con la cache pasa los 6 criterios y los reservados, pero el spread REAL a la hora de entrada es ~14,5p (ticks) contra 0,2p de la cache ⇒ neto ≈ −2p. Ver abajo |
| P52 | **Carry de funding de P15 en ETH con la pata larga en WBETH de Binance** (ETH en staking de Binance, sube solo contra ETH): misma regla congelada de P15; el valor de la pata larga sale del par `WBETHETH` de Binance (velas de 8 h, mismo exchange que el perpetuo). Descubrimiento may-2023 → 2024, reserva 2025-26. | Premio por riesgo (escalera A), combinación sobre lo único que pasó | Reemplaza a P48, que murió por datos: acá el cociente sale de un par real del mismo exchange (sin el ruido de dos precios diarios). El staking suma ~3%/año que no depende del funding, justo lo que le falta a P15 en 2025-26. Automatizable igual que P19. | medio día | ❌ **NO PASA 17-nov**: descubrimiento +6,5%/año (pasa) pero la reserva 2025-26 da +1,5%/año contra 4,0% de tasa libre. Ver abajo |
| P53 | **Anuncios de deslistado de Binance (venta forzada):** corto el perpetuo (de Binance u otro exchange donde siga) desde la vela siguiente al anuncio de deslistado del spot hasta el día del deslistado; control = mismas monedas en ventanas sin anuncio; neto de costo y funding real. Fechas del listado público de anuncios de Binance. | Flujo forzado (escalera B) | Los tenedores del spot TIENEN que vender o sacar las monedas antes de la fecha; los market makers se retiran. Riesgo de datos: que el archivo de anuncios no se pueda bajar entero o que el perpetuo deje de existir antes ⇒ si no, se descarta antes de declarar. | 1 día | en cola (nueva 16-nov) |
| P54 | **Comprar la stablecoin cuando pierde la paridad (USDC/USDT < 0,995 en Binance) y vender en ≥ 0,999 o a los 7 días**, velas de 1 h del par `USDCUSDT` (y `FDUSDUSDT`), comisión real. | Liquidez/flujo (escalera B) | En un depeg la venta es de pánico y la emisora respalda 1:1; el premio es por poner liquidez cuando nadie quiere. Muestra chica (mar-2023 y algunos más) ⇒ el criterio tiene que ser por episodio y con el peor caso en plata (un depeg que no vuelve, tipo UST, es la cola). Bajo capital, automatizable. | medio día | en cola (nueva 16-nov) |
| P55 | **Desbloqueos en versión RELATIVA, solo en la reserva 2025-26:** corto el perpetuo de la moneda que desbloquea y largo por el mismo monto una cesta igual de las otras monedas del universo de P49 (sin evento en ±14 días), de D−7 a D; mismos eventos, costo de las dos patas y funding real de ambas; control = mismas monedas en semanas sin evento. | Flujo forzado (escalera B), sobre lo que dejó P49 | En P49 la semana previa al desbloqueo rindió ~2,3 puntos mejor que una semana normal de la misma moneda, pero el mercado de alts subiendo se comía el corto absoluto. Neutralizar el mercado es lo que eso sugiere; como la idea sale de mirar el descubrimiento, **se mide solo en 2025-26, que nadie miró** (un solo disparo, sin reintentos). Automatizable con los mismos datos públicos. | medio día | en cola (nueva 17-nov) |
| P56 | **Corto de los tokens recién listados en perpetuos de Binance (días 2 a 30):** cada perpetuo USDT nuevo desde 2023, corto del open del día 2 al día 30, funding real; control = mismas monedas en ventanas de 29 días a partir del día 60; CI agrupado por semana. | Flujo forzado (escalera B) | Los tokens nuevos llegan con airdrops, launchpools y market makers con inventario que se vende en las primeras semanas (oferta forzada, no información). Datos públicos (fapi klines), sin supervivencia porque se toma toda moneda desde su listado. Riesgo declarado: funding muy negativo en los listados calientes (el corto paga) y squeezes del día 1 (se saltea a propósito). | medio día | en cola (nueva 17-nov) |
| P57 | **Vault HLP de Hyperliquid contra la letra:** rendimiento histórico del vault de market making de la casa (API pública de HL, historial de valor de la cuota) contra la letra a 3 meses (FRED), con el peor episodio (manipulación de JELLY mar-2025) como cola; criterio sobre la reserva 2025-26 y caída máxima declarada. | Premio por riesgo (escalera A) | Es cobrar el spread y las liquidaciones como market maker sin operar nada: depositar USDC y esperar, con montos chicos (sirve para $500-1.000). Nunca medido acá (grep HLP/vault: 0). Riesgo: contrato/exchange y episodios de pérdida del vault. | 2 h | en cola (nueva 17-nov) |
| P15b | **Rotación del carry de funding a las K=3 monedas que más pagan** (sobre P15). | Cambio sobre lo que pasó | Varias monedas pasan mucho tiempo afuera y esa plata rinde 0; concentrar en las que más pagan la usaría mejor. | medio día | ❌ **NO PASA 23-oct**: +0,21%/año sobre P15, CI cruza cero, y últimos 12 meses −0,9%. Ver abajo |

## Lo medido por esta línea

### 9 Oct 2026 — P0 control positivo: el arnés FUNCIONA (`tools/control_positivo_arnes.py`)

Mismas piezas del arnés de Fase 2 (importadas), señales de un oráculo que acierta la dirección a 3
velas con probabilidad q. 6 pares M15, n=4.800, perfil vivo (SL 15 / TP 60 / 3 velas).

| q (acierto) | neto/trade | CI95 | veredicto |
|---|---|---|---|
| 0,50 (sin edge) | −0,93p | [−1,25, −0,60] | NO PASA ✔ |
| 0,52 | −0,27p | [−0,60, +0,07] | NO PASA |
| 0,55 | −0,01p | [−0,35, +0,33] | NO PASA |
| 0,60 | +0,47p | [+0,13, +0,80] | PASA ✔ |
| 0,70 | +2,33p | | PASA |
| 1,00 | +6,59p | | PASA ✔ |

Lectura: **el arnés no tiene sesgo a favor ni en contra** (q=0,50 da exactamente el costo, q≥0,60
pasa). Los NO PASA de Fases 2-6 valen como medición. Lo que muestra además: **en EURUSD M15 hace
falta acertar ~55% de las direcciones a 45 min solo para empatar el costo**. Ningún método que
probamos llega a eso. Por eso P1 (instrumentos donde el costo es 6-10x más chico) pasa a ser la
próxima: ahí la misma precisión que hoy pierde podría empatar o ganar.

### 9 Oct 2026 — screen de costo vs rango por instrumento (read-only, velas MT5, sesión 08-17 UTC)

Costo = spread mediano guardado en la vela (mínimo de la barra ⇒ cota optimista, pareja para todos) +
comisión ICMarkets Raw (FX 0,7 pip/lote RT; oro $0,07/oz; índices y petróleo sin comisión).
EURUSD muestra spread 0 en las velas; el real medido por TCA es 0,10p ⇒ costo ≈0,8p.

| Instr. | costo | rango M15 | ATR H1 | ATR D1 | costo/M15 | costo/H1 | costo/D1 |
|---|---|---|---|---|---|---|---|
| EURUSD | 0,8p | 5,2p | 7,8p | 55p | **~15%** | ~10% | 1,5% |
| GBPUSD | 0,8p | 6,9p | 10,2p | 74p | 11,6% | 7,8% | 1,1% |
| USDJPY | 0,7p | 9,0p | 16,5p | 88p | 7,8% | 4,2% | 0,8% |
| XAUUSD | $0,12 | $8,2 | $15,1 | $97,7 | **1,5%** | 0,8% | 0,12% |
| US500 | 0,5 | 6,5 | 10,7 | 80 | 7,7% | 4,7% | 0,6% |
| USTEC | 0,9 | 40 | 67 | 461 | **2,3%** | 1,3% | 0,2% |
| US30 | 1,2 | 52 | 77 | 582 | 2,3% | 1,6% | 0,2% |
| DE40 | 0,5 | 33 | 47 | 335 | **1,5%** | 1,1% | 0,15% |
| XTIUSD | 0,02 | 0,39 | 0,63 | 3,21 | 5,1% | 3,2% | 0,6% |

Lectura: no dice que el detector gane en oro. Dice que **el costo que se comió el edge de ~0,5p
sobre el azar en A1 (Fase 3b) sería 6-10x más chico** en oro/índices. Es el hueco más grande sin
medir. Ojo para la cuenta: lote mínimo 0,01 en XAUUSD = 1 oz ⇒ SL de $8 = $0,08 de riesgo; en
índices 0,1 lote ⇒ $1/punto. Ambos permiten respetar el 1% con $600, al revés que el D1 de EURUSD.
Spread de oro/índices se ensancha fuera de sesión y en datos: medirlo con el spread REAL del
release como hace `score_calendar_play`.

Script: scratch `cost_screen2.py` (sin MT5 no corre; pasarlo a `tools/` si P1 avanza).

### 10 Oct 2026 — P1 `structure` en oro e índices: NO PASA, peor que el azar (`tools/backtest_p1_instrumentos.py`)

Criterio `docs/p1_otro_instrumento_criterio.md` (commit `50c06a8`, antes de medir). Velas M15 2020-2026 (150k por
instrumento), perfil vivo de M15 en **pseudo-pips** (rango M15 mediano normalizado al de EURUSD = 5,30p), sesión
london, spread de la vela (cota optimista) + comisión Raw.

| Instr. | n | neto/trade | costo (pp) | control mediana |
|---|---|---|---|---|
| EURUSD (ancla) | 76.104 | −0,92 | 0,80 | −0,83 |
| XAUUSD | 76.993 | −0,25 | 0,24 | −0,17 |
| USTEC | 76.526 | −0,32 | 0,26 | −0,30 |
| US30 | 75.443 | −0,18 | 0,20 | −0,17 |
| DE40 | 77.719 | −0,59 | 0,28 | −0,52 |

Pool de los 4 nuevos: n=306.681, **neto −0,34 pp**, CI [−0,36, −0,30], mitades −0,41 / −0,26, **control p95 −0,27 ⇒
peor que entrar al azar**; 0/4 positivos. El ancla reproduce Fase 2 (−0,92 vs −1,04), así que el tool mide lo mismo.
Lectura: **bajar el costo 3-4x se comió 2/3 de la pérdida, pero el bruto queda en ~−0,1 ⇒ `structure` no tiene
información en ningún instrumento**; el problema es la idea (comprar rupturas en M15), no la fricción. Coherente con
Fase 2b/3. Cerrado: no probar `structure` en otros índices/variantes. Lo que sí deja: el costo en oro/índices es
~0,2-0,3 pp contra 0,8 en EURUSD ⇒ sirve para P9 (A1, que sí tiene información). Swap no descontado: 2,5-3,6% de los
trades cruzan el rollover (inmaterial). Arnés con control positivo (P0) ⇒ el NO PASA vale.

### 16 Oct 2026 — P2 turtle / Donchian D1 y H4: NO PASA, peor que el azar (`tools/backtest_p2_donchian.py`)

Criterio `docs/p2_donchian_criterio.md` (commit `192e3c2`, antes de medir). 20 pares FX, velas M5 re-muestreadas a
D1/H4, ejecución fuera del rollover, stop 2·ATR(20) vela fina por vela fina, salida por canal, swap real.
Neto en R (1R = stop inicial).

| Sistema | n | neto/trade | bruto | costo | swap | ganados |
|---|---|---|---|---|---|---|
| **D1 20/10 (principal)** | 891 | **−0,226R** | −0,162 | 0,016 | −0,049 | 28% |
| D1 55/20 | 468 | −0,346R | −0,271 | 0,017 | −0,059 | 22% |
| H4 20/10 | 5.271 | −0,138R | −0,090 | 0,026 | −0,022 | 29% |
| H4 55/20 | 2.738 | −0,159R | −0,099 | 0,030 | −0,031 | 26% |

Principal: CI [−0,31, −0,14], mitades −0,19 / −0,26, **4/20 pares positivos**, **control (entradas al azar con las
mismas salidas) mediana −0,14 / p95 −0,09 ⇒ peor que el azar**. Reservados NO mirados. Lectura: el costo acá es
chico de verdad (0,016R ≈ 1% del riesgo) — **el problema no es la fricción, es que en FX 2020-2026 la ruptura de
20/55 días revierte**. Coherente con todo lo intradía (las rupturas pierden, la reversión tiene información) ⇒ entra
P10. Cerrado: no barrer N/M/stop ni otro TF para turtle en FX sobre esta data.
Oro/índices (descriptivo, sin swap): oro da +0,13 a +0,95R pero **todo sale de los largos** en la suba 2020-26
(D1 20/10: largos +0,56R, cortos −0,45R; H4 55/20: +0,95 / −0,44) ⇒ es la deriva, no el sistema (la misma trampa
que refutó al LLM de news). USTEC D1 +0,13/+0,26R con n=24-49 (ilegible); US30 y DE40 negativos. No se propone.
Nota de data: USDCAD, AUDNZD, AUDCAD, AUDJPY y CADJPY tienen cache M5 solo desde ene-2025 (n chico en esos pares).
Arnés con control positivo (P0) ⇒ el NO PASA vale.

### 17 Oct 2026 — P3 rango asiático → ruptura de Londres: NO PASA (`tools/backtest_p3_rango_asiatico.py`)

Criterio `docs/p3_rango_asiatico_criterio.md` (commit `ea1e715`, antes de medir). 20 pares M5 2019-12 → 2026-08,
reloj convertido a hora de Londres con los DST de NY y Londres (server = NY+7h, verificado en el cache), rango
[00:00, 07:00), stops OCO activos [07:00, 12:00), stop al otro extremo, objetivo 1·W, salida 16:00.

| Variante | n | neto/trade | bruto | costo | ganados |
|---|---|---|---|---|---|
| **TP 1·W (principal)** | 25.790 | **−0,031R** | +0,015 | 0,046 | 50% |
| TP 2·W (descriptivo) | 25.790 | −0,017R | +0,029 | 0,046 | 43% |

Principal: CI [−0,041, −0,020], mitades −0,018 / −0,043, **4/20 pares positivos**, control (entrada al azar en la
misma ventana, misma geometría) mediana −0,046 / p95 −0,038 ⇒ **le gana al azar (~+0,015R) pero no al costo**. Dispara
el 92% de los días; ambiguos <1%. En pips EURUSD: −0,84p/trade con W mediano 22p. Terciles de ancho (descriptivo):
angosto −0,057R · medio −0,030 · ancho −0,006 — ninguno positivo. Reservados NO mirados.
Lectura: mismo patrón que A1 (Fase 3b) y E3a (Fase 4): **hay una pizca de información (+0,3p en EURUSD sobre el
azar) pero menos que el costo**. Es la primera ruptura medida acá que NO es peor que el azar — la ruptura de Londres
tiene algo de continuación, la de M15 a cualquier hora no — pero no alcanza para operar. Cerrado: no barrer horarios,
buffer, objetivo ni filtro de ancho sobre esta data. Arnés con control positivo (P0) ⇒ el NO PASA vale.

### 22 Oct 2026 — P10 fade del canal Donchian D1, SOLO 6 reservados: NO PASA (`tools/backtest_p10_fade_donchian.py`)

Criterio `docs/p10_fade_donchian_criterio.md` (commit `d9dd03d`, antes de medir). Trade de P2 principal (D1 20/10)
con la dirección invertida: misma entrada, sale con la regla de canal de la posición que fadea, stop 2·ATR del otro
lado. Una sola corrida sobre los reservados (el tool se niega a repetirla).

| Muestra | n | neto/trade | bruto | costo | swap | ganados | CI95 | mitades | pares>0 | control p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Reservados (decide)** | 528 | **+0,071R** | +0,122 | 0,025 | −0,026 | 55% | [−0,024, +0,161] | +0,04 / +0,11 | 4/6 | +0,021 |
| 20 pares P2 (descriptivo) | 1.467 | −0,012R | +0,050 | 0,014 | −0,048 | 50% | [−0,068, +0,045] | +0,00 / −0,03 | 8/20 | −0,008 |

Reservados: pasa 4 de 5 (n, dos mitades, le gana al control p95, 4/6 pares) y **falla el CI** (límite inferior
−0,024) ⇒ NO PASA. Lo más cerca que llegó cualquier prueba de esta línea, pero: **(a)** in-sample, en 20 pares, el
mismo fade da −0,012R (cero); **(b)** dos pares hacen todo (GBPCAD +0,36R, NZDCAD +0,19R; sin ellos queda ~−0,03R);
**(c)** el swap se come casi todo el bruto en los 20 pares. Lectura: en D1 la ruptura de 20 días revierte un poco
(bruto +0,05 a +0,12R), pero no lo suficiente para pagar el swap de tenerla ~14 noches. Cerrado por criterio:
**Donchian D1 en FX, en cualquier dirección, sobre esta data** — no barrer N/M/stop/salida. Los reservados ya se
gastaron para esta familia. Arnés con control positivo (P0) ⇒ el NO PASA vale.

### 22 Oct 2026 — P9 A1 (reversión a 2σ) en oro e índices: NO PASA (`tools/backtest_p9_a1_instrumentos.py`)

Criterio `docs/p9_a1_instrumentos_criterio.md` (commit `dc2a273`, antes de medir). Señal `gen_A1` importada, M15
(no hay M5 de oro/índices sin MT5), salida por tiempo a H32 (8 h), una posición por instrumento, sin cruzar el
rollover, pseudo-pips de P1, spread de la vela + comisión Raw.

| H32 (decide) | n | neto pp | bruto | costo | largos | cortos | control mediana |
|---|---|---|---|---|---|---|---|
| EURUSD (ancla) | 2.775 | −0,17 | +0,63 | 0,80 | −1,02 | +0,59 | −0,73 |
| XAUUSD | 2.945 | +0,13 | +0,35 | 0,22 | +0,78 | −0,46 | −0,27 |
| USTEC | 2.484 | +1,15 | +1,56 | 0,41 | +2,11 | +0,21 | −0,37 |
| US30 | 2.385 | +0,98 | +1,21 | 0,24 | +1,48 | +0,44 | −0,18 |
| DE40 | 2.618 | −0,82 | −0,09 | 0,73 | −0,15 | −1,46 | −0,69 |

Pool de los 4 nuevos: n=10.432, **neto +0,33 pp, CI [−0,43, +1,09]**, mitades +0,21 / +0,45, 3/4 positivos, control
p95 +0,32 ⇒ pasa 4 de 5 y **falla el CI**. Y lo que el criterio pedía mirar: **el neto sale de los LARGOS** (USTEC
+2,11, US30 +1,48, oro +0,78) en un período en que los tres subieron fuerte; los cortos dan +0,21 / +0,44 / −0,46 y
DE40 pierde de los dos lados. El control al azar llega a p95 +0,32 por la misma deriva (largos al azar en índices que
suben ganan). Es la trampa de P2 en oro y del LLM de news: **deriva, no señal**. H4 (−0,31) y H16 (−0,26) negativos.
El ancla EURUSD M15 reproduce el patrón de Fase 3b (bruto +0,63, le gana al azar, pierde contra el costo de 0,80).
Lectura: bajar el costo no alcanzó para que la reversión pague por sí misma. Cerrado: no barrer umbral/media/horizonte
ni filtrar "solo cortos" sobre esta data (eso sería elegir el lado después de verlo). Arnés con control positivo (P0)
⇒ el NO PASA vale.

### 22 Oct 2026 — P4 lead-lag de la cesta USD: NO PASA (`tools/backtest_p4_lead_lag.py`)

Criterio `docs/p4_lead_lag_criterio.md` (commit `c924563`, antes de medir). EURUSD/GBPUSD/AUDUSD/NZDUSD en M5
alineados (499.577 velas): si los otros tres se movieron ≥1 ATR en 30 min en la misma dirección y el objetivo
quedó en ±0,25 ATR, entrar en el objetivo a favor; salida por tiempo a H6 (30 min), una posición por objetivo,
sin cruzar el rollover.

| H6 (decide) | n | neto p | bruto | costo | control mediana |
|---|---|---|---|---|---|
| EURUSD | 4.074 | −0,67 | +0,13 | 0,80 | −0,80 |
| GBPUSD | 3.361 | −0,57 | +0,25 | 0,82 | −0,82 |
| AUDUSD | 1.809 | −0,69 | +0,11 | 0,80 | −0,80 |
| NZDUSD | 1.849 | −0,93 | −0,09 | 0,84 | −0,83 |

Pool: n=11.093 (~6/día), **neto −0,69p, CI [−0,85, −0,52]**, las dos mitades negativas, 0/4 positivos, control p95
−0,687 ⇒ empata con el azar. Falla 4 de 5. H3 −0,70 y H12 −0,72, también negativos. Lectura: el "catch-up" existe
pero es diminuto (+0,1 a +0,25p brutos, ~+0,1p sobre el azar) contra 0,8p de costo en los XXX/USD. Es el mismo
patrón de toda la línea intradía: algo de información, muy por debajo de la fricción. Cerrado: no barrer ventana,
umbrales ni horizonte. Los reservados (cesta JPY) no se miran. Arnés con control positivo (P0) ⇒ el NO PASA vale.

### 22 Oct 2026 — P5 ruptura del NR7 en D1: NO PASA (`tools/backtest_p5_nr7.py`)

Criterio `docs/p5_nr7_criterio.md` (commit `5b18dda`, antes de medir). 20 pares M5 re-muestreados a D1; tras un NR7,
OCO en el máximo/mínimo del día `k` activas el día siguiente (01-23 server), stop en el otro extremo (1R = rango de
`k`), salida por tiempo a las 3 sesiones; spread de entrada y salida + comisión + swap real. Control = mismas
entradas con dirección al azar.

| Variante | n | neto/trade | bruto | costo | swap | ganados | stop |
|---|---|---|---|---|---|---|---|
| **NR7 (principal)** | 2.976 | **−0,100R** | −0,044 | 0,041 | −0,015 | 36% | 54% |
| Inside bar (descriptivo) | 2.864 | −0,067R | −0,013 | 0,038 | −0,016 | 40% | 47% |

Principal: CI [−0,147, −0,051], mitades −0,075 / −0,125, **2/20 pares positivos** (USDJPY +0,18, EURJPY +0,04),
control mediana −0,088 / p95 −0,053 ⇒ **la dirección de la ruptura no aporta nada** (igual o un poco peor que
tirar una moneda con el mismo stop y salida). Falla 4 de 5. El costo acá es chico (0,04R): el problema vuelve a ser
el bruto. Coherente con P2 (Donchian D1) y con todo lo de ruptura: **en FX 2020-26 las rupturas no siguen, ni
intradía ni en D1, con o sin compresión previa.** Cerrado: no barrer N (NR4, NR10), salida ni stop. Reservados no
mirados. Arnés con control positivo (P0) ⇒ el NO PASA vale.

### 23 Oct 2026 — P12 drift pre-FOMC en USTEC/US30: NO PASA (`tools/backtest_p12_pre_fomc.py`)

Criterio `docs/p12_pre_fomc_criterio.md` (`c1671b6`). Largo 14:00 ET del día anterior → 13:45 ET del comunicado,
51 reuniones programadas 2020-06 → 2026-09, spread de entrada y salida + 0,02% de financiación.

| | n | media neta | mediana | ganados | misma ventana en días normales | control p95 |
|---|---|---|---|---|---|---|
| USTEC | 51 | +0,290% | +0,233% | 61% | +0,045% | +0,347% |
| US30 | 51 | +0,058% | +0,113% | 65% | +0,037% | +0,253% |
| DE40 (desc.) | 50 | +0,271% | +0,139% | 60% | +0,014% | +0,267% |

Pool USTEC+US30: +0,174%, CI [+0,012, +0,342], mitades +0,28 / +0,07 ⇒ pasa 4 de 5 y **falla el control**: con 51
eventos, un día cualquiera de índice se mueve ~1% y la media de 51 días al azar llega a +0,35% por pura varianza.
**Ojo con el CI:** el pool cuenta como independientes USTEC y US30 del MISMO evento (correlación alta) ⇒ el CI
real es más ancho de lo que dice. La 2da mitad es más floja (el efecto se debilitó, como dice la literatura).
Cerrado: no barrer ventanas ni instrumentos.

### 23 Oct 2026 — P6 pico de tick_volume como filtro de `structure` M15: NO PASA (`tools/backtest_p6_volumen.py`)

Criterio `docs/p6_volumen_criterio.md` (`270287f` + enmienda 1 antes de medir: 15 pares con checkpoint de Fase 2).
Sobre las 3.059.991 señales de Fase 2 (london): pico (`vol_ratio ≥ 1,5`, 23% de las señales) n=713.713, **neto
−0,82p**, CI [−0,88, −0,79], 0/15 pares positivos; todas las señales −0,96p. Terciles de volumen: bajo −1,16 ·
medio −0,91 · alto −0,82. **El volumen SÍ elige mejor que el azar** (+0,13p sobre subconjuntos al azar, le gana al
p95) pero no saca a `structure` de la pérdida. Cerrado.

### 23 Oct 2026 — P13 A1 como opción binaria: PASA el criterio, pero el diagnóstico lo desarma (`tools/backtest_p13_a1_binaria.py`)

Origen: el user preguntó por otro broker (IQ Option). Exploratorio en muestra (20 pares): A1 acierta 54,3% a 15 min
(n=522.531). Criterio `docs/p13_a1_binaria_criterio.md` (`0a752de`) declarado antes de mirar los reservados.
**Resultado en los 6 reservados, H3 (15 min):** n=193.306, **acierto 54,44%, CI [54,22; 54,66]**, mitades 55,1 /
53,8, 6/6 pares > 52,6% ⇒ **PASA FUERTE** según el criterio (EV por $1: +0,007 con payout 85%, +0,034 con 90%).

**Diagnóstico adversarial (después, misma data):**

| Subconjunto | 20 pares | reservados |
|---|---|---|
| Todo | 54,3% | 54,4% |
| Compras / ventas | 55,2 / 53,5 | 55,3 / 53,6 |
| **Solo rollover (23-01 server)** | **68,0%** | **67,3%** |
| Sin rollover | 53,2% | 53,2% |
| Spread de la vela > mediana / ≤ mediana | 57,2 / 53,1 | 56,5 / 53,0 |
| **Horario 10-19 server y spread normal** | **52,6%** | **52,1%** |
| Entrando 5 min tarde | 52,3% | 52,2% |

Lectura: buena parte del acierto es **artefacto del bid de MT5** (el spread se abre, el bid se hunde y "rebota"
sin que el precio medio se mueva), concentrado en el rollover y en velas de spread ancho, con la asimetría
compras > ventas típica del artefacto. En una plataforma de binarias, que cotiza su propio precio medio, eso no se
cobra. **La parte operable (horario líquido, spread normal) acierta 52,1-52,6% ⇒ empata con payout 90% y pierde
con 85%.** Falla mía de especificación: el criterio debió excluir el rollover y el spread ancho desde el principio
(lección de Fase 4, que ya había visto el spread del rollover). **No se propone shadow.** Cerrado: no barrer
horarios ni umbrales.

### 23 Oct 2026 — P11 carry + tendencia semanal: NO PASA (`tools/backtest_p11_carry.py`)

Criterio `docs/p11_carry_criterio.md` (`66101d4`). Tasas de política a fin de mes 2019-11 → 2026-09 armadas con
fuentes de los bancos centrales (`docs/p11_policy_rates.csv`), swap histórico = teórico − recargo del broker
calibrado contra el swap real del spec (sale 0,2-0,5 pip/noche, razonable). 20 pares, rebalanceo semanal.

| Variante | posiciones-semana | media semanal | precio | swap | costo |
|---|---|---|---|---|---|
| **Carry + tendencia (principal)** | 2.042 | **+0,004%** | +0,008 | +0,019 | 0,004 |
| Carry solo (desc.) | 3.874 | +0,037% | +0,024 | +0,018 | 0,000 |
| Tendencia sola (desc.) | 5.404 | −0,051% | −0,025 | −0,020 | 0,004 |

Principal: CI [−0,088, +0,097], mitades +0,008 / −0,001, 11/20 pares, control p95 +0,021 ⇒ falla 4 de 5. La
tendencia le RESTA al carry (coherente con P2). Lo ganado en los 20 pares viene de los cruces con yen (USDJPY
+28,8%, GBPJPY +29,2%, EURJPY +19,5%, AUDJPY +16,9%): el desplome del yen 2021-24.

### 23 Oct 2026 — P14 carry solo, SOLO 6 reservados: NO PASA (`tools/backtest_p14_carry_solo.py`)

Criterio `docs/p14_carry_solo_criterio.md` (`4d73183`), una sola corrida. 1.388 posiciones-semana, **media
+0,001%/semana**, CI [−0,077, +0,080], mitades −0,037 / +0,039, control p95 +0,042 ⇒ falla 3 de 4. El swap cobra
(+0,019%/semana) y el precio se lo come (−0,022%): NZDJPY +25% (el yen otra vez), CHFJPY −13%, NZDCHF −9%, NZDCAD
−12%. **Cerrado el carry en FX sobre esta data:** el carry de 2020-26 fue el yen, no un premio general.

### 23 Oct 2026 — P13b: shadow en vivo de A1 como binaria (pedido del user)

Criterio `docs/p13b_shadow_binaria_criterio.md` (`0aa3233`, antes de juntar). Mide lo que el backtest no puede:
el acierto sobre el precio de una plataforma de binarias (sin el artefacto del bid de MT5) y el payout real.
Plataforma **Deriv** (API oficial, demo gratis); IQ Option descartada por no tener API oficial. Verificado: las
velas y ticks de forex de Deriv se leen sin cuenta; las cotizaciones exigen un `app_id` propio (el público 1089
responde "This trade is temporarily unavailable"). Tarea `aidan-shadow-binaria` lun-vie desde el 26-oct, 10 pares,
07-16 UTC, base propia. Gate: n≥400, CI inferior del acierto > break-even del payout real (provisorio contra 52,6%
mientras no haya `DERIV_APP_ID`); a n≥800 sin pasar se apaga.

### 23 Oct 2026 — búsqueda de ideas fuera de FX (pedido del user: "buscá qué hicieron otros, una tiene que funcionar")

Criterio de selección: que la ganancia venga de **alguien que paga un premio** (funding, seguro de volatilidad,
información que se difunde lento, sesgo de apostadores) y no de adivinar la dirección del precio, que es lo que
20 pruebas refutaron en FX. Y que haya data pública para medirla con el mismo método (criterio antes, control,
reservados) y demo/testnet para el shadow. Entran P15-P18.

Lo que se encontró de "agentes que ganan solos": la competencia con plata real Alpha Arena (Nof1, oct-nov 2025,
cripto en Hyperliquid) duró ~2 semanas; Qwen3 Max terminó con $12.231 y GPT-5 con $4.126 partiendo del mismo monto
⇒ resultados de 2 semanas con n chico, más cerca de la suerte que de una estrategia. Un estudio on-chain de 95 M
de transacciones de Polymarket (abr-2024 → dic-2025) reporta que solo el 0,51% de las billeteras ganó más de
$1.000. Los videos de agentes ganando muestran a los que ganaron, no a los que perdieron.

### 23 Oct 2026 — P15 carry de funding en cripto: PASA, también fuera de muestra (`tools/backtest_p15_funding.py`)

Criterio `docs/p15_funding_criterio.md` (`748e62f` + enmienda 1 `por bug del tool`, declarada). Datos públicos de
Binance (funding + velas de 8 h de spot y perpetuo), 2019-09 → 2026-10-22. Spot comprado + perpetuo vendido cuando
la media de 7 días del funding ≥ 0,005%/8 h, salida si < 0; capital = 2 × nocional; costo 0,38% por ida y vuelta;
rebalanceo a ±50%.

**Bug encontrado y corregido antes de reportar:** la 1ra corrida daba +13,8%/año, pero "siempre adentro" en DOGE
daba +1.797% (imposible si es neutral): el rebalanceo no reseteaba el nocional y el funding crecía con la suba de
la moneda. Corregido según el criterio (rebalanceo = cerrar y reabrir); reglas y umbrales sin cambio.

| | anual sobre capital | CI95 | mitades | caída máx | monedas > 0 | tasa libre media |
|---|---|---|---|---|---|---|
| **6 principales (decide)** | **+4,81%** | [+3,77, +6,00] | +7,2 / +2,4 | 1,18% | 6/6 | 2,87% |
| **4 reservados (fuera de muestra)** | **+5,79%** | [+4,53, +7,29] | +8,9 / +2,6 | 0,52% | 4/4 | 2,90% |

Por año (principales): 2020 +7,4% · **2021 +17,6%** · 2022 −0,1% · 2023 +2,9% · 2024 +5,5% · **2025 +0,7%** ·
2026 +0,2%. La base (spot vs perpetuo) aporta ~0: todo es funding. "Siempre adentro" da parecido (+3,8%) ⇒ lo que
gana es el premio en sí, la regla de entrada aporta poco.

**Lectura honesta:** es la **primera idea de toda la línea que pasa, y pasa fuera de muestra** — porque no adivina
el precio, cobra lo que pagan los apalancados. Pero es **chica y depende del régimen**: en promedio ~2× la tasa
libre de riesgo, concentrada en el boom de 2021, y en 2025-26 quedó por DEBAJO de la tasa libre. Sobre $600 son
~$30/año. Riesgos no modelados: quiebra del exchange (las dos patas en el mismo lado) y liquidación si no se
rebalancea a tiempo. **Próximo paso según el criterio: shadow en vivo** (registrar en papel la misma regla con
datos públicos en tiempo real, o en testnet) antes de cualquier plata.

### 23 Oct 2026 — P15b rotación del carry de funding (K=3): NO PASA (`tools/backtest_p15b_rotacion.py`)

Criterio `docs/p15b_rotacion_criterio.md` (`5f1dc1f`). Control del motor antes de medir: con K=10 y sin corte de
ranking reproduce P15 exacto (diferencia máxima por período 6e-17).

| | anual | CI95 | mitades | caída máx | últimos 12 meses |
|---|---|---|---|---|---|
| **Rotación K=3** | +5,30% | [+3,84, +6,96] | +9,7 / +0,9 | 1,87% | **−0,89%** |
| P15 (una ranura por moneda), mismas 10 | +5,09% | | | | +0,11% |
| **Diferencia** | **+0,21%** | **[−0,34, +0,82]** | | | |

Falla 2 de 5 (diferencia con CI que cruza cero; últimos 12 meses negativos). Por año: la rotación gana cuando el
funding es alto (2020 +12,8 vs +8,1; 2021 +21,1 vs +18,2) y pierde cuando es bajo (2023-2026), porque rota mucho
(290 entradas en 7 años, 0,38% cada ida y vuelta) persiguiendo diferencias chicas. Las 10 monedas nuevas no se
bajaron. Cerrado: no barrer K ni el corte de ranking.

### 23 Oct 2026 — P16 vender volatilidad (SVXY con VIX < VIX3M): NO PASA (`tools/backtest_p16_vol.py`)

Criterio `docs/p16_vender_volatilidad_criterio.md` (`7a3b84e`). Datos diarios públicos de Yahoo, oct-2011 →
23-oct-2026. Señal al cierre, ejecución a la apertura siguiente, 0,05% por lado. Control del motor antes de medir:
con la señal "siempre adentro" reproduce SVXY comprar y mantener (sino aborta).

| | CAGR | caída máx | Sharpe | peor mes |
|---|---|---|---|---|
| **Regla (adentro 93% del tiempo, 183 cambios)** | **+28,6%** | **55,4%** | **0,80** | −27,4% (dic-2014) |
| SVXY siempre adentro | +12,5% | 95,2% | 0,57 | |
| SPY comprar y mantener | +15,5% | 33,7% | 0,95 | |

CI de la media anual [+15,5%, +54,5%], mitades +45,5% / +13,7%. Pasa 4 de 5 y **falla el 4: más caída y peor
Sharpe que simplemente comprar el índice**. Eventos: feb-2018 regla −15% (SVXY −91%: ahí el filtro sí salvó),
mar-2020 −12% (SVXY −59%), **ago-2024 −29% (SVXY −17%: el filtro entró/salió a destiempo y empeoró)**. La mayor
parte del CAGR es 2012-2017, cuando SVXY era −1x; desde mar-2018 es −0,5x y la 2da mitad rinde +13,7% contra
~+16% de SPY. SVIX (−1x desde 2022) con la misma regla: +6,2%/año con caída de 75%.

**Lectura:** el premio existe y el filtro evita la catástrofe de 2018, pero en este período **comprar y mantener el
S&P 500 rindió casi lo mismo con menos riesgo**. Cerrado: no barrer el umbral del ratio, otros ETFs ni horarios.

### 24 Oct 2026 — P17 deriva post-resultados (PEAD) en acciones de EE.UU.: NO PASA (`tools/backtest_p17_pead.py`)

Criterio `docs/p17_pead_criterio.md` (`12256eb`). Cambio declarado ANTES de medir por falta de datos: no hay historial
gratis de la sorpresa de EPS ⇒ la sorpresa se mide por la reacción del precio al anuncio (EAR, Brandt et al. 2008),
con las fechas exactas de los 8-K ítem 2.02 de EDGAR. 400 empresas más grandes de hoy, eventos 2010 → ago-2026,
compra al cierre de d+2 si el EAR ≥ p80 de los 365 días previos, 20 días hábiles, resultado − SPY − 0,10%.

| | n | media neta | CI95 (por mes) | mitades | desde sep-2023 |
|---|---|---|---|---|---|
| **Señal (EAR ≥ p80)** | 3.582 | **+0,48%** | [+0,02, +0,92] | +0,36 / +0,60 | +0,97% (n=720) |
| Control: mismas acciones, día al azar lejos de anuncios | | +0,38% | p95 **+0,61%** | | |
| Cola opuesta (EAR ≤ p20) | 3.607 | **+0,47%** | | | |
| Todos los anuncios | 17.580 | +0,26% | | | |

Pasa 4 de 5 y **falla el 4 (no supera al azar)**. La lectura importante no es el número: **la cola de malas
sorpresas sube lo mismo que la de buenas** ⇒ no hay deriva por la sorpresa; lo que aparece es que las grandes
de HOY subieron más que SPY en cualquier momento (sesgo de supervivencia, exactamente lo que el control estaba
para neutralizar). Por año alterna signo (2011 −0,8, 2021 −0,9, 2022 −0,2). Reservados (401-700) NO mirados.
Cerrado: no barrer percentil, entrada, horizonte ni universo. Si se reabre PEAD, solo con la sorpresa de EPS real
y un universo sin supervivencia (data paga).

### 27 Oct 2026 — P19 shadow en papel del carry de funding: ARMADO (`tools/shadow_funding.py`)

Criterio `docs/p19_shadow_funding_criterio.md` (declarado antes de juntar). Libro en papel desde el 27-oct 00:00 UTC
con el motor `simulate` de P15 importado (6 principales, reglas y costos congelados), reconstruido entero desde datos
públicos de Binance en cada corrida ⇒ no depende de que la PC esté prendida. Cada corrida además guarda una foto
(bid/ask spot y perpetuo, marca, funding, decisión) en `state/funding_shadow.db`. Sin órdenes ni claves (5 tests de
frontera en `tools/test_shadow_funding_p19.py`). **1ra foto (27-oct):** medio spread spot+perpetuo mediana
**0,0045%** contra 0,02% asumido por P15 (la ejecución, por ahora, mejor que lo supuesto); BTC, ETH y XRP adentro,
SOL/BNB/DOGE afuera; decisiones foto = libro 3/3. Lectura a 90 días (~25-ene-2027), decisión a 180 (~25-abr-2027).
Tarea `aidan-shadow-funding` creada el 27-oct con OK del user (05:05/13:05/21:05 AR), probada: corrió y sumó 6 fotos.

### 28 Oct 2026 — P22 loop de hipótesis: ARMADO (`tools/hyp_loop.py`, `tools/hyp_data.py`)

Criterio `docs/p22_loop_hipotesis_criterio.md` (`59b3109`, declarado antes de medir). Datos públicos: FRED (7 monedas
diarias desde 1999, tasas a 3 meses, bonos de EE.UU., VIX, dólar amplio, WTI) y CFTC COT. Sin mirar el futuro (COT desde
el lunes siguiente, mensuales con 2 meses de retraso, cierres al día siguiente; test). **Control del arnés en cada vuelta:**
una señal que acierta el 60% pasa (+21 bps por período) y 20 de ruido persistente no pasan (0/20); con una sola moneda
hace falta ~58% de acierto semanal para pasar. Sanidad: el carry da lo que dice la literatura (+61 bps/mes hasta 2008,
~0 después).

**4 vueltas (28-oct): 31 hipótesis evaluadas, 5 rechazadas por espejo/misma familia, 0 pasan el descubrimiento.**
Vueltas 1-3: cada feature sola, en los dos sentidos (la IA exploró sola el lado contrario de lo que ya había fallado).
Vuelta 4: combinaciones de 2 fuentes en monedas puntuales (petróleo→CAD, tasas→JPY); varias quedaron con 6-17
períodos, insuficientes. Lo más cerca: carry siguiendo (+36,6 bps por 20 días, CI cruza cero, se murió en la 2da
mitad) y momentum de 250 días (+13,8). **Tarea `aidan-hyp-loop` creada con OK del user** (lun-vie 20:00, `--cycle --n 8`,
pythonw, log en `state/hyp_loop_YYYYMMDD.log`), probada desde el scheduler.

**Enmienda 1 (anti-repetición, no toca el gate):** la 5ta vuelta propuso solo 3 ideas y 2 eran variantes de familias de
una sola fuente que ya habían fallado ⇒ familia con mejor neto ≤ 0 se cierra a las 2 variantes; con todas las features
probadas solo se aceptan combinaciones o familias nuevas; si la IA propone poco válido, se le devuelven los rechazos.
**Vuelta 6: 8 combinaciones de 2 fuentes, y la primera que pasa el descubrimiento: #40** = especuladores largos en EUR
(COT z > 0,5) **y** tasa europea > EE.UU. + 0,5 ⇒ comprar EUR 10 días: n=63, **+70 bps por período, CI [+21, +111]**,
las dos mitades positivas (+100 / +42), azar p95 +29. **Falló la reserva con n=0**: entre 2015 y hoy la tasa europea nunca
superó a la de EE.UU. por 0,5 ⇒ no está refutada, es una idea **dormida** (sin datos nuevos para probarla); por criterio
cuenta como `falló_B` y gastó la 1ra mirada a la reserva (k=1). Si el régimen vuelve, se puede re-declarar como idea nueva.

### 28 Oct 2026 — P18 favorito-longshot en Kalshi: NO PASA (`tools/backtest_p18_kalshi.py`)

Criterio declarado antes (`docs/p18_favorito_longshot_criterio.md`, `a6dfe45`). Kalshi en vez de Polymarket (no
resuelve DNS desde esta red). 40 series principales por volumen, mercados liquidados oct-2025 → ago-2026, entrada 6 h
antes del cierre programado al ask real (vela de 1 h con bid/ask), comisión taker de cada serie, una observación por
evento. 16.772 mercados con velas, 0 sin respuesta.

**Favorito [0,90-0,97] a 6 h: n=664 eventos, media neta −13,99%/apuesta, CI95 (bootstrap por semana) [−17,4, −11,1].**
Acierta 86,3% contra un precio medio de 93,1% ⇒ pierde el doble de lo que daría un precio bien calibrado (−6,6%).
Negativo en las dos mitades (−13,8 / −14,2), sin la serie más grande (−14,3) y desde junio (−13,6). Pasa solo n≥300.

Descriptivos: el longshot ≤0,10 también pierde (−20,7%, acierta 11,2% vs 6,7% del precio ⇒ los longshots están
**sub**pagados, al revés del sesgo clásico); a 1 h (−7,7%) y 24 h (−12,7%) igual; deportes −15,1%, cripto −7,1%.
La calibración del SÍ es monótona y comprime hacia el medio: lo barato acierta más que su precio y lo caro menos.

**Cerrado: favorito-longshot en Kalshi con esta definición. No barrer tramo de precio, horizonte ni universo.**
*Lectura:* la compresión hacia el medio es lo que pagaría comprar barato, pero el longshot igual pierde por spread y
comisión ⇒ tampoco hay un "al revés" rentable que proponer. Reservadas (41-100) no miradas.

### 30 Oct 2026 — P20 cash-and-carry con futuros trimestrales: NO PASA (`tools/backtest_p20_cash_carry.py`)

Criterio `docs/p20_cash_and_carry_criterio.md` (`18706b2`, + enmienda 1 por un bug de datos, declarada abajo).
Binance USDT-M trimestrales de BTC y ETH (feb-2021 → 29-oct-2026, 2.094 días): spot comprado + trimestral vendido
cuando la base pactada neta anualizada supera la tasa libre, hasta el vencimiento; costo 0,38% por ida y vuelta,
capital 2 × nocional.

| | anual sobre capital | CI95 | mitades | caída máx | monedas > 0 | tasa libre media |
|---|---|---|---|---|---|---|
| **BTC+ETH** | **+2,81%** | [+0,84, +5,50] | +2,2 / +3,4 | 4,6% | 2/2 | **3,40%** |

Por año: 2021 +3,8% (rf 0,1%) · 2022 +1,8% (1,9%) · 2023 +0,9% (5,1%) · **2024 +6,9% (5,1%)** · 2025 +2,8% (4,2%) ·
2026 +0,4% (3,7%). BTC 19 trades (0 forzadas, 74% del tiempo adentro), ETH 17 (2 salidas forzadas por suba ≥80%
en 2021). Falla solo el criterio 1, pero es el que importa: **rinde menos que dejar la plata en la tasa libre**, y
en 2025-26 (la razón de P20) también queda debajo. Fijar la base no ayuda si la base misma se achicó: el premio
de apalancamiento cayó para el funding y para los trimestrales a la vez.

**Enmienda 1 (bug de datos, antes de reportar):** la serie continua `NEXT_QUARTER` repite el último precio los días
en que el contrato siguiente no cotiza (~505 días por moneda, p.ej. 56.774,5 del 27-mar al 15-abr-2021). Se descarta
un open idéntico al del día anterior. **No cambió ningún trade ni el resultado** (+2,81% antes y después).

**Cerrado:** cash-and-carry trimestral sobre esta data; no se barren umbral, días mínimos ni contrato. Con P15
(funding) cayendo igual, la línea de "premio de apalancamiento cripto" depende de que vuelva un mercado como 2021;
el shadow P19 es lo que lo va a mostrar.

### 31 Oct 2026 — P21 carry de funding en Hyperliquid: A PASA (también fuera de muestra), B NO PASA (`tools/backtest_p21_hyperliquid.py`)

Criterio `docs/p21_hyperliquid_criterio.md` (`edc1715`), motor `simulate` de P15 importado (solo cambia el costo).
Período 2023-05-12 → 2026-10-22 (el funding de Hyperliquid empieza ahí). Data verificada: ~2% de horas faltantes,
0 duplicados. El funding de Hyperliquid promedia **~2× el de Binance** (BTC 0,0129% vs 0,0066% por 8 h): la mitad de
las horas está exactamente en el piso de interés (0,00125%/h = 0,01%/8 h) y en Binance ese piso se perdió en 2025.

| | anual s/capital | CI95 | mitades | caída máx | monedas > 0 | tasa libre |
|---|---|---|---|---|---|---|
| **A: spot Binance + perp vendido en HL (decide)** | **+6,25%** | [+4,94, +7,83] | +10,2 / +2,3 | 0,39% | 6/6 | 4,58% |
| A reservados (fuera de muestra) | **+6,18%** | [+4,62, +8,00] | +9,3 / +3,1 | 0,46% | 4/4 | 4,58% |
| B: diferencial (perp BN comprado + perp HL vendido) | +3,27% | [+2,50, +4,17] | +5,5 / +1,1 | 0,16% | 6/6 | 4,58% |
| P15 Binance, mismo período (desc.) | +2,42% | [+1,77, +3,19] | +4,4 / +0,5 | 0,37% | 6/6 | |

Por año (A, principales): 2023 +8,1% · 2024 +11,9% · **2025 +3,4% · 2026 +1,4%**. "Siempre adentro" da lo mismo
(+6,1%) ⇒ otra vez la regla de entrada aporta poco: lo que paga es el premio.

**Lectura honesta:** pasa los 5 criterios y fuera de muestra, y **le gana a Binance en todos los años** — Hyperliquid
paga más. Pero tiene el mismo problema que P15, más suave: **la 2da mitad (+2,3%) y 2025-26 quedan por debajo de la
tasa libre** (~4%). Sobre $600 son ~$37/año en promedio, ~$10/año al ritmo de 2026. Riesgos no modelados: dos
exchanges (Binance + Hyperliquid, puente USDC) y deslizamiento on-chain en monedas chicas. **Cerrado B** (diferencial
BN-HL) sobre esta data. **Próximo paso según el criterio: shadow en papel** como P19 (el user decide si se arma la
tarea; ver la propuesta en el reporte de la rutina del 31-oct).

### 28 Oct 2026 — P21 broker más barato: NO PASA (`tools/backtest_p21_broker.py`)

Criterio `docs/p21_broker_barato_criterio.md` (`d401247`). Costos verificados: **Fusion Zero USD 4,50** ida y vuelta (el
más barato), IC USD 7, Pepperstone ~7, FP Markets ~6; Interactive Brokers 0,2 pb pero mínimo USD 25.000 por orden ⇒ no
sirve para esta cuenta. **Escritorio** (comisión × 0,643, mismo spread y swap): A1 20 pares M5 −0,40 a −0,71 pips ·
lead-lag −0,42 · rango asiático −0,018 R · fixing −0,20 ⇒ cerrados. Solo **A1 en EUR/USD M15** da positivo (+0,08).
**Re-medición por el arnés de P9:** A1 en EUR/USD con Fusion = **+0,08 pips/operación, CI [−0,59, +0,74]** (H16, n=4.693;
mitades +0,09/+0,06, por encima del azar) ⇒ indistinguible de cero, y con lote 0,01 son <1 centavo por operación. Pool
oro+índices con Fusion: NO PASA igual que en P9 (CI cruza cero). **Conclusión: el costo no es lo único que falta; la
ventaja bruta de lo medido es demasiado chica para cualquier broker minorista.** Lo único de ejecución que queda sin
medir es entrar con orden límite (P23).

### 3 Nov 2026 — P23 A1 en EUR/USD con entrada límite: NO PASA (`tools/backtest_p23_a1_limite.py`)

Criterio `docs/p23_a1_limite_criterio.md` (`720f8ff`). Velas M1 de MT5 (desde el 23-jun-2021: MT5 no da M1 más viejo;
el período arranca 9 meses después que P21). Sanidad: la misma señal a mercado da **+0,10p por señal** con Fusion,
igual que el +0,08 de P21.

| variante (Fusion) | llenadas | neto llenadas | CI95 | x señal límite | x señal mercado | mercado: llenadas / no llenadas |
|---|---|---|---|---|---|---|
| **0,25σ, 30 min (decide)** | 3.688 (79%) | **−0,43p** | [−1,18, +0,32] | −0,34 | +0,10 | **−1,75 / +6,95** |
| 0 σ, 30 min | 4.040 (94%) | −0,33 | [−1,04, +0,39] | −0,31 | +0,07 | −0,37 / +7,39 |
| 0,5σ, 30 min | 3.340 (66%) | −0,62 | [−1,42, +0,18] | −0,41 | +0,03 | −3,14 / +6,12 |
| 0,25σ, 15 / 60 min | | −0,59 / −0,53 | | | | |

Control al azar (misma mecánica): mediana −0,80, p95 −0,17. Falla 4 de 5 (pasa solo n). **La lectura es de libro:
selección adversa.** El límite se llena cuando el precio sigue en contra (esas, a mercado, hubieran dado −1,75p) y
se pierde las que revierten enseguida (+6,95p). Mejorar el precio de entrada no compensa quedarse sin las buenas; cuanto
más lejos el límite, peor. **Cerrado:** A1 en EUR/USD por el lado de la ejecución (no se barren offset ni vida). Con
esto A1 queda cerrado en instrumento, broker y entrada; solo sigue el shadow P13b (binaria en vivo). Próxima: P24.

### 4 Nov 2026 — P19 enmienda 1: libro Hyperliquid (P21-A) sumado al shadow de funding

Con OK del user. Criterio en `docs/p19_shadow_funding_criterio.md` (enmienda 1, declarada con el libro en 0 períodos).
Mismo motor y reglas de P15; perpetuo vendido en Hyperliquid, spot en Binance, costo 0,37%. Desde el 4-nov 00:00 UTC;
lectura 2-feb-2027, decisión 3-may-2027. Misma tarea `aidan-shadow-funding`, misma base (columna `venue` nueva; las
150 filas previas quedaron como `binance`). 1ra foto: 6/6 monedas, medio spread spot+perpetuo mediana 0,006% (asumido
0,02%). Frontera: solo lectura por `/info`, 4 tipos permitidos, sin claves (7 tests).

### 4 Nov 2026 — P27 juez LLM (gpt-oss-20b local) sobre 299 trades reales: NO PASA (`tools/backtest_p27_llm_judge.py`)

Criterio `docs/p27_llm_judge_criterio.md` (`9bf204f`). Velas D1→M5 relativas, sin fechas ni etiquetas de AIdan.

| | n | veto | TAKE $/trade | VETO $/trade | diferencia | CI95 | mitades |
|---|---|---|---|---|---|---|---|
| **juez** | 299 | 56% | −0,58 | −0,42 | **−0,16** | [−0,94, +0,65] | −0,37 / +0,18 |
| placebo (velas de otro trade) | 300 | 65% | −0,42 | −0,53 | +0,10 | [−0,69, +0,94] | +0,13 / +0,06 |

Falla 3, 4 y 5. Lo que aprueba pierde igual que lo que veta, y con las velas equivocadas separa igual: **el gráfico no
le da información útil al juez**. Ojo con el número engañoso: seguir al juez habría perdido −$76 en vez de −$146, pero
solo porque opera la mitad; el placebo, con velas al azar, habría perdido −$45. Menos trades = menos pérdida, no juicio.
A los 37 trades parecía separar (+$1,95 vs −$0,11) y a los 56 ya no: ruido, como estaba advertido. **Cerrado:** no se
barren modelo, prompt ni temporalidades sobre estos trades. P27b (calendario) y P27c (memoria) se leen al terminar.

### 4 Nov 2026 — P29 screen de información: casi nada tiene información de dirección; la volatilidad sí (`tools/info_screen.py`)

Criterio `docs/p29_info_screen_criterio.md` (`07ee73e`). 138 celdas de dirección + 33 de riesgo; descubrimiento 70% /
reserva 30%; placebo por corrimiento circular; costo real por instrumento. Calibración OK: la reversión 2σ en EURUSD
(A1) muestra información y falla el costo, igual que Fase 3b; el control positivo sintético pasa (test).

- **Dirección: 18 celdas con información fuera de muestra, 1 pasa el costo.** En FX la información existe (reversión de
  corto plazo, hora del día a 1 h) pero es **0,1-0,5 bps brutos contra 0,8-1,8 bps de costo**: el costo es 3-10 veces la
  ventaja. Cripto: nada (costo 10 bps). Lead-lag de USTEC a FX/oro: nada.
- **La que pasa: DE40, hora del día, a 4 h:** neto +3,47 bps, CI [+0,72, +6,40], reserva desde oct-2024. Comprar en las
  horas de servidor 05-08 y 20 rinde +5,65 bps más que estar siempre comprado ⇒ no es solo la suba del índice. Con 138
  celdas, 1 que pase puede ser azar ⇒ **P30** (índices europeos nunca mirados).
- **Riesgo: la volatilidad es predecible en 30 de 33 celdas** (IC 0,15-0,44, todos los instrumentos). Es la única
  información sólida del gráfico: no dice para dónde, dice cuánto ⇒ **P31**.
- **Lectura:** en FX con esta cuenta el problema es el costo frente a una ventaja minúscula; en índices el costo es
  4-6 veces menor y ahí aparece lo único que pasa.

### 4 Nov 2026 — P31 movimiento esperado vs costo en los trades de AIdan: NO PASA (`tools/backtest_p31_vol_cost.py`)

Criterio `docs/p31_vol_costo_criterio.md` (`e6db49f`). 737 trades reales (20-abr → 9-oct), rango medio de las 16 velas
M15 previas; corte del tercio bajo en la 1ra mitad = 6,11 pips. 2da mitad: tercio bajo **−$0,84/trade** (n=172) vs resto
**−$0,39** (n=197); diferencia −0,45, CI [−1,18, +0,26], placebo p5 −0,57 ⇒ falla 2 y 5. Misma dirección en la 1ra mitad
(−1,20 vs −0,91). Sacar el tercio bajo habría dejado la 2da mitad en −$76 en vez de −$220, pero **el resto sigue
perdiendo**: el filtro achica la pérdida (sobre todo por operar menos), no da vuelta el resultado. Descriptivo: en m15 el
resto queda en +$0,05/trade (coherente con el piso de ATR que ya tiene). **Cerrado** sobre estos trades.

### 4 Nov 2026 — P27b (juez + calendario) y P27c (juez + memoria): NO PASAN

Mismo criterio (`docs/p27_llm_judge_criterio.md`, secciones P27b y P27c, declaradas antes de ver resultados).
- **P27b** (n=282): aprobadas −$0,45 vs vetadas −$0,53 por trade, diferencia +0,08 CI [−0,73, +0,90]; aporte sobre P27
  +0,16 CI [−0,87, +1,09]. Cerca de un evento alto (n=19) veta más, pero separa peor que sin calendario.
- **P27c** (n=260 con ≥20 previos): aprobadas −$0,50 vs vetadas −$0,37; aporte de la memoria −0,14 CI [−1,15, +0,85];
  no mejora con el tiempo (1er tercio −0,55, último −0,20).
- **Cerrado:** juez LLM sobre las señales de AIdan, con velas, calendario o memoria. **P28 no se arma** (era condicional).
  Confirma P29/P31: las señales de AIdan no traen nada que un filtro pueda aprovechar.

### 5 Nov 2026 — P24 prima nocturna en índices: NO PASA (`tools/backtest_p24_prima_nocturna.py`)

Criterio `docs/p24_prima_nocturna_criterio.md` (`f55821a`). Largo del cierre del contado a la apertura siguiente,
mayo-2020 → oct-2026, swap ACTUAL de MT5 (~0,027% del precio por noche en US30/USTEC, triple el viernes; cota alta
para 2020-22).

| | n | neto/noche | bruto | con 1/2 swap | intradía | control p95 |
|---|---|---|---|---|---|---|
| US30 | 1583 | −0,014% | +0,030% | +0,005% | +0,017% | +0,011% |
| USTEC | 1582 | +0,002% | +0,056% | +0,021% | +0,015% | +0,035% |
| DE40 (desc.) | 1649 | −0,005% | +0,037% | +0,011% | +0,011% | +0,005% |

Pool US30+USTEC: −0,006%/noche, CI [−0,031, +0,019], mitades −0,026 / +0,014 ⇒ falla 2, 3, 4 y 5.
- **La noche sí rinde algo en bruto** (+0,03 a +0,06%), un poco más que el intradía, como dice el paper.
- **Pero el CFD cobra justo eso:** el swap por noche es del mismo tamaño que el premio. Con medio swap (tasas de
  2020-22) queda apenas positivo y sin significancia.
- **Y la ventana no es especial:** una ventana al azar de la misma duración da casi lo mismo (control p50 −0,009 /
  +0,007) ⇒ lo que hay es la deriva alcista 2020-26, no un premio de la noche.
- **Cerrado** prima nocturna con CFDs de índices. No buscar otra hora de entrada o salida.

### 6 Nov 2026 — P25 cambio de mes en índices: NO PASA (`tools/backtest_p25_cambio_de_mes.py`)

Criterio `docs/p25_cambio_de_mes_criterio.md` (`ec547c9`). Largo del cierre del contado del último día hábil del
mes al cierre del 3er día hábil del siguiente, may/jun-2020 → oct-2026, swap ACTUAL de MT5 (cota alta 2020-22).
US500 no estaba en el cache (habría hecho falta MT5) y quedó afuera, declarado antes de medir.

| | n | neto/evento | bruto | con 1/2 swap | ganados | control p50 | control p95 |
|---|---|---|---|---|---|---|---|
| US30 | 76 | +0,248% | +0,387% | +0,314% | 55% | −0,032% | +0,283% |
| USTEC | 76 | +0,214% | +0,368% | +0,281% | 54% | +0,071% | +0,520% |
| DE40 (desc.) | 78 | +0,339% | +0,459% | +0,393% | 55% | +0,017% | +0,361% |

Pool US30+USTEC: +0,231%/evento, CI [−0,130, +0,580], mitades +0,311 / +0,151 ⇒ falla 2 y 4.
- **Va en la dirección del paper:** en bruto la ventana sube ~0,38% contra ~0 de 3 días al azar del mismo año, en
  los tres índices y en las dos mitades. Es lo más parecido a un flujo real que dio la línea de índices.
- **Pero con un evento por mes es ruido:** 76 meses no alcanzan para separarlo del azar (CI cruza cero; US30 queda
  apenas debajo del p95 del control y USTEC lejos). Además el pool cuenta US30 y USTEC como independientes y se
  mueven juntos ⇒ el CI real es todavía más ancho.
- **El swap le saca ~0,15 por evento** (4-5 noches), casi la mitad del premio.
- **Cerrado** cambio de mes en CFDs de índices con este costo. No buscar otra ventana ni otro día de entrada.
  Lo que queda abierto, sin poder medirlo acá: en un instrumento sin swap (futuros) el bruto sería el número que
  importa, y tampoco alcanzaría significancia con esta muestra. Próxima: P26 (valor PPP en FX).

### 7 Nov 2026 — P26 valor en FX (REER vs media de 5 años): NO PASA (`tools/backtest_p26_valor.py`)

Criterio `docs/p26_valor_ppp_criterio.md` (`08d0da5`). REER amplio del BIS (FRED), 7 monedas contra USD, largo las
2 más baratas y corto las 2 más caras, mensual, exceso de retorno con diferencial de tasas a 3 meses, REER de t−2.
La muestra arranca en **2002-04 y no en 1999**: las tasas a 3 meses de FRED no cubren las 7 monedas antes (límite de
data, no elegido después de mirar). Selftest: control positivo (señal = retorno futuro) +3,9%/mes y señal causal.

| | n | media/mes neta | anual | Sharpe | caída máx |
|---|---|---|---|---|---|
| Completa 2002-04 → 2026-07 | 292 | −0,049% | −0,58% | −0,07 | −45% |
| Descubrimiento → 2014 | 153 | −0,115% | −1,38% | −0,14 | −45% |
| Reserva 2015 → | 139 | +0,024% | +0,29% | +0,04 | −24% |

Criterios: 1 ✅ · 2 ❌ (CI [−0,56, +0,42]) · 3 ✅ (apenas) · 4 ❌ (control al azar p50 −0,02%, p95 +0,18%) · 5 ❌.
- **Descriptivo:** solo precio +0,55%/año (≈0); con REER de t−4 −0,14%/año; carry 2 contra 2 con las mismas
  monedas +3,1%/año y **correlación −0,29 con valor** ⇒ las monedas "baratas" en REER son las de tasa baja (JPY, CHF):
  el valor paga el carry en contra. Años buenos solo en crisis (2008-09, 2016).
- **Cerrado** valor REER 5 años en G8 con esta regla. No buscar otra ventana, otro número de patas ni otro rezago.
  Con esto los tres premios clásicos del FX (carry, momentum, valor) quedaron medidos acá y ninguno paga con
  esta data. Próxima: P30 (estacionalidad horaria en STOXX50/F40/UK100; velas ya bajadas). Entra P34 (Gotobi).

### 9 Nov 2026 — P30 hora del día en índices europeos, fuera de muestra: NO PASA (`tools/backtest_p30_hora_europa.py`)

Criterio `docs/p30_hora_indices_europa_criterio.md` (`505347c`). Mapa de horas de DE40 congelado del descubrimiento de
P29 (compra horas servidor 5, 7, 8, 10, 20; vende 1-3, 22, 23), aplicado tal cual a STOXX50 y F40 entre 2017 y abr-2020,
fechas anteriores a la primera vela de DE40 que tenemos.

| inst | n | IC (placebo p95) | bruto | spread | swap | neto bps | CI | exceso vs siempre largo |
|---|---|---|---|---|---|---|---|---|
| STOXX50 | 503 | +0,011 (0,031) | +0,29 | 4,64 | 2,56 | **−6,92** | [−15,7, +2,4] | +1,8 (CI cruza) |
| F40 | 621 | −0,015 (0,027) | −2,45 | 1,86 | 2,04 | **−6,35** | [−13,7, +0,9] | +0,5 (CI cruza) |

- **Sin información:** el mapa de DE40 no anticipa nada en otros índices ni en otras fechas (IC ~0, bajo el placebo);
  sin swap también pierde (−4,3 bps en los dos). Falla 2, 3 y 4 en los dos índices.
- **Secundario (70/30 propio, como P29):** ninguna celda pasa en STOXX50, F40 ni UK100. UK100 a 1 h muestra algo de
  información pero el costo es 3 veces más grande. Lo único que se repite son las horas de compra 5-8 de servidor (la
  mañana europea antes de la apertura) en los cuatro índices, y no alcanza para pagar el costo.
- **Cerrado** hora del día en índices europeos. El pase de DE40 en P29 queda como el azar esperable de 138 celdas ⇒
  **de P29 no queda ninguna señal de dirección en pie**. Entra P35 (demanda de cobertura al cierre de EE.UU.).

### 10 Nov 2026 — P32 semana del vencimiento trimestral en índices: NO PASA (`tools/backtest_p32_vencimiento.py`)

Criterio `docs/p32_vencimiento_trimestral_criterio.md` (`66c15c4`). Largo del cierre del contado 5 días hábiles antes
del 3er viernes de mar/jun/sep/dic al cierre de ese viernes, may-2020 → oct-2026, swap ACTUAL de MT5 (cota alta).

| inst | n | neto % | bruto % | ganadores | control p50 / p95 | semana siguiente (bruto) |
|---|---|---|---|---|---|---|
| US30 | 26 | **−0,49** | −0,29 | 38% | +0,13 / +0,79 | +0,35 |
| USTEC | 26 | +0,18 | +0,39 | 54% | +0,26 / +1,24 | +0,34 |
| DE40 (desc.) | 26 | −0,40 | −0,23 | 42% | +0,25 / +1,00 | −0,13 |

- Pool US30+USTEC n=52: **−0,15%/evento, CI [−0,85, +0,58]**, mitades −0,35 / +0,04. Criterios: 1 ✅ · 2 ❌ · 3 ❌ · 4 ❌ · 5 ❌.
- La semana del vencimiento rinde **menos** que una semana cualquiera del mismo año (debajo de la mediana del control
  en los tres índices) y la semana siguiente **sube**, al revés de la hipótesis. Con n=26 la potencia era baja (declarado),
  pero ni el signo acompaña.
- **Cerrado** vencimiento trimestral en CFDs de índices. No probar el mensual ni la semana siguiente como estrategia.
  Próxima: P33 (pre-feriado en EE.UU.; data ya bajada). Entra P36 (flujos de los ETF de bitcoin).

### 11 Nov 2026 — P33 día pre-feriado en índices de EE.UU.: NO PASA (`tools/backtest_p33_pre_feriado.py`)

Criterio `docs/p33_pre_feriado_criterio.md` (`20f0527`). Largo del cierre del contado del día hábil anterior al
cierre del último día hábil antes de un feriado de la NYSE (12:45 ET si cierra temprano), jul-2020 → sep-2026,
feriados calculados por regla (selftest contra fechas conocidas), swap ACTUAL de MT5 (cota alta).

| inst | n | neto % | bruto % | ganadores | sin cierres tempranos | control media / p95 |
|---|---|---|---|---|---|---|
| US30 | 60 | +0,03 | +0,06 | 48% | −0,01 (n=53) | +0,01 / +0,23 |
| USTEC | 60 | +0,17 | +0,22 | 62% | +0,14 (n=53) | −0,02 / +0,30 |

- Por evento (promedio de los dos índices, una observación por feriado) n=60: **+0,10%, CI [−0,07, +0,28]**,
  53% ganados, mitades +0,15 / +0,05. Criterios: 1 ✅ · 2 ❌ · 3 ✅ · 4 ❌ · 5 ✅.
- **US30 no muestra nada** (igual que un día cualquiera). USTEC va en la dirección del paper pero queda adentro de
  lo que da el azar con 60 días (debajo del p95 del control), y la segunda mitad es más floja que la primera.
- El costo no fue el problema esta vez (una noche de swap ≈ 0,03-0,05): **el bruto ya es chico**. El efecto del
  paper (varias veces un día normal) no aparece en 2020-26.
- **Cerrado** pre-feriado en CFDs de índices. No buscar otra ventana ni un subconjunto de feriados. Con esto las
  cuatro anomalías de calendario de índices (noche, cambio de mes, vencimiento, pre-feriado) quedan sin pasar.
  Próxima: P34 (Gotobi en USD/JPY; data ya bajada). Entra P37 (emisión de stablecoins → BTC).

### 11 Nov 2026 — P34 Gotobi en USD/JPY: NO PASA (`tools/backtest_p34_gotobi.py`)

Criterio `docs/p34_gotobi_criterio.md` (`84834f6`). Largo USDJPY 00:00 → 00:55 UTC (hasta el fixing de Tokio) los
días 5/10/15/20/25/fin de mes, dic-2019 → ago-2026, comisión real + spread mínimo de la vela.

- n=478: **bruto +0,85p, neto −0,29p**, CI [−1,94, +1,39], 51% ganados, mitades +0,40 / −0,97, pesimista −0,59.
  Criterios: 1 ✅ · 2 ❌ · 3 ❌ · 4 ❌ · 5 ❌.
- **La misma ventana sube igual los días que NO son gotobi** (+0,97p bruto, control p95 +1,36): no hay nada especial
  en el día de pago, es la hora (y la suba del dólar 2020-23). Bruto por año: positivo 2020-23, **negativo 2024-26**
  ⇒ el efecto del paper, si existió, ya está arbitrado.
- Descriptivo (no decide): el corto 00:55 → 03:00 da +2,68p neto, 52% ganados. Sin control todavía ⇒ entra como P38
  solo en pares con yen nunca mirados.
- **Cerrado** Gotobi en USDJPY. No probar otra ventana ni subconjuntos de días. Próxima: P35 (cobertura al cierre de EE.UU.).

### 11 Nov 2026 — P35 demanda de cobertura al cierre de EE.UU.: NO PASA (`tools/backtest_p35_cobertura_cierre.py`)

Criterio `docs/p35_cobertura_cierre_criterio.md` (`b1150ca`). Si el retorno del cierre anterior a las 15:30 ET cae en
el quintil extremo del descubrimiento, seguir esa dirección de 15:30 a 16:00 ET; may-2020 → oct-2026.

| inst | días | n desc | neto desc bps | n reserva | neto reserva bps | bruto | ganadores | control p95 |
|---|---|---|---|---|---|---|---|---|
| US30 | 1568 | 314 | −2,22 | 255 | **−2,23** | −1,87 | 43% | +1,77 |
| USTEC | 1567 | 314 | −0,83 | 235 | **−4,55** | −3,63 | 42% | +2,38 |

- Reserva por día (n=364): **−3,86 bps, CI [−6,34, −1,32]**; largos −4,56, cortos −3,11; todos los años negativos
  (2023 −1,1 · 2024 −5,6 · 2025 −3,2 · 2026 −3,9). Descubrimiento −0,90. Criterios: 1 ✅ · 2 ❌ · 3 ❌ · 4 ❌ · 5 ❌.
- **El efecto del paper va al revés en estos CFDs 2020-26:** después de un día fuerte, la última media hora
  revierte (pendiente negativa en los dos índices). No es una idea nueva para probar acá: sería un patrón de precio
  intradía (escalera E, cerrada) elegido después de mirar.
- **Cerrado** momentum de cierre en CFDs de índices. No probar otro umbral ni otro tramo.

### 11 Nov 2026 — P36 flujos de los ETF de bitcoin → BTC del día siguiente: NO PASA (`tools/backtest_p36_flujos_etf_btc.py`)

Criterio `docs/p36_flujos_etf_btc_criterio.md` (`58dd176` + enmienda 1 `2cdc9a3`). Flujo total diario de farside
(ene-2024 → oct-2026, 692 días con precio); tercio alto ⇒ largo BTC perpetuo 24 h desde las 08:00 UTC del día
siguiente, tercio bajo ⇒ corto; 0,14% ida y vuelta + funding real.

- **Enmienda 1 (declarada y commiteada antes de la corrida válida):** la primera corrida descartaba 579 días porque
  farside marca con "-" a los fondos que todavía no existían. Corregida la lectura, no los parámetros. La corrida
  descartada (n=52, abr-oct 2026) daba +0,07%, CI cruzando cero: tampoco pasaba.
- Umbrales del descubrimiento: −19 M / +216 M. **Descubrimiento n=231: −0,16%/día.** Reserva n=248: **+0,15%/día,
  CI [−0,09, +0,40]**, bruto +0,29%, 47% ganados, mitades +0,15 / +0,16, largos +0,15 / cortos +0,15; placebo p95
  +0,10. Criterios: 1 ✅ · 2 ❌ · 3 ❌ · 4 ✅ · 5 ✅.
- **Lectura:** el flujo es casi un espejo del precio del MISMO día (Spearman +0,41) y no anticipa el siguiente
  (+0,04). La reserva positiva le gana al placebo pero el descubrimiento perdía con la misma regla ⇒ con 2 años de
  datos no se distingue del azar. Por año: 2024 −0,10 · 2025 −0,07 · 2026 +0,21.
- **Cerrado** flujos de ETF → dirección de BTC al día siguiente. No probar ETH (el criterio lo reservaba para un PASA),
  otro horizonte ni IBIT solo.

### 11 Nov 2026 — P37 emisión de stablecoins → BTC la semana siguiente: NO PASA (`tools/backtest_p37_emision_stablecoins.py`)

Criterio `docs/p37_emision_stablecoins_criterio.md` (`25998ff`). Emisión semanal de USDT+USDC (DefiLlama) con un día
de rezago; tercio alto del descubrimiento (2020-22) ⇒ largo BTC perpetuo de lunes a lunes; 354 semanas.

- Umbral del descubrimiento: **+2,2% de emisión por semana**. Descubrimiento n=52: +1,68%/semana. **Reserva (2023-26):
  solo 8 semanas superan el umbral** (n≥40 exigido): +1,36%, CI [−2,10, +5,23], debajo del control de semanas al azar
  (p95 +4,43). Momentum (BTC de la semana previa, mismo esquema) +0,41. Corto del tercio bajo −1,06.
  Criterios: 1 ❌ · 2 ❌ · 3 ✅ · 4 ❌ · 5 ✅.
- **Falla de diseño mía, declarada:** un umbral fijo en % de emisión no es estacionario (en 2020-21 la oferta era
  chica y crecía 2-5% por semana; desde 2023 casi nunca). Igual el descriptivo no ayuda: la emisión se correlaciona
  más con la suba de BTC de la semana PREVIA (+0,24) que con la siguiente (+0,09) ⇒ sigue al precio, que era el
  riesgo declarado. Por año de los largos: 2020 +4,2 · 2021 −0,3 · 2022 −2,4 · 2023 −3,3 · 2024 +4,0 · 2025 −2,8.
- **Cerrado** emisión de stablecoins → BTC semanal. No re-probar con umbral móvil ni solo USDT (sería buscar el
  parámetro de algo que no pasó). Entran P39-P43 (cripto: prima de volatilidad, tendencia semanal, funding extremo,
  prima de Coinbase, vencimiento de Deribit).

### 12 Nov 2026 — P38 reversión después del fixing de Tokio en EURJPY/AUDJPY: NO PASA (`tools/backtest_p38_post_fixing_jpy.py`)

Criterio `docs/p38_post_fixing_jpy_criterio.md` (`e1fe1b0`). Corto el cruce de 00:55 a 03:00 UTC los días gotobi,
comisión real + spread mínimo de la vela; control = misma ventana en días hábiles no gotobi del mismo año.

| par | n | bruto | neto | CI95 | mitades | control p95 |
|---|---|---|---|---|---|---|
| EURJPY | 478 | +3,85 | **+2,54** | [+0,61, +4,51] | +0,57 / +4,51 | −0,67 |
| AUDJPY | 116 | +1,85 | +0,61 | [−2,62, +4,02] | −0,15 / +1,38 | +0,56 |
| **juntos** | **594** | +3,46 | **+2,16** | [+0,48, +3,87] | +0,57 / +3,76 | −0,87 |

- Criterios: 1 ❌ (n=594 < 600) · 2 ✅ · 3 ✅ · 4 ✅ · 5 ✅ · 6 ✅. **NO PASA por la regla de muestra.** Falla mía de
  preparación: no miré antes cuántas velas tenía AUDJPY en el cache (empieza en ene-2025, no en 2019).
- **Lo que sí dice:** en días normales esa ventana SUBE (control −2,3p neto ⇒ ~+1p bruto a favor del yen débil) y los
  días gotobi BAJA ~3,5p ⇒ no es la hora, es el día. USDJPY (descriptivo, ya mirado) muestra lo mismo: +2,68p contra
  control p95 +0,51.
- **Diagnóstico descriptivo (no decide, hecho después de mirar):** casi todo viene del **gotobi de fin de mes**
  (día ≥26): EURJPY +10,3p (n=80) contra +1,0p el resto (n=398); AUDJPY +3,1 (n=19) contra +0,1. Los gotobi comunes
  no alcanzan para pagar el costo.
- **Cerrado** P38 tal como estaba. No se re-corre con otro n ni sin AUDJPY. La idea que queda nace de mirar y por
  eso se prueba **solo donde no se miró**: P44 = corto el cruce con yen de 00:55 a 03:00 UTC el último día hábil del
  mes, en CHFJPY y NZDJPY (reservados de Fase 4, nunca abiertos), criterio declarado antes.

### 12 Nov 2026 — P39 prima de volatilidad en BTC (DVOL de Deribit): PASA el criterio, con reparos (`tools/backtest_p39_vrp_cripto.py`)

Criterio `docs/p39_vrp_cripto_criterio.md` (`f3d7dee`). Cada 30 días, si el DVOL supera la volatilidad realizada de
los 30 días previos, se vende volatilidad 30 días; resultado = proxy de swap de varianza vendido en puntos de vol
(incluye la convexidad), costo 2 puntos (pesimista 4). Mar-2021 → ago-2026.

| | con señal | neto/mes | ganadas | CI95 | desc. (2021-23) | reserva (2024-26) | anclas >0 | peor | caída máx |
|---|---|---|---|---|---|---|---|---|---|
| **BTC** | 55 | **+6,43** | 75% | [+2,49, +10,49] | +10,21 (n=31) | +1,55 (n=24) | 30/30 | −33,4 | 44,8 |
| **ETH** (fuera de muestra) | 48 | **+6,96** | 71% | [+1,90, +11,92] | +10,83 (n=28) | +1,53 (n=20) | 30/30 | −37,6 | 64,2 |

- Criterios: BTC 1 ✅ · 2 ✅ · 3 ✅ · 4 ✅ · 5 ✅ ⇒ **PASA**; ETH (mismo criterio, nunca mirado) también 5/5.
- Verificación propia antes de mirar ETH: el spot del cache es el precio de APERTURA con su hora exacta ⇒ la
  realizada previa no mira el futuro.
- **Por qué NO es un hallazgo todavía (los 3 reparos, en orden):**
  1. **El premio se achica hasta desaparecer.** Por año (BTC): 2021 +17,0 · 2022 +11,6 · 2023 +3,3 · 2024 +5,5 ·
     2025 +1,6 · 2026 −5,1. La reserva sola tiene CI [−3,4, +6,0] (BTC) y [−5,1, +7,5] (ETH); **desde 2025 da
     −1,3 / −1,4**. Es el mismo patrón que el funding (P15/P21): un premio cripto que se comprime cuando entra el dinero
     institucional.
  2. **El proxy es optimista.** El DVOL se calcula como el VIX (incluye las alas, que son más caras); un straddle ATM
     cobra menos, y armar la canasta completa de opciones cuesta más que 2 puntos. Un sesgo de 1-3 puntos alcanza para
     dejar la reserva en cero.
  3. **ETH no es independiente:** es otro instrumento del MISMO período, muy correlacionado con BTC. Confirma que el
     resultado no depende de BTC, no que siga vivo hacia adelante.
- El filtro no agrega: vender siempre da +6,35 en BTC (casi igual). Lo que funciona es el premio en sí, no la señal.

**Propuesta (para el OK del user, no se activa nada):**
- **Plan:** shadow en papel con precios REALES de opciones de Deribit (API pública, sin cuenta): cada 30 días anotar
  bid/ask del straddle ATM a ~30 días de BTC y ETH, simular la venta con cobertura delta diaria contra el perpetuo y
  registrar el resultado neto. Lectura a 6 meses (~mayo-2027), decisión a 12.
- **Razón:** el backtest pasó con un proxy y la única forma gratis de medir el costo real (bid/ask histórico de
  opciones es pago) es juntarlo hacia adelante. Mismo esquema que P19 (funding en papel).
- **Pros:** es premio por riesgo (escalera A), sin adivinar dirección; reglas fijas y automatizables; costo de armarlo
  medio día; no toca AIdan.
- **Contras:** 2025-26 ya da negativo ⇒ lo más probable es que el papel confirme que el premio se fue; riesgo de cola
  grande (peor mes −33 a −38 puntos, ~5 meses de premio); 6-12 operaciones por año ⇒ lento.
- **Opinión:** armarlo solo si se quiere una segunda pata en papel junto a P19; prior de que sirva en plata, bajo.
  No proponer variantes del filtro ni del plazo (sería buscar el parámetro).

### 12 Nov 2026 — P40 tendencia semanal en cripto (time-series momentum): NO PASA (`tools/backtest_p40_tsmom_cripto.py`)

Criterio `docs/p40_tsmom_cripto_criterio.md` (`d8110df`). Cada lunes, largo el perpetuo de cada una de las 6
principales (BTC, ETH, SOL, BNB, XRP, DOGE) si su retorno de 28 días es > 0; 0,07% por lado al entrar/salir + funding
real; ene-2020 → oct-2026.

- **Reserva (2023-26, 198 semanas): +0,785%/semana, CI [−0,071, +1,755]**, Sharpe 0,99. Siempre largo: +1,009%,
  Sharpe 0,88. **Placebo (misma fracción de semanas largas, al azar) p95: 1,10.** Descubrimiento: +2,75%/semana,
  Sharpe 1,81 vs 1,38. Criterios: 1 ✅ · 2 ❌ · 3 ✅ · 4 ✅ · 5 ❌.
- Por año (regla / siempre largo, %/semana): 2020 +2,55/+2,86 · 2021 +6,07/+6,60 · 2022 −0,38/−1,55 ·
  2023 +1,25/+1,97 · 2024 +1,61/+2,31 · 2025 +0,44/−0,08 · 2026 −0,42/−0,50. Invertida ~45-58% del tiempo.
- **Lectura:** la regla solo es "estar comprado la mitad del tiempo". Ayuda en los años bajistas (2022) y pierde en
  los alcistas; la caída máxima baja de 90% a 42%, pero el placebo con la misma exposición logra un Sharpe igual o
  mejor ⇒ el retorno de 4 semanas no aporta información sobre la próxima en 2023-26. Coincide con Fase 4 E4 (FX) y
  con lo que reporta la literatura reciente: el momentum de cripto se debilitó después de 2021.
- **Cerrado** momentum semanal de series de tiempo en cripto. No probar 2/8/12 semanas, otra cesta ni las reservadas.

### 13 Nov 2026 — P39b shadow en papel de la prima de volatilidad con precios reales de Deribit: ARMADO

OK del user (13-nov) a la propuesta de P39. Criterio `docs/p39b_shadow_vol_criterio.md` (`ca23af9`), tool
`tools/shadow_vol_deribit.py` (9 tests en `tools/test_shadow_vol_p39b.py`: no opera, solo endpoints públicos, no toca
AIdan, regla y proxy iguales a P39), base `%APPDATA%/AIdan/state/vol_shadow.db`, tarea `aidan-shadow-vol` (todos los
días 05:30 AR, arranca al prender la PC si se la perdió).

- Regla de P39 congelada: cada 30 días desde el 13-nov, si DVOL > realizada previa, vende 1 straddle ATM a ~30 días
  al **bid real**, cobertura delta diaria con el perpetuo de Binance (costo y funding reales), comisiones de Deribit,
  liquida al vencimiento con el precio oficial. Resultado en USD y en puntos de vol, comparado con el proxy de P39.
- **Diagnóstico diario** (brecha DVOL − IV bid del straddle ATM) para responder rápido si el proxy exagera.
- **Día 1 (13-nov), n=1, sin lectura:** brecha BTC +3,4 · ETH +4,3 puntos (umbral 1,5); spread bid-ask ~1,1 puntos.
  Si se sostiene, el reparo 2 se confirma y la reserva de P39 queda en negativo con precios reales. Ciclo 0 abierto en
  las dos (DVOL BTC 40,1 vs realizada 39,5; ETH 56,1 vs 55,8), vencimiento 4-dic.
- Lecturas: **~13-dic** (30 días de diagnóstico) · ~13-may-2027 (descriptiva) · **~13-nov-2027** (decisión, n≥18).
- **Enmienda 1 (13-nov, `7c4606d`, pedido del user):** se suman **Binance Options y Bybit Options** (lote mínimo 0,01 BTC
  ≈ $690, contra 0,1 BTC en Deribit), misma regla y mismo día para los tres; reporte también en USD con el lote mínimo.
  Día 1: brecha BTC +3,1 (Binance) / +3,2 (Bybit), ETH +4,0 / +5,0; spreads bid-ask más angostos que Deribit (0,3-0,4
  vs ~1,1 puntos). Ciclo 0 abierto en los 6 libros.
- **Enmienda 2 (13-nov, `da54768`, pedido del user):** límite de pérdida por operación = la prima cobrada (si recomprar al
  ask deja una pérdida igual o mayor, esa versión se cierra y espera al próximo ciclo). Se mide AL LADO de la regla sin
  límite; el reporte muestra total y peor resultado de las dos en USD con lote mínimo. Control una vez por día.


### 14 Nov 2026 — P41 funding extremo como señal contraria: NO PASA (`tools/backtest_p41_funding_extremo.py`)

Criterio `docs/p41_funding_extremo_criterio.md` (`52fba65`). Funding promedio de 3 días de BTC y ETH contra sus
percentiles 90/10 de los 365 días previos (móviles, por la lección de P37); arriba del 90 ⇒ corto 7 días, abajo del 10
⇒ largo; 0,14% ida y vuelta + funding real; una posición a la vez por moneda.

- **Reserva (2023-26) n=130: −1,34% por operación, CI [−2,58, −0,15]**, 47% ganados. Descubrimiento (2020-22) n=92:
  −0,12%. Placebo (mismas cantidades por moneda y lado, días al azar) p95 +1,03%. Criterios: 1 ✅ · 2 ❌ · 3 ❌ · 4 ❌ · 5 ❌.
- Por lado en la reserva: **corto (funding alto) −2,34%** (n=57, 40% ganados) · largo (funding bajo) −0,57% (n=73).
  En el descubrimiento el corto también perdía (−3,64%) y el largo ganaba (+1,68%). El funding cobrado (+0,14%) apenas
  paga la comisión; todo el resultado es precio. Por año: 2020 −4,0 · 2021 +1,1 · 2022 +0,2 · 2023 −0,7 · 2024 −1,6 ·
  2025 −2,6 · 2026 −0,9. BTC −0,61 / ETH −2,15.
- **Lectura:** se cumplió el riesgo declarado: el funding alto marca subas fuertes que siguen subiendo, no techos. El
  apiñamiento de largos no anticipa liquidaciones a 7 días. Que el corto pierda NO habilita la regla al revés (sería
  momentum, cerrado en P40, y buscar el signo después de mirar).
- **Cerrado** funding extremo como señal de dirección en cripto. No probar otro percentil, plazo ni ventana.

### 14 Nov 2026 — P42 prima de Coinbase → BTC del día siguiente: NO PASA, cerca (`tools/backtest_p42_prima_coinbase.py`)

Criterio `docs/p42_prima_coinbase_criterio.md` (`cd321ec`). Prima diaria = cierre BTC-USD de Coinbase / (spot de
Binance a las 00:00 × USDT-USD de Coinbase) − 1, desde may-2021 (cuando Coinbase lista USDT-USD). Terciles móviles de
365 días; tercio alto ⇒ largo el perpetuo 24 h, bajo ⇒ corto; 0,07% por lado al cambiar de posición + funding real.

- **Reserva (2024 → oct-2026) n=712 días: +0,19%/día, CI [−0,01, +0,38]**, mitades +0,16 / +0,21; placebo (prima
  desplazada) p95 +0,09. **Descubrimiento (2022-23) n=416: −0,06%/día.** Criterios: 1 ✅ · 2 ❌ (por 0,006) · 3 ❌ · 4 ✅ · 5 ✅.
- Descriptivo: la prima se correlaciona más con el retorno del MISMO día (Spearman +0,14) que con el siguiente
  (+0,04) ⇒ el riesgo declarado (reflejo del precio) se cumple en parte. Por año: 2022 0,00 · 2023 −0,11 ·
  2024 +0,35 · 2025 0,00 · 2026 +0,22. En la reserva ganan los dos lados (largo +0,14 / corto +0,22); entrando a las
  08:00 en vez de 00:00, +0,23.
- **Lectura:** mismo patrón que P36 (flujos de ETF): la reserva le gana al placebo, pero la misma regla perdía en
  2022-23 y el resultado depende de 2024 y 2026 ⇒ no se distingue de un régimen. No hay fuera de muestra limpio que
  mirar (ETH quedaba reservado solo para un PASA).
- **Cerrado** prima de Coinbase como señal diaria. No probar otros umbrales, horizontes ni ETH. *Si en el futuro
  aparece una tercera señal de "demanda de EE.UU." con el mismo patrón, la combinación (no cada una) sería la
  hipótesis, declarada antes.*

### 14 Nov 2026 — P43 vencimiento mensual de Deribit y volatilidad de BTC: NO PASA (`tools/backtest_p43_vencimiento_deribit.py`)

Criterio `docs/p43_vencimiento_deribit_criterio.md` (`03af480`). Velas de 1 h de BTCUSDT (Binance), jul-2019 → oct-2026.
Para cada viernes a las 08:00 UTC, `L` = ln(varianza realizada 48 h después / 48 h antes); vencimiento (último viernes
del mes) contra viernes normales.

- **Reserva (2023-26), 45 vencimientos vs 153 normales: D = +0,073 ⇒ ×1,08, CI [−0,20, +0,32].** Descubrimiento
  (2019-22), 40 vs 132: D = +0,19 (×1,21), CI [−0,09, +0,49]. Criterios: 1 ✅ · 2 ❌ · 3 ✅ · 4 ❌ (1,08 < 1,10).
- Descriptivo: en la reserva las 48 h previas al vencimiento son un 19% más tranquilas que en un viernes normal (el
  "pegado" se ve), pero las posteriores también lo son (−13%): no hay liberación. En 2019-22 era al revés (antes +18%,
  después +43%). Trimestrales ≈ normales. El precio cae −0,61% en las 48 h previas al vencimiento vs +0,08% en
  viernes normales (no decide, t≈1,5). Por año D: 2019 +0,05 · 2020 +0,40 · 2021 +0,15 · 2022 +0,12 · 2023 −0,15 ·
  2024 +0,12 · 2025 +0,28 · 2026 +0,04.
- **Lectura:** el signo es el esperado en 7 de 8 años, pero el tamaño en la reserva es chico y el ruido de 48 h lo
  tapa ⇒ no sirve para ubicar en el tiempo la venta de volatilidad de P39b (un 8% de varianza ≈ 1,5 puntos de vol
  sobre 40, del orden del spread de la opción).
- **Cerrado** vencimiento de Deribit como efecto de volatilidad/dirección en BTC. No probar 24/72 h ni ETH.

### 14 Nov 2026 — P44 gotobi de fin de mes en CHFJPY/NZDJPY (reservados): NO PASA (`tools/backtest_p44_gotobi_fin_de_mes.py`)

Criterio `docs/p44_gotobi_fin_de_mes_criterio.md` (`71db919`). Corto el cruce de 00:55 a 03:00 UTC el último día hábil
del mes, comisión real + spread mínimo de la vela; control = misma ventana el resto de los días hábiles del mismo año.
Antes de declarar solo se miró el largo del cache (dic-2019 → ago-2026 en los dos).

| par | n | bruto | neto | CI95 | mitades | control p95 |
|---|---|---|---|---|---|---|
| CHFJPY | 80 | +10,91 | **+9,15** | [+4,39, +13,96] | +5,81 / +12,49 | +2,72 |
| NZDJPY | 80 | +0,02 | **−1,36** | [−5,92, +2,73] | −1,77 / −0,96 | +1,66 |
| **juntos** | **160** | +5,47 | **+3,89** | [+0,49, +7,14] | +2,02 / +5,77 | +1,10 |

- Criterios: 1 ✅ · 2 ✅ · 3 ✅ · 4 ✅ · 5 ✅ · **6 ❌** (NZDJPY negativo). **NO PASA.**
- Lo que dice: el efecto de fin de mes aparece fuerte en 3 de 4 cruces con yen (EURJPY y AUDJPY en P38, CHFJPY acá) y no
  en NZDJPY. CHFJPY sube año a año (bruto 2019 +3,9 → 2025 +21,2), lo que se parece más a la debilidad del yen 2022-25
  amplificada en un día de flujo que a un efecto estable. Otros gotobi (no fin de mes): CHFJPY +1,33p, NZDJPY −0,48p.
- **Cerrado** Gotobi/fixing de Tokio en todas sus variantes, como declaraba el criterio. Quedarse con CHFJPY solo sería
  un subconjunto elegido después de mirar: no se prueba. Los JPY reservados ya están gastados.
- Próxima: P45 (carry de funding de Hyperliquid en otras monedas). Nueva en la cola: P51 (cierre del gap de apertura semanal en FX).

### 14 Nov 2026 — P13b shadow binaria en vivo: NO PASA ⇒ tarea borrada

Lectura a n≥400 (`tools/score_shadow_binaria.py`): 432 señales, 427 resueltas, **acierto 48,71% CI [44,0, 53,4]**;
payout real medido n=365, mediana 71,7% ⇒ break-even 58,24%; EV por $1 −0,21 CI [−0,30, −0,13]. Criterios 1 y 2 ❌.
Ni el extremo alto del CI llega al break-even ⇒ no hacía falta esperar a n=800. Tarea `aidan-shadow-binaria` borrada
(OK del user). **Cerrado** A1 como binaria en Deriv. La base `state/binary_shadow.db` queda.


### 16 Nov 2026 — P45 carry de funding de Hyperliquid en 15 monedas nuevas: PASA, con el mismo reparo (`tools/backtest_p45_hl_otras_monedas.py`)

Criterio `docs/p45_hl_otras_monedas_criterio.md` (`863e142`) + enmienda 1 (`c475b3f`). Reglas de P21-A sin cambios
sobre las 15 monedas con más volumen de HL que no estaban en P21 (lista fijada por volumen antes de mirar el funding).
**La 1ra corrida dio un PASA falso** (JUP +1066%, XPL +389%): la primera vela del spot de Binance tras el listado
trae un precio de relleno y la regla entraba ahí. Enmienda 1 (antes de re-medir): se descarta esa vela y el tool
aborta si en alguna vela usada el perpetuo y el spot se separan ≥ 5%.

| | anual s/capital | CI95 | mitades | caída máx | monedas > 0 | tasa libre |
|---|---|---|---|---|---|---|
| **P45 (decide, capital entre las disponibles)** | **+7,34%** | [+5,51, +9,40] | +12,1 / +2,6 | 0,66% | 14/15 | 4,58% |
| con ceros (como P21) | +3,58% | [+2,85, +4,43] | +5,1 / +2,1 | 0,34% | 14/15 | |
| costo 0,49% (deslizamiento ×2,5) | +6,82% | [+4,99, +8,87] | | 0,72% | 14/15 | |

Por año: 2023 +11,7% · 2024 +12,9% · **2025 +2,8% · 2026 +2,7%**. Las que más pagan: kPEPE, NEAR, AAVE, UNI (+7 a
+12%/año activo); la única negativa, TRUMP (funding medio negativo).

**Lectura honesta:** pasa los 5 criterios en monedas que nunca se usaron ⇒ el premio de HL **no es de las 10 grandes,
es estructural**. Pero repite el problema de P15/P21: **la 2da mitad y 2025-26 quedan debajo de la tasa libre** (~4%).
Y la versión con ceros (la que usaba P21) no le gana a la tasa libre: la diferencia es cómo se reparte el capital
cuando hay pocas monedas, declarada antes de medir pero que hay que tener presente. Sobre $600 son ~$44/año en
promedio, ~$16/año al ritmo de 2025-26. Próximo paso propuesto (OK del user): sumar 4-6 de estas monedas al libro de
papel de HL de P19, para ver en vivo si un libro más ancho saca algo más que las 6 grandes.

### 16 Nov 2026 — P46 nowcast de Cleveland vs consenso antes del CPI: NO PASA (`tools/backtest_p46_nowcast_cpi.py`)

Criterio `docs/p46_nowcast_cpi_criterio.md` (`a4e8af1`). Nowcast del CPI m/m de cada día (archivo público de la Fed
de Cleveland, tal como se publicó) contra el consenso de Investing.com; EURUSD de 18:00 NY del día previo a 15 min
antes del dato, costo 1,3 pips. Descubrimiento jun-2018 → dic-2023.

- n=39 (47 sin señal por diferencia < 0,05): **neto −14,3p por operación**, mediana −19,7, CI [−22,9, −5,3], mitades
  −19,3 / −9,5, bruto −13,0 contra azar p95 +8,2; ganadas 23%. Criterios 2, 3 y 4 ❌.
- El nowcast **acertó el signo de la sorpresa solo 9 de 25** (36%): en este período no le ganó al consenso (en 2021 quedó
  sistemáticamente abajo y el dato salió arriba). Manteniendo hasta +30 min después del dato: −22,6p. Placebo (mismas
  señales los 5 días previos): −2,5p.
- La pérdida es grande pero **no se invierte la señal** (sería elegir después de mirar). **Cerrado** el posicionamiento
  pre-CPI por nowcast; no se prueban el core ni otros umbrales. Reserva (2024-26) no mirada.

### 16 Nov 2026 — P48 carry de funding con stETH: medición INVÁLIDA por datos (`tools/backtest_p48_steth_carry.py`)

Criterio `docs/p48_steth_carry_criterio.md` (`6cfb36d`). La corrida dio NO PASA (+6,9%/año pero CI [−3,1, +17,0] y caída
máx 13,5%), **pero el dato está roto**: el cociente stETH/ETH armado con los dos precios diarios de DefiLlama salta
±10% de un día al otro (p1-p99 0,93-1,08; valores de 1,11 y 1,14 son imposibles; el mínimo real de jun-2022 fue
~0,935, acá 0,849). Ese ruido infla la caída y el CI. **No hay historia gratis limpia** del par para 2022 (CoinGecko
limita a 365 días, Binance no tiene `STETHETH`). Error mío: la línea "por año" imprimió también 2025-26 (la reserva);
como la medición no vale, no cambia nada, y el tool ahora solo imprime el tramo elegido. **Reemplazo: P52** con WBETH,
que tiene par propio en Binance desde may-2023.

### 16 Nov 2026 — P50 préstamo de stablecoins en Aave vs letra: NO PASA (`tools/backtest_p50_prestamo_stablecoins.py`)

Criterio `docs/p50_prestamo_stablecoins_criterio.md` (`2cbfe52`). 50% USDC + 50% USDT en Aave v3 Ethereum, APY diario
publicado (DefiLlama), letra a 3 meses (FRED DTB3), gas 1%/año sobre $1.000. Descubrimiento feb → dic 2023.

- APY media USDC 3,87% y USDT 4,14% contra letra 5,13% ⇒ **premio neto −2,13%/año** (sin gas −1,1%), CI [−3,1, −1,4],
  las dos mitades negativas. Caída máx en USD 0,64% (el precio diario no ve el piso de 0,88 intradía del 11-mar).
- Con las tasas altas de 2023, prestar en cripto pagó MENOS que la letra. **Cerrado** el préstamo pasivo de stablecoins
  en Aave; no se busca otro mercado, cadena ni moneda. Reserva no mirada.

### 16 Nov 2026 — P47 inclusión en el S&P 500: salteada por datos

No hay fuente gratis de las fechas de ANUNCIO (Wikipedia trae la fecha efectiva; los comunicados de S&P no están en un
archivo bajable). Queda en cola. Próximas: P49, P51, P52. Nuevas en la cola: P52 (carry con WBETH), P53 (deslistados de
Binance), P54 (comprar la stablecoin en un depeg).

### 17 Nov 2026 — P51 cierre del gap de apertura semanal en FX: NO PASA, inválido por costo (`tools/backtest_p51_gap_semanal.py`)

Criterio `docs/p51_gap_semanal_criterio.md` (`9500745`). 20 pares M5, gap > 0,5·ADR14, entrada 1 h después de la
apertura del domingo hacia el cierre del viernes, salida al tocarlo o a las 24 h.

| | n | neto | CI95 | mitades | control p95 | pares > 0 |
|---|---|---|---|---|---|---|
| descubrimiento (costo de la cache) | 333 | +12,1p | [+5,2, +19,0] | +7,9 / +16,3 | +5,9 | 13/18 |
| reservados (GBPNZD, NZDCHF, NZDCAD, GBPCAD) | 87 | +22,2p | [+12,4, +31,7] | +17,0 / +27,3 | +10,7 | 4/4 |

**En la letra pasa todo, y no lo creo. Lo que lo tira:**
- **El costo estaba mal.** El criterio usaba el spread de la cache (el MÍNIMO de la vela, "cota optimista"). A la hora
  de entrada (domingo 22-23 UTC) el spread real medido con ticks de MT5 es **~14,5 pips de mediana** contra 0,2 de la
  cache (`tools/check_p51_spread_ticks.py`, n=86, MT5 solo guarda ticks desde 2026). Descontando eso, el descubrimiento
  queda en **≈ −2p por operación** (falla el criterio 2).
- **Es casi todo el lado largo:** 250 largos +18,5p contra 83 cortos −7,0p. Los gaps "hacia abajo" son 3 de cada 4:
  las velas son de bid, y en la apertura el spread se abre y baja el bid ⇒ buena parte del gap es spread, no precio.
  Entrando 5 min más tarde (al cierre de la misma vela) los largos pierden 8p de golpe.
- **Las 20 monedas comparten los fines de semana.** Agrupando por fin de semana (89) el CI es [−2,2, +25,4] y sin los
  5 mejores fines de semana la media es −0,8p. Los reservados son los mismos fines de semana ⇒ no son independientes.
- Lo único que queda en pie: 2026 con el spread real da +17p (n=86, ~30 fines de semana); es un año elegido después
  de mirar ⇒ no vale. **Cerrado** el gap semanal en FX; no se prueban otras horas de entrada (la que evita el spread
  sería elegida después de mirar) ni umbrales. Error mío de diseño: tenía que declarar el CI por fin de semana y
  verificar el spread de la hora de entrada antes de medir.

### 17 Nov 2026 — P52 carry de funding con WBETH (ETH en staking de Binance): NO PASA en la reserva (`tools/backtest_p52_wbeth_carry.py`)

Criterio `docs/p52_wbeth_carry_criterio.md` (`48c072c`) + enmienda 1 (`1e6de96`: el control de datos abortó por el
desacople REAL de WBETH del 10/11-oct-2025, −3,1% en una vela y vuelta en la siguiente; se pasó a controlar el tramo
que se mide, antes de ver ningún resultado). Regla de P15 congelada, pata larga = ETH × cociente `WBETHETH` de Binance
(8 h, sin ruido: salto máx 0,49% en el descubrimiento). Costo 0,48% ida y vuelta.

| tramo | WBETH (decide) | CI95 | mitades | caída máx | tasa libre | ETH sin staking | WBETH siempre adentro |
|---|---|---|---|---|---|---|---|
| descubrimiento may-2023 → 2024 | **+6,47%/año** | [+4,8, +8,3] | +7,4 / +5,5 | 0,62% | 5,21% | +5,18% | +7,50% |
| **reserva 2025 → oct-2026** | **+1,46%/año** | [+0,35, +2,45] | +1,8 / +1,2 | 1,49% | **3,97%** | +0,75% | +2,42% |

- El descubrimiento pasa los 4 criterios; **la reserva no**: +1,5%/año contra 4,0% de tasa libre. El staking suma lo
  prometido en el cociente (+2,6%/año) pero la regla pasa casi todo 2025-26 afuera (funding bajo) y ahí no lo cobra.
  Ni "siempre adentro" (+2,4%) llega a la tasa libre. El desacople del 10-oct-2025 llevó la caída a 1,5% (chica).
- Es el mismo techo de P15/P21/P45: **el premio de funding de 2025-26 no le gana a la letra**, con o sin staking.
  **Cerrado** el carry con ETH en staking; no se cambia de token ni de umbral.
- Error menor heredado de P48: la línea "componentes período completo" suma también la reserva (no decide; corregir
  si se reusa el tool).

### 17 Nov 2026 — P49 desbloqueos grandes de tokens: NO PASA (`tools/backtest_p49_unlocks.py`)

Criterio `docs/p49_desbloqueos_criterio.md` (`ad8d14b`). Calendario público de DefiLlama (`tools/p49_unlocks_data.py`),
cliffs ≥ 1% de lo circulante con insiders o inversores, corto del perpetuo de Binance de D−7 a D, funding real,
costo 0,20%. Descubrimiento 2022-2024.

- n=323 eventos (32 monedas, 122 semanas; 110 descartados porque el perpetuo todavía no existía): **neto +0,86% por
  evento**, mediana +1,79%, ganados 56%, pero **CI agrupado por semana [−1,49%, +3,20%]** y **mitades −0,27% / +1,98%**
  ⇒ fallan los criterios 2 y 3. Pasan 1, 4, 5 y 6.
- Lo que sí se ve: en semanas normales el corto de esas mismas monedas pierde (control p50 −1,45%) ⇒ la semana previa
  al desbloqueo rinde ~2,3 puntos mejor que una semana cualquiera de la moneda. Pero en absoluto no alcanza (las alts
  subieron en 2023-24 y el corto solo pierde menos). Descriptivo: los desbloqueos > 10% dan +5,6% (n=38) — elegido
  después de mirar, no vale. Después del desbloqueo (D→D+7) el corto pierde −0,55%.
- **Cerrado** el corto absoluto antes del desbloqueo; no se prueban otros tamaños, ventanas ni categorías. La versión
  relativa (corto la moneda contra una cesta, que es lo que el control sugiere) entra como P55 **solo sobre la reserva
  2025-26**, que nadie miró, porque la idea sale de mirar el descubrimiento.


Próximas: P53, P54, P55. Nuevas en la cola (17-nov): P55 (desbloqueos relativos, solo reserva), P56 (corto de
listados nuevos en perpetuos), P57 (vault HLP de Hyperliquid vs letra).
