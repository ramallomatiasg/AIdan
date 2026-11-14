# P41 — Funding extremo como señal contraria (cripto): criterio declarado ANTES de medir (14-nov-2026)

**Hipótesis:** cuando el funding de los perpetuos está muy alto, los largos apalancados están apiñados; las
liquidaciones posteriores fuerzan ventas y el precio cae en los días siguientes (y al revés con funding muy
negativo). Es un flujo con mecanismo (escalera B-C), distinto de P15 (cobrar el funding con cobertura): acá se toma
la DIRECCIÓN contraria al apiñamiento y además se cobra el funding mientras dura.
**Riesgo declarado:** que el funding alto solo marque mercados alcistas fuertes que siguen subiendo (momentum) ⇒ el
corto pierde. Se compara contra un placebo con las mismas fechas posibles y la misma mezcla de lados.

## Datos
- `.cache_p15/{SYM}.json` (Binance, ya bajado en P15): funding real cada 8 h y precio de apertura del perpetuo cada
  8 h. **Principales: BTC y ETH.** Reservados (fuera de muestra, solo si PASA): ADA, LINK, LTC, AVAX (los de P15).
  Antes de declarar solo se miró el formato del archivo (no niveles de funding ni retornos).

## Señal (fija)
- Cada día a las 00:00 UTC: `f3` = promedio de los 9 fundings de los 3 días previos.
- Umbrales **móviles y causales** (lección de P37: un umbral fijo no es estacionario): percentil 90 y percentil 10 de
  `f3` en los 365 días previos de la misma moneda (exige ≥ 300 días de historia).
- `f3` > p90 ⇒ **corto** el perpetuo; `f3` < p10 ⇒ **largo**. Si un percentil empata con el valor (funding plano en
  0,01%), la desigualdad estricta deja la señal afuera.

## Ejecución
- Entra al precio del perpetuo de las 00:00 UTC del día de la señal, sale 7 días después a las 00:00. Una posición a
  la vez por moneda (no se superponen; mientras hay una abierta, las señales se ignoran).
- Costo: 0,07% por lado (0,14% ida y vuelta). Funding real: el corto **cobra** la suma del funding del período (paga
  si es negativo); el largo la paga.
- Resultado por operación en % neto.

## Muestras
- Descubrimiento: entradas 2020-01-01 → 2022-12-31. Reserva: entradas desde 2023-01-01 hasta la última semana completa
  del cache. BTC y ETH juntos.

## Control
- **Placebo:** 2000 réplicas con el mismo número de operaciones por moneda y lado en la reserva, en días al azar de la
  reserva (con datos completos), mismo costo y funding ⇒ percentil 95 de la media.

## Criterios (PASA = los 5, sobre la reserva salvo que diga otra cosa)
1. n ≥ 30 operaciones en la reserva (BTC+ETH).
2. Media neta por operación > 0 y extremo inferior del CI95 (bootstrap simple, 5000 réplicas) > 0.
3. Media neta > 0 también en el descubrimiento.
4. Media neta > percentil 95 del placebo.
5. Media neta del lado **corto** (el mecanismo principal) > 0 en la reserva.

## Descriptivo (no decide)
Por moneda, por lado, por año; parte del resultado que viene del funding vs del precio; fracción de días con señal.

## Si PASA
No se activa. Siguiente: monedas reservadas (mismo período completo), luego papel en vivo; propuesta al user.
## Si NO PASA
Cerrar funding extremo como señal de dirección en cripto. No probar otro percentil, otro plazo ni otra ventana de
promedio.
