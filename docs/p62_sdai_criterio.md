# P62 — Tasa de ahorro de Sky (sDAI) contra la letra: criterio declarado ANTES de medir (20-nov-2026)

**Hipótesis:** la tasa de ahorro que fija el protocolo (DSR, pagada con sus ingresos) rinde más que la letra del Tesoro
a 3 meses, también fuera de muestra. Tipo **A**. Se lee junto con P57/P58/P61: con varios "rendimientos" probados,
alguno puede pasar el descubrimiento por azar ⇒ manda la reserva.

## Datos (verificado antes de declarar que responden; **ningún precio ni rendimiento mirado**)
- **Precio diario de sDAI en USD:** DefiLlama coins `coingecko:savings-dai` (desde 2023-10-12). El precio en USD incluye
  el rendimiento y cualquier despegue de DAI. Cache `.cache_p62/`.
- **Letra:** FRED DTB3 (`.cache_p50/dtb3.json`).
- Descriptivo (no decide): sUSDS (`ethereum:0xa3931d71…`, desde 2024-10-09) en la reserva, porque es el producto que hoy
  se compraría.

## Regla (idéntica a P61)
- Tramos de 28 días no solapados. Premio = retorno − (letra media + costo) × días/365.
- **Costo:** 0,3%/año (gas + swap DAI/USDC, amortizado). Pesimista 1%/año.

## Muestra
- **Descubrimiento:** tramos que arrancan 2023-10-12 → 2024-12-31. **Reserva:** 2025-01-01 → hoy, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Premio anual > 0.
2. CI95 bootstrap en bloques de 3 tramos (5000, semilla fija) con inferior > 0.
3. Las dos mitades cronológicas > 0.
4. Caída máxima del precio de sDAI < 5%.
5. Premio > 0 con el costo pesimista.

**Reserva:** premio > 0 **y** CI inferior > 0 **y** caída máxima < 5%.

## Límites
- El precio de CoinGecko es un agregado de mercados; el riesgo de contrato de Sky no está en la serie.
- n chico en el descubrimiento (~16 tramos).

## Si PASA
No se activa. Papel 3 meses, monto mínimo, decisión del user.
## Si NO PASA
Cerrada la tasa de ahorro de Sky; no se prueban sUSDS como principal, stUSDS ni otros períodos.
