# P18 — sesgo favorito-longshot en mercados de predicción — criterio declarado ANTES de medir

**Fecha:** 28-oct-2026 (rutina semanal, Parte 3: P18 es la primera de la cola que se puede ejecutar; P7 espera
a Leo y P8 está bloqueada por muestra). **Tool:** `tools/backtest_p18_kalshi.py` (read-only, sin MT5, no toca
la DB de AIdan). Baja datos PÚBLICOS de la API de Kalshi a `.cache_p18/`.

## Pregunta

En apuestas está documentado que los longshots se sobrepagan y los favoritos se subpagan. **¿Comprar el lado
favorito (precio 0,90-0,97) unas horas antes del cierre deja ganancia neta de comisión en Kalshi?**

## Cambios declarados respecto de la propuesta original (por acceso a datos, no por mirar resultados)

- **Kalshi en vez de Polymarket:** `polymarket.com` y sus APIs no resuelven DNS desde esta red (28-oct). Kalshi
  sí, y su API pública trae el histórico (`/historical/markets`, cutoff 29-ago-2026) con velas de 1 hora que
  incluyen **bid y ask** ⇒ se compra al ask real, no al último precio.
- **Ancla sin mirar el futuro:** muchos mercados cierran antes cuando el evento ocurre (`can_close_early`).
  Medir "6 h antes del cierre real" usaría la hora de cierre, que no se conoce de antemano. Se ancla en
  `expected_expiration_time` (programada, conocida al abrir) y se exige que el mercado siga abierto en ese
  momento. Si cerró antes, no se podía operar ⇒ se excluye (no es selección sobre el resultado).
- **Se puede operar desde Argentina:** sin verificar. Es condición para cualquier shadow, no para medir.

## Universo y datos

- Series de Kalshi ordenadas por volumen total (`/series?include_volume=true`), sin las multivariadas
  (`KXMVE*`) y sin las que no tienen mercados en el período.
- **Principal:** las 40 primeras series. **Reservadas (no se miran salvo que el principal PASE):** las
  series 41-100.
- Período: mercados liquidados con `expected_expiration_time` entre **2025-10-01 y 2026-08-28** (cutoff del
  histórico).
- Muestreo fijo (semilla 20261028): hasta **150 eventos por serie**, y por evento hasta los **6 mercados** de
  mayor volumen.
- Se excluyen mercados que duran menos de 24 h (`open_time` → `expected_expiration_time`): el horizonte de
  6 h no existe en los de 15 minutos o 1 hora.

## Regla (congelada)

- **Momento de entrada E** = `expected_expiration_time` − **6 h**. Vela = la última vela de 1 h con
  `end_period_ts` ≤ E. El mercado tiene que estar abierto en E (`close_time` > E).
- Precios: ask del SÍ = `yes_ask.close`; ask del NO = 1 − `yes_bid.close`. Se exige bid > 0, ask < 1 y
  spread (ask − bid del SÍ) ≤ 0,03.
- **Señal:** se compra el lado (SÍ o NO) cuyo ask esté en **[0,90, 0,97]**.
- **Comisión de Kalshi (taker):** `fee_multiplier` de la serie × P × (1 − P) por contrato (fórmula pública,
  multiplicador estándar 0,07; se usa el de cada serie). Sin redondeo (se asume orden de ≥100 contratos).
- **Resultado por mercado** (por dólar invertido) = (1 si gana, 0 si pierde − ask − comisión) / ask.
- **Una observación por evento:** si varios mercados del mismo evento dan señal, se promedian (están
  correlacionados).

## Control

La hipótesis nula es que el precio está bien calibrado: si el favorito a 0,93 gana el 93% de las veces, el
retorno esperado es −comisión/ask (negativo). El criterio exige ganarle a eso y además ser positivo neto.

## Criterio de PASA (los 5, sobre el principal)

1. n ≥ 300 eventos con señal.
2. Media neta > 0 con **CI95 por bootstrap agrupado por semana** cuyo límite inferior > 0.
3. Media neta > 0 en las dos mitades cronológicas.
4. Media neta > 0 sacando la serie que más aporta (que no sea una sola serie).
5. Media neta > 0 en los últimos 3 meses (desde 2026-06-01).

Descriptivos (no deciden): el lado longshot (ask ≤ 0,10), entrada a 1 h y a 24 h, por categoría, tabla de
calibración (precio vs acierto real por tramo).

**Si pasa:** reservadas (41-100) una vez con la misma regla; si también pasa, verificar acceso desde
Argentina y armar un shadow en papel sobre la API en vivo (como P13b/P19). **Si no pasa:** cerrado el
favorito-longshot en Kalshi con esta definición; no se barren el tramo de precio, el horizonte ni el universo.
