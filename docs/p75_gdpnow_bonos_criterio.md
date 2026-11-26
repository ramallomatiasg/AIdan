# P75 — Cambio semanal del GDPNow → bonos (IEF) la semana siguiente: criterio declarado ANTES de medir (25-nov-2026)

**Hipótesis:** el GDPNow de la Fed de Atlanta resume los datos de actividad que van saliendo. Si el mercado de bonos
los incorpora con retraso, una suba del nowcast en la semana anticipa tasas más altas (bonos abajo) la semana
siguiente, y una baja lo contrario. Tipo **C** (información). Prior bajo: el mercado ve los mismos datos en el momento.

## Datos (solo se verificó la URL; ningún valor del nowcast ni retorno mirado con esta señal)
- `GDPTrackingModelDataAndForecasts.xlsx` (Fed de Atlanta, página del GDPNow), hoja de archivo con el nowcast por fecha
  de publicación y trimestre objetivo. Cache `.cache_p75/`.
- IEF (bonos del Tesoro 7-10 años), cierre ajustado diario de Yahoo (el cache de P64, `.cache_p64/IEF.json`).

## Regla (fija)
- `N(d, q)` = último nowcast publicado con fecha ≤ d para el trimestre q.
- Cada viernes F (o el último día hábil de la semana con precio de IEF): `q` = trimestre objetivo del último nowcast
  publicado con fecha ≤ jueves de esa semana. **Señal** = `N(jueves de la semana, q) − N(jueves de la semana previa, q)`.
  Si no hay nowcast de q en el jueves previo (cambió el trimestre en la semana) ⇒ sin posición. Si la señal es 0 ⇒ sin
  posición. (Se usa el jueves para que ninguna publicación del viernes pueda estar después del cierre.)
- Señal > 0 ⇒ **corto IEF**; señal < 0 ⇒ **largo IEF**, del cierre del viernes F al cierre del viernes siguiente.
- **Costo:** 0,05% por lado × |posición nueva − posición vieja| (pesimista 0,10%).

## Placebo
200 placebos: a cada semana con señal se le asigna la señal de otra semana al azar (semilla 20261125). Se compara el
retorno BRUTO medio.

## Muestra
- **Descubrimiento:** viernes desde el inicio del archivo (2011) hasta el 27-dic-2019. **Reserva:** 2020 → nov-2026,
  solo si pasa. *Ojo:* antes de mediados de 2014 el GDPNow no se publicaba en vivo (el archivo es una reconstrucción
  en tiempo real) ⇒ se reporta aparte 2014-07 → 2019 como descriptivo.

## Criterios (descubrimiento; PASA = los 5)
1. ≥150 semanas con posición.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000) con inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Retorno bruto medio > p95 de los 200 placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Acierto, por año, largo vs corto por separado, sesgo de la muestra (IEF largo siempre), correlación con el retorno de
IEF de la semana de la señal.

## Si PASA
No se activa nada; reserva y propuesta al user. Automatizable con un ETF (o futuros de bonos).
## Si NO PASA
Cerrado el GDPNow como señal semanal para bonos; no se prueban otros plazos, umbrales, TLT ni la semana misma.
