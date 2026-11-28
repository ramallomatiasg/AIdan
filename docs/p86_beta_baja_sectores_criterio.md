# P86 — Beta baja en sectores (Frazzini & Pedersen 2014): criterio declarado ANTES de medir (27-nov-2026)

**Hipótesis:** los inversores que no pueden apalancarse compran lo de beta alta y lo encarecen ⇒ lo de beta baja rinde
más por unidad de riesgo. Tipo **A** (premio por riesgo). Se mide en los 9 SPDR sectoriales originales, sin
apalancamiento (entra con $500). Prior medio-bajo: en sectores "beta baja" puede ser solo "defensivos".

## Datos (verificado antes de declarar: solo filas y fechas, **ningún retorno mirado con esta regla**)
- XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY y SPY: cierre ajustado diario de Yahoo, 22-dic-1998 → 25-nov-2026
  (7.025 días los sectores). Cache `.cache_p86/` (`tools/fetch_p86_p88_cache.py`).
- Letra a 3 meses: FRED `DTB3` (cache de P50), último dato disponible hacia atrás, /252 por día.

## Regla (fija)
- Al cierre del último día hábil de cada mes: beta de cada sector contra SPY con los últimos 252 retornos diarios simples
  (cov/var). Se compran a peso igual (1/3) los 3 de beta más baja para el mes siguiente; se rebalancea a 1/3 cada mes.
- **Costo:** 0,05% × Σ|peso nuevo − peso viejo (derivado)| en cada rebalanceo (pesimista 0,10%). SPY sin costo.
- Sharpe = media / desvío del exceso mensual sobre la letra × √12.

## Muestra
- **Descubrimiento:** meses ene-2000 → dic-2012 (la primera beta usa 1999). **Reserva:** ene-2013 → oct-2026, solo si
  pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Sharpe beta baja − Sharpe de SPY > 0.
2. CI95 de esa diferencia por bootstrap en bloques de 6 meses (5000, mismos meses para los dos): inferior > 0.
3. Diferencia > 0 en las dos mitades cronológicas.
4. Diferencia > 0 con el costo pesimista.
5. Placebo: el Sharpe de beta baja supera el p95 de 1000 carteras de 3 sectores elegidos al azar cada mes (mismo costo).

**Reserva:** criterios 1 y 2.

## Descriptivo (no decide)
Retorno anual, vol, caída máx; alfa y beta contra SPY; los 9 a peso igual; rotación; qué sectores entran más seguido;
por década.

## Si PASA
No se activa. Reserva y propuesta al user (regla mensual con 3 ETFs, automatizable con broker de comisión cero).
## Si NO PASA
Cerrado beta baja en sectores; no se prueban otras ventanas de beta, otra cantidad de sectores, pesos por beta ni
apalancamiento.
