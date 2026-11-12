# P37 — Emisión de stablecoins → retorno de BTC: criterio declarado ANTES de medir (11-nov-2026)

**Hipótesis (Griffin & Shams 2020; Lyons & Viswanath-Natraj 2023):** emitir USDT/USDC es plata nueva que entra
a comprar cripto ⇒ semanas de mucha emisión anticipan suba de BTC. Tipo **B-C** (flujo on-chain). Riesgo
conocido: la emisión puede SEGUIR al precio (causalidad inversa) ⇒ el control de momentum decide.

## Datos
- Oferta circulante diaria de USDT (id 1) + USDC (id 2), API pública de DefiLlama
  (`stablecoins.llama.fi/stablecoincharts/all?stablecoin=N`), guardada en `.cache_p37/`. Antes de declarar solo
  se verificó que la API responde.
- Precio: perpetuo BTCUSDT de Binance, apertura de velas de 8 h (cache de P15, hasta 2026-10-21) y funding real.
- Costo: **0,14% ida y vuelta** (0,05% taker + 0,02% deslizamiento por lado) + funding real cruzado (el largo
  paga los 21 fundings de la semana).

## Regla (fija)
- Grilla semanal: cada **lunes 00:00 UTC** desde 2020-01-06.
- Señal = log(S(t−1d) / S(t−8d)), con S = USDT+USDC del dato de DefiLlama fechado ese día (un día de rezago
  extra: el dato fechado el domingo se usa recién el lunes).
- **Descubrimiento** = 2020-01 → 2022-12; **reserva** = 2023-01 → 2026-10. Umbral = tercio alto (p66,7) de la
  señal en el descubrimiento (congelado).
- Señal ≥ umbral ⇒ largo BTC perpetuo de lunes 00:00 a lunes 00:00 siguiente; si no, afuera.
  Descriptivo: corto en el tercio bajo.

## Controles
- **Deriva:** largo en semanas al azar de la misma reserva (misma cantidad), 2000 repeticiones → p95.
- **Momentum (causalidad inversa):** misma regla con la señal = retorno de BTC de los 7 días previos (tercio
  alto del descubrimiento) en la misma reserva.

## Criterios (PASA = los 5, sobre la reserva salvo el 3)
1. n ≥ 40 semanas largas en la reserva.
2. Media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Descubrimiento: media neta > 0.
4. Media neta > p95 del control de deriva.
5. Media neta > media neta de la regla de momentum.

## Descriptivo (no decide)
Bruto, ganadores, por año, corto del tercio bajo, Spearman señal vs retorno siguiente y señal vs retorno de
BTC de la semana previa.

## Si PASA
No se activa. Proponer: papel en vivo + ETH como fuera de muestra.
## Si NO PASA
Cerrar emisión de stablecoins → BTC semanal. No probar otro horizonte, solo USDT, ni otro umbral.
