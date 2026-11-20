# P60 — Extensión de duración de fin de mes en bonos del Tesoro (TLT): criterio declarado ANTES de medir (19-nov-2026)

**Hipótesis:** los índices de bonos (Bloomberg US Treasury / Aggregate) se rebalancean el último día hábil de cada mes y
su duración se alarga (entran bonos nuevos largos, salen los que bajan de 1 año). Los fondos que replican el índice
TIENEN que comprar duración ese día ⇒ los bonos largos suben en los últimos días del mes. Tipo **B** (flujo forzado).
Distinto de Fase 5 (rebalanceo acciones/FX) y de P25 (cambio de mes en índices de acciones). Nunca medido acá.

## Datos (ningún precio mirado antes de declarar)
- **TLT** (ETF de bonos del Tesoro de +20 años) diario, cierre **ajustado** por dividendos (Yahoo chart API, pública),
  2004-01-01 → 2026-11-18. Cache `.cache_p60/`. TLT paga dividendo mensual con ex-fecha a comienzo de mes: el cierre
  ajustado lo incluye y no ensucia la ventana.
- Letra a 3 meses: FRED `DTB3` (cache de P50).

## Regla (fija)
- Ventana de fin de mes = del **cierre del 4to día hábil antes del último** al **cierre del último día hábil del mes**
  (captura los retornos de los últimos 3 días hábiles). Días hábiles = días con precio de TLT.
- Exceso de la ventana = retorno de TLT − letra × 3/252 − costo.
- **Costo** ida y vuelta: **0,05%** (spread de TLT ~0,01% + deslizamiento; comisión 0 en un broker de ETFs).
  Pesimista: **0,10%**.
- **Control (el resto de los días):** todas las ventanas de 3 días hábiles consecutivos NO solapadas con la de fin de mes
  del mismo mes (bloques de 3 días contados hacia atrás desde la ventana de fin de mes, sin costo). Diferencia =
  media de fin de mes (antes de costo) − media del control.

## Muestra
- **Descubrimiento:** meses ene-2004 → dic-2018 (180 ventanas). **Reserva:** ene-2019 → oct-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. n ≥ 100 ventanas.
2. Exceso medio por ventana > 0 y CI95 bootstrap (por ventana, 5000 remuestreos, semilla fija) con extremo inferior > 0.
3. Las dos mitades cronológicas con exceso medio > 0.
4. Exceso medio > 0 con el costo pesimista.
5. Le gana al resto de los días: diferencia (fin de mes − control) > 0 con CI95 bootstrap inferior > 0.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Exceso anualizado (× 12), por año, % de ventanas positivas, peor ventana, último día solo vs los 3 días, IEF (7-10 años)
con la misma regla como comparación.

## Límites
- El efecto está publicado (Fed de NY, Hartley & Schwarz) ⇒ puede estar arbitrado: por eso la reserva es la que vale.
- TLT es un ETF de duración ~17: la ventana tiene la volatilidad de los bonos largos, el exceso esperado es chico frente
  al ruido.
- El user no tiene broker de ETFs hoy: si pasa, el papel va primero.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo (orden al cierre del 4to día hábil antes del fin de mes) y propuesta
al user con monto mínimo y peor caso en USD.
## Si NO PASA
Cerrado el fin de mes en bonos; no se prueban otras ventanas, otros ETFs de bonos ni futuros.
