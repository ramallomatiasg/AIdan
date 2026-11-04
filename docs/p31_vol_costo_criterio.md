# P31 — ¿el movimiento esperado al entrar separa las operaciones de AIdan que ganan de las que pierden? — criterio declarado ANTES de medir

**Fecha:** 4-nov-2026. **Origen:** P29 (`docs/propuestas_registro.md`): la dirección casi no se puede predecir, pero
la **volatilidad sí** (IC 0,15-0,44 fuera de muestra en 30 de 33 celdas). Idea: no operar cuando el movimiento
esperado no alcanza a pagar el costo. **Tool:** `tools/backtest_p31_vol_cost.py` (read-only: DB `mode=ro`, sin MT5,
velas del cache M1 de P23).

## Datos

- **Todos los trades reales** de `trade_archive` con `mt5_pnl`, del 20-abr al 9-oct-2026 (737; el cache M1 termina el
  9-oct). Resultado = `mt5_pnl` del broker.
- **Dato al entrar:** rango medio (máximo − mínimo) de las **16 velas M15 cerradas antes de la entrada**, en pips
  (lo mismo que R1 en P29). Desfase AR → servidor +6 h (verificado en P27).

## Regla (fija)

- Partición cronológica: **primera mitad** (ajuste) / **segunda mitad** (prueba).
- En la primera mitad se calcula el **corte del tercio inferior** del dato. "Movimiento bajo" = dato ≤ ese corte.
- En la segunda mitad se compara el PnL medio por trade de "movimiento bajo" contra el resto.

## Criterio (las 5; NO mover)

1. n de la segunda mitad ≥ 300.
2. En la segunda mitad, PnL medio de "movimiento bajo" < PnL medio del resto, con CI95 bootstrap de la diferencia
   cuyo extremo superior < 0.
3. Misma dirección en la primera mitad.
4. PnL medio de "movimiento bajo" en la segunda mitad < 0 (o sea, sacarlos mejora el total).
5. Placebo: con el dato desordenado entre trades (500 permutaciones), la diferencia real queda por debajo del p5.

**Descriptivo:** por track; m15 tiene piso de ATR fijo desde el 16-ago (sus trades posteriores ya vienen filtrados).

**Pasa ⇒** proponer el filtro en papel en vivo (registrar el dato en cada señal, sin bloquear) y recién después, con
OK, activarlo por env. **No pasa ⇒** la volatilidad no ayuda a elegir operaciones de AIdan; no se barren ventanas ni
cortes sobre estos trades.
