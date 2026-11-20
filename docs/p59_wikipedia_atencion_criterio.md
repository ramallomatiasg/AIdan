# P59 — Atención en Wikipedia → reversión de las alts (semanal, neutral al mercado): criterio declarado ANTES de medir (19-nov-2026)

**Hipótesis:** un salto de atención minorista (vistas de la página de Wikipedia de la moneda) empuja el precio por
encima de lo que vale y la semana siguiente revierte (Da, Engelberg y Gao 2011 en acciones). El dato de vistas no está
en el precio. Tipo **C** (información). Nunca medido acá.

## Datos (verificado antes de declarar que las fuentes responden; **ningún precio ni vista mirados**)
- **Universo:** perpetuos USDT de Binance (fapi `exchangeInfo` actual + la lista histórica de símbolos de P56,
  incluye los deslistados), `underlyingType = COIN`.
- **Nombre de la moneda:** `assetName` de la lista pública de activos de Binance (`bapi/asset/v2/public/asset/asset/get-all-asset`).
- **Mapeo moneda → artículo (regla fija, aplicada sin mirar vistas ni precios):** se prueban en orden los títulos
  `<Nombre> (cryptocurrency)`, `<Nombre> (blockchain)`, `<Nombre> (blockchain platform)`, `<Nombre>` en la API REST de
  Wikipedia en inglés (`page/summary`, sigue redirecciones); se acepta el primero que exista, no sea desambiguación y
  cuyo resumen contenga `cryptocurrency`, `blockchain`, `token` o `coin`. Dos monedas con el mismo artículo ⇒ quedan
  afuera las dos. La lista se guarda (`.cache_p59/mapping.json`) antes de bajar vistas o precios.
- **Vistas:** Wikimedia pageviews `per-article/en.wikipedia/all-access/user/<artículo>/daily`. **Precios:** velas
  diarias de fapi (open) y funding real. Cache `.cache_p59/`.

## Regla
- Semanas que arrancan el lunes 00:00 UTC. Para la semana t: vistas de los 7 días que terminan el domingo anterior
  (V₁) contra la media semanal de las 8 semanas previas a esa (V₈). Señal = log(V₁ / V₈). Solo cuentan monedas con
  V₈ ≥ 700 vistas/semana, perpetuo vivo con volumen el lunes t y el lunes t+1 (o su última vela) y ≥ 30 días listado.
- Hacen falta ≥ 10 monedas elegibles; k = max(2, ⌊n/5⌋). Las k con señal MÁS ALTA ⇒ **corto**; las k con señal MÁS
  BAJA ⇒ **largo**; peso igual, del open del lunes t al open del lunes t+1, funding real (el largo paga, el corto cobra).
- Retorno semanal = media de las patas largas + media de las patas cortas ($1 por lado).
- **Costo:** 0,10% por cada entrada o salida de una moneda (taker 0,05% + deslizamiento 0,05%), sobre el cambio real
  de la cartera de cada lado. Pesimista: 0,20%.

## Muestra
- **Descubrimiento:** semanas 2020-01-06 → 2023-12-25. **Reserva:** 2024-01-01 → 2026-11-09, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥ 100 semanas con cartera.
2. Retorno semanal neto medio > 0 y CI95 por bootstrap en bloques de 4 semanas (5000, semilla fija) con inferior > 0.
3. Las dos mitades cronológicas > 0.
4. Media > 0 con el costo pesimista.
5. **Placebo desplazado:** la media bruta real supera el percentil 95 de 200 placebos donde la serie de señales de cada
   moneda se desplaza circularmente un número al azar de semanas (≥ 26) — misma distribución de señales, timing roto.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Pata larga y corta por separado, cantidad media de monedas, por año, la versión al revés (momentum de atención) solo
como signo.

## Límites
- El mapeo por nombre pierde monedas sin artículo propio (quedan las grandes y conocidas): el universo es chico.
- Wikipedia en inglés es un proxy parcial de la atención (no mide Twitter/Telegram).
- Precio del perpetuo, no spot; las alts deslistadas entran si Binance sirve sus velas.

## Si PASA
No se activa. Reserva; después papel semanal con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrada la atención en Wikipedia; no se prueban otras ventanas, umbrales, idiomas ni el signo contrario.
