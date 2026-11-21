# P61 — sUSDe de Ethena contra la letra: criterio declarado ANTES de medir (20-nov-2026)

**Hipótesis:** tener sUSDe (USDe en staking) cobra el funding de los cortos de Ethena sin operar nada y rinde más que
la letra del Tesoro a 3 meses, también fuera de muestra. Es el carry de P15 (lo único que pasó en el proyecto)
empaquetado. Tipo **A** (premio por riesgo).

## Datos (verificado antes de declarar que responden; **ningún precio ni rendimiento mirado**)
- **Precio diario de sUSDe en USD:** DefiLlama coins `coingecko:ethena-staked-usde` (desde 2024-03-20). Medir el precio
  en USD (no el APY publicado) incluye a la vez el rendimiento y cualquier despegue de USDe. Cache `.cache_p61/`.
- **Letra:** FRED DTB3 (`.cache_p50/dtb3.json`, se re-baja si no cubre el período).
- Descriptivo: APY publicado del pool de Ethena en DefiLlama yields (`66985a81-…`), solo para comparar.

## Regla
- Tramos de 28 días no solapados desde el primer día con precio. Retorno del tramo = precio final / precio inicial − 1.
- Premio del tramo = retorno − (letra media del tramo + costo) × días/365.
- **Costo:** 0,5%/año (compra/venta en Curve o Binance + gas, amortizado en ~1 año de tenencia). Pesimista 1,5%/año.
- Premio anual = suma de premios / suma de días × 365.

## Muestra
- **Descubrimiento:** tramos que arrancan 2024-03-20 → 2024-12-31. **Reserva:** 2025-01-01 → hoy, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Premio anual > 0.
2. CI95 por bootstrap en bloques de 3 tramos (5000, semilla fija) con inferior > 0.
3. Las dos mitades cronológicas > 0.
4. Caída máxima del precio de sUSDe (diaria, desde máximo) < 10%.
5. Premio > 0 con el costo pesimista.

**Reserva (más estricta que P57, por la cantidad de "rendimientos" probados):** premio > 0 **y** CI inferior > 0 **y**
caída máxima < 10%.

## Descriptivo (no decide)
Rendimiento por año, APY publicado medio, peor día.

## Límites
- El precio de CoinGecko es un agregado: un despegue en un solo exchange (oct-2025) puede no verse completo.
- La serie no mide el riesgo de contrato ni de custodia de Ethena (exchanges donde tiene los cortos).
- El cooldown de unstake (7 días) se ignora: se asume salida por mercado secundario.

## Si PASA
No se activa. Papel con la cuota diaria 3 meses, monto mínimo y peor caso en USD, decisión del user.
## Si NO PASA
Cerrado sUSDe; no se prueban otros períodos, tokens de Ethena (USDtb, etc.) ni filtros por funding.
