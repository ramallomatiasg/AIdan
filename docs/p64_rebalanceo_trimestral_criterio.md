# P64 — Rebalanceo de fondos de mezcla fija a fin de TRIMESTRE (acciones contra bonos): criterio declarado ANTES de medir (23-nov-2026)

**Hipótesis:** los fondos con mezcla fija (60/40, fondos de fecha objetivo, pensiones) rebalancean al cierre del
trimestre: si en el trimestre las acciones le ganaron a los bonos, TIENEN que vender acciones y comprar bonos (y al
revés). Ese flujo es predecible ⇒ en los últimos días del trimestre lo que subió más debería rendir menos que lo otro
(Harvey, Mazzoleni y Melone 2025, "The Unintended Consequences of Rebalancing"). Tipo **B** (flujo forzado). Distinto
de P60 (duración de bonos todos los meses), Fase 5 (cobertura FX de fin de mes) y P25 (cambio de mes). Nunca medido.

## Datos (ningún precio mirado antes de declarar)
- **SPY** y **TLT** diarios, cierre **ajustado** por dividendos (Yahoo chart API, pública), 2003-12-01 → 2026-11-20.
  Cache `.cache_p64/`. **IEF** (bonos 7-10 años) solo descriptivo.
- No hace falta la letra: la posición es larga-corta, autofinanciada.

## Regla (fija)
- Días hábiles = días con precio de SPY. `e` = último día hábil del trimestre (mar/jun/sep/dic). Entrada al cierre de
  `e-5`, salida al cierre de `e` ⇒ captura los **últimos 5 días hábiles** del trimestre.
- Señal (con datos hasta la entrada): `D = r_SPY − r_TLT` desde el cierre del último día hábil del trimestre anterior
  hasta el cierre de `e-5`.
- Posición `s = −signo(D)`: si las acciones le ganaron a los bonos ⇒ corto SPY / largo TLT; si perdieron ⇒ al revés.
  Siempre se opera (sin umbral: un umbral elegido ahora sería un parámetro más).
- Retorno de la ventana = `s · (r_SPY − r_TLT)` en la ventana − costo.
- **Costo** ida y vuelta de las dos patas: **0,10%** (spread de SPY y TLT ~0,01% c/u + deslizamiento; comisión 0).
  Pesimista: **0,20%** (incluye préstamo del corto).
- **Control (resto del trimestre):** la misma regla aplicada a bloques de 5 días hábiles no solapados contados hacia
  atrás desde `e-5` dentro del mismo trimestre (señal = `D` desde el inicio del trimestre hasta el comienzo de cada
  bloque, sin costo). Diferencia = media de la ventana de fin de trimestre (antes de costo) − media del control.
  Separa "rebalanceo de fin de trimestre" de "reversión acciones/bonos en general".

## Muestra
- **Descubrimiento:** trimestres 2004-T1 → 2018-T4 (60 ventanas). **Reserva:** 2019-T1 → 2026-T3 (31), solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. n ≥ 50 ventanas.
2. Retorno neto medio > 0 y CI95 bootstrap (por ventana, 5000 remuestreos, semilla fija) con extremo inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Le gana al resto del trimestre: diferencia > 0 con CI95 bootstrap (por trimestre) inferior > 0.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado (× 4), % positivas, peor ventana, por año, sólo trimestres con |D| sobre la mediana, fines de mes que NO son
fin de trimestre con la misma regla (placebo de calendario), IEF en vez de TLT.

## Límites
- n chico (4 por año): el CI va a ser ancho; la reserva tiene 31 ventanas.
- El efecto está publicado ⇒ puede estar arbitrado: la reserva manda.
- El user no tiene broker de ETFs hoy: si pasa, el papel va primero.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo y propuesta al user con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrado el rebalanceo trimestral acciones/bonos; no se prueban umbrales, otras ventanas ni otros ETFs.
