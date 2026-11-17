# P50 — préstamo de stablecoins (Aave v3) contra la letra del Tesoro — criterio declarado ANTES de medir

**Fecha:** 16-nov-2026 (investigación diaria). **Tool:** `tools/backtest_p50_prestamo_stablecoins.py` (read-only,
sin MT5, no toca la DB).

## Pregunta

Los apalancados de cripto toman prestado stablecoins y pagan interés. ¿Prestar USDC/USDT en Aave paga un premio
neto sobre la letra del Tesoro a 3 meses, y el peor episodio (el depeg de USDC de mar-2023) entra en un límite
aceptable? Es la versión más simple del premio de cripto y no requiere adivinar precios.

## Datos (verificados el 16-nov, antes de medir; solo se miró el rango de fechas y el TVL)

- APY diario de suministro (`apyBase`) de Aave v3 Ethereum, mercado principal: USDC
  `aa70268e-4b52-42bf-a116-608b370f9501` y USDT `f981a304-bb6c-45b8-b0c5-fd2f515ad23a` (DefiLlama yields, desde
  6/13-feb-2023). Cache `.cache_p50/`.
- Letra a 3 meses: FRED `DTB3` (diaria, rendimiento de descuento; se usa tal cual).
- Precio diario de USDC y USDT en USD: DefiLlama coins (para medir el depeg).

## Regla (congelada)

Cartera 50% USDC + 50% USDT prestados en Aave v3 todo el período (sin rotar). Cada día acumula `apyBase/365`.
Costo: **$10 de gas por año sobre una posición de $1.000** (depósito + retiro) ⇒ 1%/año (conservador para gas de
2024-26). Premio diario = (APY − DTB3) / 365 − costo/365.

## Muestra

- **Descubrimiento:** 13-feb-2023 → 31-dic-2023 (incluye el depeg de USDC). **Reserva (solo si pasa):**
  1-ene-2024 → 15-nov-2026.

## Criterio de PASA (descubrimiento, todos)

1. Premio anualizado neto sobre la letra > 0.
2. CI95 por bootstrap en bloques de 30 días: límite inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Caída máxima del valor en USD (con el precio diario de las stablecoins) < 15%.

**Reserva:** premio anualizado neto > 0. **Descriptivo:** cada moneda sola, el premio por año, sin gas.

**Si no pasa:** cerrado el préstamo pasivo de stablecoins en Aave como premio sobre la letra; no se busca el mejor
mercado, cadena ni moneda.

## Límites

- Riesgo de contrato de Aave y de la emisora de la stablecoin, no modelado más allá del precio diario.
- El user (Argentina) no compra letras directamente: la letra es la vara de la tasa libre, no una alternativa
  real de inversión para él.
- La APY de DefiLlama es la publicada por el protocolo, no la realizada por un depósito concreto.
