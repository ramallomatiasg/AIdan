# P21 — carry de funding (P15) en Hyperliquid y en el diferencial entre exchanges — criterio declarado ANTES de medir

**Fecha:** 31-oct-2026 (rutina semanal, primera propuesta abierta de `docs/propuestas_registro.md`).
**Tool:** `tools/backtest_p21_hyperliquid.py` (read-only, sin MT5, no toca la DB). Baja datos PÚBLICOS de
Hyperliquid (`api.hyperliquid.xyz/info`: `fundingHistory` horario y `candleSnapshot` de 8 h) a `.cache_p21/`;
reusa el cache de Binance de P15 (`.cache_p15/`, spot y perpetuo de 8 h + funding).

## Pregunta

P15 (carry de funding en Binance) pasó, también fuera de muestra, pero en 2025-26 quedó por debajo de la tasa
libre. Hyperliquid cobra funding cada HORA y tiene otro público (más apalancado). **(A)** ¿el mismo carry, con el
perpetuo vendido en Hyperliquid, le gana a la tasa libre? **(B)** ¿cobrar el diferencial de funding entre los dos
exchanges (perpetuo vendido donde más paga, comprado donde menos) es un premio aparte?

## Período y universo (data verificada el 31-oct, antes de medir)

- Funding de Hyperliquid disponible desde el **12-may-2023** ⇒ período **2023-05-12 → 2026-10-22** (el corte de
  P15), ~3,4 años. Una moneda entra desde su primer funding en Hyperliquid + 7 días.
- **Principal:** BTC, ETH, SOL, BNB, XRP, DOGE (las mismas de P15).
- **Reservados (solo si pasa):** ADA, LINK, LTC, AVAX.

## Reglas (congeladas, las de P15 salvo lo marcado)

**(A) carry en Hyperliquid:** spot comprado en Binance + perpetuo vendido en Hyperliquid por el mismo nocional.
- Decisión cada 8 h (00/08/16 UTC) con el funding conocido hasta ese momento.
- Señal: media del funding horario de Hyperliquid de los últimos 7 días, expresada por cada 8 h (suma / 21).
  Entrar si ≥ 0,005%, salir si < 0.
- Precios: open de la vela de 8 h (spot Binance, perpetuo Hyperliquid). Funding cobrado proporcional al precio
  del perpetuo / el de entrada (precio de la vela de 8 h que contiene el cobro).
- Capital 2 × nocional; rebalanceo (cerrar y reabrir) si el spot se mueve ±50%.
- **Costo:** spot 0,10% + perpetuo Hyperliquid 0,045% (taker, nivel base) por lado + 0,02% de deslizamiento por
  lado y pata ⇒ **0,37%** del nocional por ida y vuelta.

**(B) diferencial:** perpetuo comprado en Binance + perpetuo vendido en Hyperliquid.
- Señal: media de 7 días de (funding Hyperliquid − funding Binance), por cada 8 h. Entrar si ≥ 0,005%, salir
  si < 0. Solo esa dirección (la inversa sería otra hipótesis).
- Resultado: funding Hyperliquid cobrado − funding Binance pagado + base (perp_BN/entrada − perp_HL/entrada).
- **Costo:** 0,05% (Binance perp) + 0,045% (Hyperliquid) por lado + 0,02% por lado y pata ⇒ **0,27%**.
- Capital 2 × nocional (margen 100% en cada pata), mismo rebalanceo.

## Criterio de PASA (cada variante por separado, cartera de las 6 principales, los 5 de P15)

1. Rendimiento anualizado sobre el capital > tasa libre media del período (`docs/p11_policy_rates.csv`, USD).
2. CI95 por bootstrap en bloques de una semana: límite inferior > 0.
3. > 0 en las dos mitades cronológicas.
4. Caída máxima < 10%.
5. ≥ 4 de 6 monedas con neto > 0.

**Descriptivo (no decide):** P15 en Binance sobre el MISMO período (para saber si Hyperliquid mejora algo),
"siempre adentro", por año.

**Si pasa (A o B):** reservados una vez (> 0 y > tasa libre); después shadow en papel como P19.
**Si no pasa:** cerrado el carry de funding en Hyperliquid y el diferencial BN-HL sobre esta data; no se barren
umbrales, ventana ni monedas.

## Límites

- Riesgo de exchange (dos venues: el doble de superficie) y de puente (USDC a Hyperliquid) no modelados.
- Hyperliquid es un exchange on-chain: el deslizamiento real en monedas chicas puede ser mayor que 0,02%.
- Las velas de 8 h no ven el precio exacto de cada cobro horario.
