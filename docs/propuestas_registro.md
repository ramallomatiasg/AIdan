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
| P1 | **Misma lógica, otro instrumento: XAUUSD, USTEC, DE40, US30 en M15/H1.** Correr el detector de `structure` (arnés Fase 2, `--symbols`) y los planes de Fase 4 sobre oro e índices. | Cambio de instrumento | Screen del 9-oct (abajo): en EURUSD el costo de un trade es **~15% del rango mediano de una vela M15**; en oro 1,5%, USTEC 2,3%, DE40 1,5%. El research dijo que lo que falla es el supuesto "scalping intradía con esta fricción" — esta es la salida más barata: 6-10x menos fricción por el mismo movimiento relativo. Nunca medido acá (0 menciones de XAU/oro en docs). | 1 día (cache de velas nuevo) | **PRÓXIMA** |
| P2 | **Trend following clásico H4/D1: canal Donchian 20/55 con stop ATR y trailing (turtle)**, 20 pares + oro + índices, con swap. | Nueva lógica | H4 solo se probó con el detector de structure (refutado); Donchian nunca. Horizonte largo = costo chico frente al movimiento (c/ATR D1 ≈ 1%). Choca con lote mínimo como D1, pero primero saber si hay edge. | 1 día | en cola |
| P3 | **Rango asiático → ruptura de Londres** (orden en los extremos del rango 00-07 UTC, SL al otro lado, TP 1-2× rango). | Nueva lógica | Rankeada en el research del 19-ago, nunca medida acá. Es confluencia + sesión, las dos cosas que sobrevivieron en el estudio de falsificación. | medio día | en cola |
| P4 | **Lead-lag de la cesta USD:** cuando GBPUSD/AUDUSD/NZDUSD ya se movieron X·ATR en M5 y EURUSD no, operar el "catch-up". | Nueva lógica | El cache `.cache_fase2/M5_500000` tiene 26 pares alineados. Nunca medido. | 1 día | en cola |
| P5 | **Compresión → expansión en D1: inside bar / NR7 breakout** con stop en el otro extremo. | Nueva lógica | Nunca medido. Barato con las velas D1 que ya hay. | medio día | en cola |
| P6 | **Volumen de ticks como filtro de la ruptura** (spike de `tick_volume` vs mediana 20 barras). | Cambio sobre lo implementado | Backlog #4 desde mayo, nunca medido. Se mide como celda del arnés Fase 2, no en vivo. | medio día | en cola |
| P7 | **Leo: pedirle su diario REAL de operaciones** (fecha, par, entrada, SL, TP, resultado) + Setup 2. | Método externo | Si Leo es rentable, sus trades reales son la verdad contra la que comparar la traducción, mejor que el audit visual. Pendiente de su respuesta al artifact. | 0 (depende de él) | esperando a Leo |
| P8 | **Combinar lo implementado: calendar play + canal rápido de news (v3.65.0)** = operar el dato con número a T+15-60 s, dirección por sorpresa, TP en la excursión mediana a +3 min medida por el shadow. | Combinación | Solo tiene sentido si el shadow de calendar play junta n≥25 (hoy 1 fila, por horario). | 0 hasta tener data | bloqueada por muestra |

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
