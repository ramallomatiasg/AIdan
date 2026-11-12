# P36 — Flujos de los ETF de bitcoin → retorno del día siguiente: criterio declarado ANTES de medir (11-nov-2026)

**Hipótesis:** la entrada neta diaria a los ETF de bitcoin al contado de EE.UU. es plata que compra por
mandato; si el precio no la absorbe toda el mismo día, el día siguiente sigue en esa dirección. Tipo **B-C**
de la escalera (flujo + dato con demora). Nunca medido acá.

## Datos
- Flujos: tabla diaria "Total" (millones de USD) de farside.co.uk (`bitcoin-etf-flow-all-data`), 11-ene-2024 →
  hoy, guardada en `.cache_p36/`. Antes de declarar solo se miró que la tabla existe y su rango de fechas.
- Se excluyen los días con todos los fondos en 0,0 (feriados de EE.UU.) y los días con algún fondo sin dato
  ("-").
- Precio: perpetuo BTCUSDT de Binance, apertura de velas de 8 h (cache de P15, hasta 2026-10-21); funding real
  de Binance del mismo cache.
- Costo: 0,05% por lado (taker) + 0,02% de deslizamiento por lado = **0,14% ida y vuelta**, más el funding
  real que se cruza (el largo paga, el corto cobra; se cuentan los 3 fundings entre la entrada y la salida
  inclusive).

## Regla (fija)
- Flujo del día D (fecha de la tabla, día hábil de EE.UU.).
- **Entrada 08:00 UTC de D+1** (el total de farside puede completarse de madrugada: 8 h de margen para no
  mirar el futuro), salida 08:00 UTC de D+2 (24 h).
- **Descubrimiento / reserva:** primera mitad cronológica de los días válidos / segunda mitad. Umbrales =
  tercios (percentiles 33,3 y 66,7) del flujo en el descubrimiento (congelados).
- Flujo ≥ p66,7 ⇒ largo; ≤ p33,3 ⇒ corto; en el medio, nada.

## Placebo
La misma regla con la serie de flujos **desplazada en el tiempo** (corrimiento circular al azar de 30 a n−30
días, 2000 repeticiones): percentil 95 de la media neta en la reserva. Responde: ¿el flujo de ESE día importa
o es la deriva del período?

## Criterios (PASA = los 5)
1. n ≥ 100 operaciones en la reserva.
2. Reserva: media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Descubrimiento: media neta > 0.
4. Reserva: media neta > percentil 95 del placebo.
5. Las dos mitades de la reserva con media neta > 0.

## Descriptivo (no decide)
Bruto, ganadores, largos vs cortos, por año, correlación de Spearman flujo(D) vs retorno siguiente, y
flujo(D) vs retorno del MISMO día D (¿el flujo sigue al precio?).

## Si PASA
No se activa. Proponer: papel en vivo + el mismo test con los ETF de ether (otra serie, nunca mirada).
## Si NO PASA
Cerrar flujos de ETF → dirección de BTC al día siguiente. No probar otro horizonte, otro umbral, ni fondos
sueltos (IBIT solo).

## Enmienda 1 (11-nov, antes de leer el resultado válido)
La primera corrida descartó 579 de 728 días: en farside un fondo que **todavía no existía** figura con "-",
y la regla "algún fondo sin dato" sacaba todo lo anterior al lanzamiento del último ETF. Corrección de lectura
(no de parámetro): un "-" cuenta como dato faltante solo si ese fondo ya había tenido un valor numérico en un
día anterior; antes de su primer dato vale 0. El resto del criterio no cambia. La corrida descartada (n=52,
abr-oct 2026) queda anotada en el registro.
