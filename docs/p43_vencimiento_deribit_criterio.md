# P43 — Vencimiento mensual de opciones de Deribit y volatilidad de BTC: criterio declarado ANTES de medir (14-nov-2026)

**Hipótesis (escalera B):** los vencimientos mensuales de Deribit (último viernes del mes, 08:00 UTC) concentran
mucho interés abierto; la cobertura de gamma de los dealers "pega" el precio antes del vencimiento y lo libera
después ⇒ la volatilidad realizada es MÁS BAJA en las 48 h previas y MÁS ALTA en las 48 h posteriores que en un
viernes normal. Si pasa, sirve para ubicar en el tiempo la venta de volatilidad de P39b (vender antes del vencimiento
no; vender después). En índices el vencimiento (P32) no dio nada; en BTC el mercado de opciones pesa más.
**Riesgo declarado:** el efecto de fin de semana (el vencimiento es viernes y las 48 h posteriores tocan sábado y
domingo, que en cripto son más tranquilos) ⇒ por eso el control son los MISMOS tramos alrededor de viernes normales.

## Datos
- Binance spot BTCUSDT, velas de 1 h (API pública), desde 2019-07-01 hasta el último viernes completo.
  Antes de declarar solo se miró que la API responde.

## Medida
- Para cada viernes F a las 08:00 UTC: `RVpre` = suma de retornos log horarios al cuadrado de las 48 h previas;
  `RVpost` = de las 48 h posteriores. `L = ln(RVpost / RVpre)`.
- Vencimientos = último viernes de cada mes (los trimestrales incluidos). Viernes normales = el resto.
- Estadístico: `D = media(L | vencimiento) − media(L | normal)`.

## Muestras
- Descubrimiento: viernes de 2019-07 a 2022-12. Reserva: 2023-01 → último viernes completo.

## Criterios (PASA = los 4)
1. n ≥ 36 vencimientos en la reserva.
2. Reserva: `D` > 0 y extremo inferior del CI95 (bootstrap de los dos grupos, 5000 réplicas) > 0.
3. Descubrimiento: `D` > 0.
4. Tamaño económico: `exp(D)` ≥ 1,10 en la reserva (la varianza post/pre sube al menos 10% más que en un viernes
   normal; menos que eso no alcanza para pagar el spread de una opción, ~1 punto de vol sobre ~40-55).

## Descriptivo (no decide)
Tramos pre y post por separado (vs normales), trimestrales vs mensuales, retorno con signo en las 48 h previas
(¿el precio se mueve hacia algún lado antes?), por año.

## Si PASA
No se activa. Siguiente: medirlo en ETH (fuera de muestra) y proponer al user sumar la regla de "no vender antes del
vencimiento" al papel de P39b.
## Si NO PASA
Cerrar el vencimiento de Deribit como efecto de volatilidad/dirección en BTC. No probar otros tramos (24/72 h) ni ETH.
