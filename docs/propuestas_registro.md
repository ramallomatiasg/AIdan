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
| P19 | **Shadow en papel del carry de funding (P15)**: cada 8 h, con el funding y los precios públicos de Binance en vivo, registrar qué haría la regla congelada de P15 (entrar/salir, funding cobrado, costo) en una base propia; sin órdenes. | Siguiente paso de lo único que pasó | P15 es la única idea de la línea que pasó, también fuera de muestra, pero 2025-26 rindió casi cero. Antes de cualquier plata hay que ver si el premio sigue vivo HOY y si la ejecución (base spot-perpetuo al entrar) se parece a la del backtest. Mismo esquema que el shadow P13b (proceso propio + tarea). | medio día | 🧪 **SHADOW ARMADO 27-oct** (`tools/shadow_funding.py`, criterio `docs/p19_shadow_funding_criterio.md`): lectura a 90 días (~25-ene), decisión a 180 (~25-abr). Ver abajo |
| P20 | **Cash-and-carry con futuros TRIMESTRALES de cripto** (comprar spot + vender el futuro con vencimiento de Binance, BTC/ETH, mantener hasta el vencimiento) cuando la base anualizada supera la tasa libre + costo. | Misma lógica que P15, otro instrumento | Mismo premio que P15 (lo pagan los apalancados en largo) pero **se fija al entrar**: la base pactada no cambia con el régimen día a día, que es justo lo que hizo caer a P15 en 2025-26. Al vencimiento converge al spot ⇒ el resultado se conoce al entrar salvo costos. Data pública (velas de los contratos de entrega de Binance, `dapi`/`fapi` con vencimiento). Nunca medido acá. | 1 día | ❌ **NO PASA 30-oct**: +2,81%/año sobre el capital contra tasa libre 3,40%; 2025 +2,8% y 2026 +0,4%, también debajo ⇒ no arregla lo que hizo caer a P15. Ver abajo. Cerrado |
| P21 | **Carry de funding (P15) en Hyperliquid y en el diferencial entre exchanges** (mismo motor y reglas congeladas de P15; variante: cobrar el funding del exchange que más paga y cubrir en el que menos). | Misma lógica, otro instrumento/venue | P15 es lo único que pasó, y cayó en 2025-26 en Binance. Hyperliquid liquida funding cada HORA y suele pagar más que Binance (otro público, más apalancado); el diferencial entre exchanges es un premio distinto del nivel. API pública (`api.hyperliquid.xyz`, resuelve desde esta red) con historial de funding. Nunca medido acá (P15 solo usó Binance). | medio día | ✅ **A PASA 31-oct, también fuera de muestra** (+6,2%/año sobre el capital vs tasa libre 4,6%, ~2,5× Binance en el mismo período); **B (diferencial) NO PASA** (+3,3%). Pero 2025-26 vuelve a quedar debajo de la tasa libre. Ver abajo |
| P22 | **Loop de hipótesis con IA sobre datos que AIdan no mira** (posicionamiento COT, tasas, bonos, VIX, dólar, petróleo; 7 monedas, 1999 →): la IA (Groq) propone con lista cerrada, el arnés prueba descubrimiento 1999-2014 → reserva 2015 → shadow hacia adelante, y TODO lo probado vuelve como memoria. Familias cerradas tras 3 fallos, espejos y duplicados rechazados. | Pedido del user (28-oct): que AIdan aprenda de todo y se pula solo | Aprende de 25 años de datos y no de 7 trades/día; mira más que precio. | 1 día | 🧪 **ARMADO 28-oct**: 4 vueltas, 31 hipótesis, 0 pasan el descubrimiento (ver abajo) |
| P21 | **¿Un broker más barato salva algo?** Fusion Zero (USD 4,50 ida y vuelta) contra IC (USD 7), sobre todo lo ya medido. | Pedido del user (28-oct) | Si el problema fuera el costo, bajar 1/3 la comisión daría vuelta lo que estaba cerca. | medio día | ❌ **NO PASA 28-oct**: ver abajo |
| P23 | **A1 en EUR/USD con entrada LÍMITE (maker)**: poner la orden en la banda de 2σ en vez de entrar a mercado, con Fusion. | Cambio de ejecución sobre lo único con información | Con Fusion A1 en EUR/USD queda en +0,08 pips (cero). Entrar con límite ahorra el spread y entra en mejor precio, pero sufre selección adversa (solo se llena cuando el precio sigue en contra): hay que medirlo con velas de 1 minuto o ticks, no con M15. | 1 día | en cola (nueva 28-oct) |
| P24 | **Prima nocturna en índices (overnight drift)**: largo US30/USTEC/DE40 del cierre de la sesión de contado a la apertura siguiente, neto de spread y del swap REAL de MT5; descriptivo: el tramo intradía (apertura → cierre). | Paper + otro instrumento | Lou, Polk & Skouras (2019) y Cliff, Cooper & Gulen (2008): en EE.UU. casi todo el retorno de las acciones se gana de noche y el intradía rinde ~0. No adivina dirección intradía (lo refutado acá) y vive en índices, donde el costo medido en P1 es 0,2-0,3 pp. El riesgo es el swap del CFD (se cobra justo por la noche que se mantiene). Data ya bajada (`.cache_p1/M15`). Nunca medido acá. | medio día | en cola (nueva 30-oct) |
| P25 | **Cambio de mes en índices (turn-of-the-month)**: largo US500/US30/USTEC/DE40 del cierre del último día hábil del mes al cierre del 3er día hábil del mes siguiente, neto de spread y swap REAL de MT5; control = misma ventana de 4 días en fechas al azar del mismo año. | Paper + otro instrumento | Ariel (1987), Lakonishok-Smidt (1988), McConnell-Xu (2008): en EE.UU. casi todo el retorno mensual de las acciones se concentra en esa ventana (flujos de sueldos y fondos). Distinto de Fase 5 (rebalanceo de FX fin de mes) y de P12 (pre-FOMC). No adivina dirección intradía y vive en índices (costo 0,2-0,3 pp). Prior medio: efecto publicado hace décadas, puede estar arbitrado. ~80 meses en 2020-26 ⇒ gate por evento. | medio día | en cola (nueva 31-oct) |
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

