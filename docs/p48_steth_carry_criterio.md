# P48 — carry de funding de P15 en ETH con la pata larga en stETH — criterio declarado ANTES de medir

**Fecha:** 16-nov-2026 (investigación diaria). **Tool:** `tools/backtest_p48_steth_carry.py` (read-only, sin MT5,
no toca la DB). Motor `simulate` de P15 importado, sin cambios.

## Pregunta

P15 (spot comprado + perpetuo vendido en Binance) cayó casi a cero en 2025-26 porque bajó el funding. Si la pata
larga es stETH en vez de ETH, se cobra además el rendimiento del staking de Lido (~2-4%/año) que no depende del
funding. ¿Eso alcanza para ganarle a la tasa libre, también en 2025-26, sin que el descuento de stETH (jun-2022)
se coma el premio?

## Datos (verificados el 16-nov, antes de medir)

- ETH spot y perpetuo de 8 h + funding de Binance: `.cache_p15/ETH.json` (el de P15).
- APR diario de Lido stETH: `yields.llama.fi/chart/747c1d2a-c668-4682-b9f9-296708a3dd90` (DefiLlama, desde
  3-may-2022).
- Precio diario de stETH y de ETH en USD: `coins.llama.fi/chart` (DefiLlama) ⇒ cociente stETH/ETH por día.
- Cache en `.cache_p48/`.

## Regla (la de P15, congelada)

Señal y umbrales de P15 (media de funding de 7 días ≥ 0,005% por 8 h para entrar, < 0 para salir), decisión cada
8 h, capital 2 × nocional, rebalanceo ±50%. Única diferencia: la pata larga vale
`ETH_spot(t) × (stETH/ETH)(día) × crecimiento_del_staking(día)`, donde el crecimiento acumula el APR diario de Lido
(stETH rebasa: el saldo crece). Costo: el de P15 (0,38%) + 0,05% por lado por el swap ETH↔stETH ⇒ **0,48%** de ida
y vuelta.

## Muestra

- **Descubrimiento:** 10-may-2022 (APR + 7 días) → 31-dic-2024 (incluye el descuento de jun-2022).
- **Reserva:** 1-ene-2025 → 22-oct-2026 (el tramo donde P15 no le ganó a la tasa libre). Se mira solo si pasa el
  descubrimiento.

## Criterio de PASA (descubrimiento, todos)

1. Rendimiento anualizado sobre el capital > tasa libre media del período (`docs/p11_policy_rates.csv`, USD).
2. CI95 por bootstrap en bloques de una semana: límite inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Caída máxima < 10%.

**Reserva:** anualizado > tasa libre media de 2025-26. **Descriptivo (no decide):** P15 en ETH sin staking en los
mismos tramos, cuánto aporta el staking, el mínimo del cociente stETH/ETH, "siempre adentro".

**Si no pasa:** cerrado el carry de funding con stETH sobre esta data; no se barren umbrales ni se cambia de token
de staking.

## Límites

- Una sola moneda (ETH) ⇒ no hay criterio de "monedas > 0".
- El cociente sale de dos precios diarios con horarios no idénticos (ruido de ±0,3%).
- No se modela el riesgo de contrato de Lido ni la cola de retiro (días) si se sale por el protocolo.
