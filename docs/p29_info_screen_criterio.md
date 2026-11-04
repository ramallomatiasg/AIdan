# P29 — screen de información: ¿qué dato anticipa el retorno? — criterio declarado ANTES de medir

**Fecha:** 4-nov-2026. **Origen:** `docs/fuentes_de_ventaja_2026-11-04.md` (pedido del user: *"estamos atacando el
problema que no es"*). **Tool:** `tools/info_screen.py` (read-only: sin MT5, sin DB de AIdan; caches ya bajados).

## Pregunta

Para cada dato candidato, ¿su valor al cierre de la vela `t` anticipa el retorno de `t` a `t+h`, **fuera de la muestra
donde se miró**, **mejor que el mismo dato desordenado** y **por más que el costo de operar**?

## Datos (fijos)

- **FX M15, ~20 años** (`.cache_fase2/M15_500000`): EURUSD, GBPUSD, USDJPY, AUDUSD. Reservados para la etapa
  siguiente, NO se miran acá: EURGBP, USDCHF, NZDUSD, EURJPY.
- **Índices y oro M15, 2020-26** (`.cache_p1/M15`): USTEC, US30, DE40, XAUUSD.
- **Cripto 8 h, 2019-26** (`.cache_p15`): BTC, ETH, SOL (perpetuo + funding). Reservadas: ADA, LINK, LTC, AVAX.
- **Partición:** descubrimiento = primer 70% de cada serie en el tiempo; reserva = último 30%.
- **Horizontes:** M15 → h = 4, 16, 96 velas (1 h, 4 h, 1 día). Cripto → h = 1, 3, 21 (8 h, 1 día, 7 días).
- **Muestras sin solapar:** se toma una observación cada `h` velas.
- **Costo por operación (ida y vuelta):** FX = spread mediano de las velas + comisión del spec (EURUSD 0,9 p); índices
  = spread mediano (1,0-1,2 puntos); oro = 0,04 + 0,07 (comisión); cripto perpetuo = 0,10% del precio.

## Catálogo (cerrado; no se agrega nada después de ver resultados)

Dirección:
- **F1 `hora`:** retorno medio a `h` por hora UTC, estimado en descubrimiento (estructura de flujos por sesión).
- **F2 `dia`:** ídem por día de la semana.
- **F3 `lead_ustec`:** retorno de USTEC en la última hora → aplicado a EURUSD, GBPUSD, USDJPY, AUDUSD y XAUUSD
  (información de otro mercado; solo 2020-26).
- **F4 `momentum`:** retorno propio de las últimas `h` velas (control: se espera ~0 intradía).
- **F5 `rev2s`:** z-score del cierre contra su media de 20 velas, con signo invertido (control: es A1; se espera
  información positiva **pero debajo del costo**, como dio Fase 3b).
- **F6 `funding_7d`** (cripto): funding medio de los 7 días previos, signo invertido (funding alto ⇒ largos pagando).
- **F7 `basis`** (cripto): perpetuo/spot − 1, signo invertido.

Riesgo (no da dirección; se mide aparte):
- **R1 `vol`:** rango medio de las últimas 16 velas (M15) / 6 períodos (cripto) → tamaño absoluto del retorno a `h`.

## Medición

- **IC** = correlación de Spearman entre el dato y el retorno siguiente (para R1, contra |retorno|), en descubrimiento
  y en reserva.
- **Placebo:** el mismo dato desplazado circularmente en la reserva (200 corrimientos al azar, semilla 20261104) ⇒
  p95 de |IC|.
- **Prueba económica (solo dirección):** con los cortes de quintil del descubrimiento, en la reserva se compra en el
  quintil superior y se vende en el inferior; neto por operación = retorno con signo − costo. CI95 bootstrap.

## Criterio (por celda instrumento × dato × horizonte)

**Dirección PASA si se cumplen las 4:**
1. n de reserva ≥ 200 observaciones sin solapar.
2. IC de descubrimiento e IC de reserva con el mismo signo, y |IC reserva| > p95 del placebo.
3. Neto medio por operación en reserva > 0.
4. CI95 inferior de ese neto > 0.

**Riesgo (R1) PASA si:** IC reserva > 0 y > p95 del placebo (sin prueba de costo: no opera, informa).

**Calibración (antes de leer nada):** F5 en EURUSD tiene que mostrar información (criterio 2) y fallar el costo
(3-4), como Fase 3b. F4 no debería pasar. Un control positivo sintético (dato = retorno futuro + ruido) tiene que pasar
(test del tool). Si la calibración falla, se arregla el tool antes de leer el resto.

**Múltiples pruebas:** son ~130 celdas; con estos 4 filtros en reserva se esperan pocas pasando por azar, pero
**ninguna celda que pase se opera**: pasa a P30 = backtest de estrategia **en los instrumentos reservados** (nunca
mirados), con su propio criterio. Lo que no pase queda cerrado para esta data.
