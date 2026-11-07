# P25 — Cambio de mes (turn-of-the-month) en índices: criterio declarado ANTES de medir (6-nov-2026)

**Hipótesis (Ariel 1987; Lakonishok-Smidt 1988; McConnell-Xu 2008):** en EE.UU. casi todo el retorno mensual de
las acciones se concentra entre el último día hábil del mes y el 3er día hábil del siguiente (flujos de sueldos,
aportes a fondos de retiro, rebalanceos). Tipo **B** de la escalera (`docs/fuentes_de_ventaja_2026-11-04.md`):
flujo forzado de calendario, no adivina dirección intradía.

## Datos
- `.cache_p1/M15` (MT5 ICMarkets, bajado 10-oct): **US30, USTEC** (principales), **DE40** (descriptivo, otra
  sesión), may/jun-2020 → 2026-10-09. Hora del server = Nueva York + 7 h todo el año (verificado en P12).
- **US500 no está en el cache** y bajarlo exigiría MT5: queda afuera de esta corrida (se declara, no se agrega
  después de mirar).
- Costo: el mismo de P24 — swap ACTUAL de MT5 leído el 5-nov (~0,027% del precio por noche en US30/USTEC,
  ~0,023% en DE40) × noches calendario, + spread de la vela de entrada y de la de salida. Cota alta para 2020-22.

## Regla (fija, sin parámetros que buscar)
- Días hábiles = días de semana con la vela de cierre del contado en el cache (16:00 ET → 23:00 server; DE40:
  17:30 Berlín). Así los feriados quedan afuera solos.
- **Entrada:** apertura de la vela de cierre del contado del **último día hábil del mes**.
- **Salida:** apertura de la vela de cierre del contado del **3er día hábil del mes siguiente** (ventana de
  4 días hábiles: último, 1ro, 2do, 3ro).
- Retorno neto por evento en % del precio. Un evento por mes y por instrumento.

## Control (placebo)
Mismo instrumento, mismo año calendario, entrada en el cierre de un **día hábil al azar que no esté en una ventana
de cambio de mes**, salida 3 días hábiles después (misma duración en días hábiles), mismos costos (noches reales
de esa ventana). 2000 repeticiones de la media de n eventos → percentil 95. Responde: ¿la ventana es especial o es
la deriva alcista 2020-26? (lección de P9 y P24).

## Criterios (PASA = los 5)
1. n ≥ 60 eventos en US30 y en USTEC.
2. Pool US30+USTEC: media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas del pool con media neta > 0.
4. Media neta real > percentil 95 del control, en US30 **y** en USTEC.
5. US30 y USTEC con media neta > 0 cada uno.

## Descriptivo (no decide)
- Bruto (sin costos), con la mitad del swap, % de eventos ganadores.
- DE40 con su sesión.

## Si PASA
No se activa. Siguiente paso a proponer al user: papel en vivo + US500/STOXX50 nunca mirados como fuera de muestra.
## Si NO PASA
Cerrar cambio de mes en CFDs de índices con este costo. No buscar otra ventana (2, 5 o 7 días) ni otro día de entrada.
