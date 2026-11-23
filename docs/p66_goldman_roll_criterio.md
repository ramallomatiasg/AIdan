# P66 — Adelantarse al "roll" de los fondos índice de commodities (petróleo WTI): criterio declarado ANTES de medir (23-nov-2026)

**Hipótesis:** los fondos que replican índices de commodities (GSCI, BCOM) pasan del futuro cercano al siguiente entre
los días hábiles 5 y 9 de cada mes (el "Goldman roll"): venden el cercano y compran el siguiente, en fechas conocidas.
Quien se adelanta (corto el cercano / largo el diferido ANTES del roll) cobra la presión de precio (Mou 2011). Tipo
**B** (flujo forzado). Nunca medido (grep roll/GSCI: 0).

## Datos (ningún precio mirado antes de declarar; solo se miró la fecha de inicio de cada ETF)
- No hay curva de futuros gratis con contratos vencidos ⇒ aproximación declarada con ETFs (Yahoo chart API, cierre
  ajustado), cache `.cache_p66/`:
  - **USO** (hasta mar-2020 tenía el contrato CERCANO de WTI y rolaba en 4 días unas dos semanas antes del vencimiento,
    ≈ días hábiles 6-10 ⇒ en los días 1-4 tiene el contrato que los índices van a vender).
  - **USL** (12 meses escalonados, rola 1/12 por mes ⇒ ≈ la curva diferida).
- **Quiebre declarado:** en abril-2020 USO cambió su cartera (pasó a varios meses) ⇒ la aproximación deja de valer.
  La muestra termina en **mar-2020**.

## Regla (fija)
- Días hábiles = días con precio de los dos ETFs. Posición: **largo USL / corto USO** del cierre del último día hábil
  del mes anterior al cierre del **4to día hábil** del mes (retornos de los días hábiles 1-4, antes del roll).
- Retorno = `r_USL − r_USO` en la ventana − costo.
- **Costo** ida y vuelta de las dos patas: **0,20%** (USL es poco líquido: spread ~0,1%; USO ~0,02%). Pesimista
  **0,40%** (incluye préstamo de USO).
- **Control (resto del mes):** la misma posición en bloques de 4 días hábiles no solapados desde el **día hábil 10**
  hasta fin de mes (después del roll), sin costo. Diferencia = media de la ventana (antes de costo) − media del control.
  Separa "presión del roll" de "el cercano rinde menos que la curva por el contango todo el mes".

## Muestra
- **Descubrimiento:** meses ene-2008 → dic-2014 (84). **Reserva:** ene-2015 → mar-2020 (63), solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. n ≥ 70 ventanas.
2. Neto medio > 0 y CI95 bootstrap (por ventana, 5000, semilla fija) inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Le gana al resto del mes: diferencia > 0 con CI95 bootstrap (por mes) inferior > 0.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado (× 12), % positivas, peor ventana, por año, días 5-9 (durante el roll) con la misma posición.

## Límites
- Es una aproximación: USL no es "el contrato siguiente" sino 12 meses; si el efecto vive solo entre el 1er y el 2do
  contrato, se diluye ~12 veces en la pata larga (la corta sí es el contrato que rola).
- Efecto publicado y achicado después de 2007 (Mou) ⇒ la reserva manda.
- Si pasa, la ejecución real sería con futuros (CL) o ETFs; el user no tiene broker de futuros: papel primero.

## Si PASA
No se activa nada. Reserva; si pasa, buscar cómo ejecutarlo hoy (USO ya no sirve: futuros o el diferencial CL1-CL2) y
proponerlo al user con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrado el adelanto al roll de commodities; no se prueban otras ventanas, otros commodities ni otros ETFs.
