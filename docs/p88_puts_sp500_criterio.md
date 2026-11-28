# P88 — Vender puts cubiertos del S&P 500 (índice CBOE PutWrite `^PUT`) contra SPY: criterio declarado ANTES de medir (27-nov-2026)

**Hipótesis:** la volatilidad implícita del índice paga, en promedio, más que la realizada (premio por vender seguro
contra caídas) ⇒ vender cada mes un put ATM a 1 mes con la plata en letras rinde más por unidad de riesgo que tener el
índice. Tipo **A**. Sin apalancamiento (distinto de P16). Riesgo: es casi "SPY con menos subida" y cae en 2008.

## Datos (verificado antes de declarar: solo filas y fechas, **ningún retorno mirado con esta regla**)
- `^PUT` (índice de retorno total de la estrategia, Yahoo, 2-ago-1996 → 27-nov-2026) y SPY ajustado (Yahoo). Cache
  `.cache_p88/`. Letra: FRED `DTB3` (cache de P50).
- El índice no tiene costos de transacción. **Costo de replicarlo:** 0,05% por mes (spread del put vendido; pesimista
  0,15% por mes).

## Muestra
- Retornos mensuales de fin de mes a fin de mes. **Descubrimiento:** ene-1997 → dic-2010 (incluye 2000-02 y 2008).
  **Reserva:** ene-2011 → oct-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 6)
1. Sharpe PUT − Sharpe SPY > 0 (exceso mensual sobre la letra, ×√12, con costo base).
2. CI95 de esa diferencia por bootstrap en bloques de 6 meses (5000, mismos meses): inferior > 0.
3. Diferencia > 0 en las dos mitades cronológicas.
4. Diferencia > 0 con el costo pesimista.
5. Exceso medio de PUT sobre la letra > 0 con CI95 (bloques de 6) inferior > 0.
6. Caída máxima de PUT ≤ caída máxima de SPY.

**Reserva:** criterios 1, 2 y 5.

## Descriptivo (no decide)
Retorno anual, vol, caída máx; alfa y beta contra SPY; por década; peor mes.

## Si PASA
No se activa. Reserva y propuesta (vender un put mensual o ETF que lo replique; capital mínimo real: un put de SPY
cubierto necesita ~100 × precio de SPY ⇒ con $500-1.000 no entra; habría que ver ETF o mini-opciones).
## Si NO PASA
Cerrado vender puts del índice sin apalancamiento; no se prueban otros strikes, plazos, BXM (calls cubiertos) ni filtros.
