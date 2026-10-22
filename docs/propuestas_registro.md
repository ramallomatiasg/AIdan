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
| P4 | **Lead-lag de la cesta USD:** cuando GBPUSD/AUDUSD/NZDUSD ya se movieron X·ATR en M5 y EURUSD no, operar el "catch-up". | Nueva lógica | El cache `.cache_fase2/M5_500000` tiene 26 pares alineados. Nunca medido. | 1 día | en cola |
| P5 | **Compresión → expansión en D1: inside bar / NR7 breakout** con stop en el otro extremo. | Nueva lógica | Nunca medido. Barato con las velas D1 que ya hay. | medio día | en cola |
| P6 | **Volumen de ticks como filtro de la ruptura** (spike de `tick_volume` vs mediana 20 barras). | Cambio sobre lo implementado | Backlog #4 desde mayo, nunca medido. Se mide como celda del arnés Fase 2, no en vivo. | medio día | en cola |
| P7 | **Leo: pedirle su diario REAL de operaciones** (fecha, par, entrada, SL, TP, resultado) + Setup 2. | Método externo | Si Leo es rentable, sus trades reales son la verdad contra la que comparar la traducción, mejor que el audit visual. Pendiente de su respuesta al artifact. | 0 (depende de él) | esperando a Leo |
| P8 | **Combinar lo implementado: calendar play + canal rápido de news (v3.65.0)** = operar el dato con número a T+15-60 s, dirección por sorpresa, TP en la excursión mediana a +3 min medida por el shadow. | Combinación | Solo tiene sentido si el shadow de calendar play junta n≥25 (hoy 1 fila, por horario). | 0 hasta tener data | bloqueada por muestra |
| P9 | **A1 (reversión a 2σ, Fase 3b) en oro e índices**, con el mismo arnés en pseudo-pips de P1 (`.cache_p1/M15`). | Misma lógica, otro instrumento + combinar lo medido | A1 fue la ÚNICA señal que le ganó al azar (~+0,5p bruto sobre el control) y murió por costo (0,9p+spread en FX). En oro/índices el costo medido en P1 es **0,20-0,28 pseudo-pips** ⇒ el mismo +0,5 sobre el azar podría quedar neto positivo. A diferencia de `structure`, acá hay información probada; falta saber si sobrevive a otro instrumento. | medio día (cache ya bajado) | **PRÓXIMA** |
| P10 | **Fade del canal Donchian D1 (reversión de mediano plazo), probado SOLO en los 6 pares reservados.** Corto cuando el cierre rompe el máximo de 20 días, largo al revés; misma ejecución/stop/salida que P2 invertidas. | Hipótesis nacida de un NO PASA, test fuera de muestra | P2 dio que entrar con la ruptura de 20 días es **peor que el azar** (−0,23R vs control −0,14R, 16/20 pares negativos, las 2 mitades) con costo de solo 0,016R ⇒ el bruto negativo es información, no fricción. Distinto de lo refutado: fade-chop y L1 eran intradía (M5) con costo ~15% del rango; acá el costo es ~1% del movimiento. Como la idea sale de mirar los 20 pares, **se declara antes y se mide únicamente en los 6 reservados** (nunca mirados) ⇒ out-of-sample limpio. | medio día (tool de P2 + flag) | ❌ **NO PASA 22-oct** (4/5: CI cruza cero), ver abajo. Cerrado Donchian D1 en FX en cualquier dirección |
| P11 | **Carry con filtro de tendencia (D1/semanal):** mantener el lado del par que COBRA swap solo cuando la tendencia D1/60d va en la misma dirección; rebalanceo semanal, 20 pares. | Paper (Menkhoff et al. 2012; Lustig-Verdelhan) | Es la única familia de FX con premio documentado que NO es de precio intradía: el retorno viene del diferencial de tasas, no de adivinar la dirección, y el horizonte largo deja el costo en ~1% del movimiento. Nunca medido acá (0 menciones de carry en docs). **Límite de data a resolver ANTES de declarar:** el `spec.json` del cache trae el swap ACTUAL, no el histórico ⇒ usarlo para 2020-26 sería look-ahead (en 2020-21 las tasas estaban en ~0). Hace falta una tabla mensual de tasas de política (Fed/BCE/BoE/BoJ/RBA/RBNZ/BoC/SNB, pública) para reconstruir el swap mes a mes. | 1 día (tabla de tasas + tool) | en cola |
| P12 | **Drift pre-FOMC (Lucca & Moench 2015) en índices:** largo US500/USTEC/DE40 desde el cierre del día anterior al anuncio hasta 14:00 ET del día del FOMC (antes del dato); descriptivo en USD (EURUSD). | Paper + otro instrumento | Es el único efecto de calendario documentado que ocurre ANTES del dato (no hay que reaccionar rápido, que es donde news perdió) y vive en índices, donde el costo medido en P1 es 0,2-0,3 pp. Nunca medido acá (0 menciones de FOMC/Lucca en docs). **Ojo:** la literatura posterior (2016+) reporta que el efecto se debilitó tras publicarse ⇒ prior bajo, y con ~8 reuniones/año hay ~50 eventos en 2020-26 ⇒ el gate tiene que ser por evento, no por vela. Necesita la tabla de fechas FOMC (pública) y `.cache_p1/M15`. | medio día | en cola (nueva 22-oct) |

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
