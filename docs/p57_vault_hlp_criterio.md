# P57 — Vault HLP de Hyperliquid contra la letra del Tesoro: criterio declarado ANTES de medir (18-nov-2026)

**Hipótesis:** el vault HLP (market making y liquidaciones de la casa en Hyperliquid) cobra un premio estructural
(spread + liquidaciones) que paga más que la tasa libre, sin adivinar precios: depositar USDC y esperar. Tipo **A**
(premio por riesgo). Sirve con $500-1.000. Nunca medido acá.

## Datos (verificado antes de declarar: solo cantidad de puntos y fechas, **ningún valor mirado**)
- API pública de Hyperliquid, `info` → `vaultDetails` del vault `0xdfc24b077bc1425ad1dea75bcb6f8158e10df303`
  ("Hyperliquidity Provider (HLP)"), serie `allTime`: `accountValueHistory` y `pnlHistory` (PnL acumulado),
  103 puntos cada ~14 días del 10-may-2023 al 19-nov-2026. Cache `.cache_p57/hlp_vaultDetails.json` (bajado el 18-nov).
- Letra a 3 meses: FRED `DTB3` (la misma de P50).

## Cálculo
- Rendimiento de cada tramo entre dos puntos = ΔPnL / valor de la cuenta al inicio del tramo (ponderado en el tiempo:
  saca el efecto de depósitos y retiros, suponiendo que entran en los puntos de la serie).
- Premio del tramo = rendimiento − DTB3 media del tramo × días/365 − costo × días/365.
- **Costo:** 1%/año (puente y retiro ~$10/año sobre $1.000, igual que P50). Sin comisión del vault (HLP no cobra a
  los depositantes).
- Índice de la cuota = producto de (1 + rendimiento) ⇒ caída máxima.

## Muestra
- **Descubrimiento:** tramos que arrancan del 10-may-2023 al 31-dic-2024. **Reserva:** 2025 → nov-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. Premio anualizado neto sobre la letra > 0.
2. CI95 por bootstrap en bloques de 4 tramos (~8 semanas), 5000 remuestreos: límite inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Caída máxima del índice de la cuota < 15%.
5. Peor tramo de ~14 días > −10%.

**Reserva:** premio anualizado neto > 0 y caída máxima < 15% (incluye el episodio JELLY de mar-2025).

## Descriptivo (no decide)
Rendimiento anual por año, peor tramo y su fecha, tamaño del vault, cuántos tramos negativos.

## Límites
- La serie viene muestreada cada 14 días: no ve caídas intra-tramo (una pérdida que se recupera dentro de 2 semanas
  no aparece). El rendimiento por tramo es una aproximación del rendimiento de la cuota si los flujos no caen justo
  en los puntos.
- Riesgo de contrato/exchange (Hyperliquid, puente de Arbitrum) no modelado: es la cola que la serie no muestra.
- Retiros del HLP tienen bloqueo de 4 días.
- El user no compra letras: la letra es la vara de la tasa libre.

## Si PASA
No se activa. Reserva; después papel (seguir la cuota en vivo) con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrado HLP como premio sobre la letra; no se miran otros vaults de Hyperliquid.
