# P71 — Reversión acciones/bonos de fin de MES (meses que NO cierran trimestre), solo la reserva: criterio declarado ANTES de medir (24-nov-2026)

**Origen:** descriptivo de P64 (23-nov). La regla de P64 aplicada a los fines de mes que NO son fin de trimestre dio
**+1,03%/ventana en 2004-2018 (n=120)**, el doble que el fin de trimestre. Ese número ya está mirado ⇒ el descubrimiento
de esta idea está "gastado". La única prueba honesta es la **reserva 2019 → oct-2026**, con la regla de P64 sin tocar.
Tipo **B** (flujo forzado: rebalanceo mensual de fondos de mezcla fija y de fondos de fecha objetivo).

## Datos
- `.cache_p64/SPY.json` y `TLT.json` (cierre ajustado de Yahoo, bajados el 23-nov para P64, hasta 2026-11-20). No se
  baja nada nuevo. IEF solo descriptivo.

## Regla (la de P64, sin cambios)
- `e` = último día hábil de un mes de **ene, feb, abr, may, jul, ago, oct, nov**. Entrada al cierre de `e-5`, salida al
  cierre de `e` (últimos 5 días hábiles del mes).
- Señal `D = r_SPY − r_TLT` desde el cierre del último día hábil del mes anterior hasta `e-5`; posición `−signo(D)`.
- Costo 0,10% ida y vuelta las dos patas; pesimista 0,20%.
- **Control:** bloques de 5 días hábiles no solapados hacia atrás desde `e-5` dentro del mismo mes, misma regla, sin
  costo (como P64).

## Muestra
- **Solo reserva:** meses 2019-01 → 2026-10 que no cierran trimestre (~62 ventanas). El período 2004-2018 NO se re-mide.

## Criterios (PASA = los 3)
1. Neto medio > 0 y CI95 bootstrap (por ventana, 5000, semilla fija) con extremo inferior > 0.
2. Le gana al resto del mes: diferencia (bruto − control) > 0 con CI95 bootstrap (por mes) inferior > 0.
3. Media neta > 0 con el costo pesimista.

(Son los criterios de reserva de P64 + el pesimista, porque si pasa sería algo para operar.)

## Descriptivo (no decide)
Mitades, por año, % positivas, peor ventana, IEF en vez de TLT, anualizado (× 8 ventanas por año).

## Límites
- El hallazgo salió mirando datos (descriptivo de P64) ⇒ la reserva es la ÚNICA evidencia que cuenta.
- n ~62: CI ancho. El user no tiene broker de ETFs: si pasa, papel primero.

## Si PASA
No se activa nada. Papel en vivo + propuesta al user con monto mínimo y peor caso en USD; entra a la cartera.
## Si NO PASA
Cerrada la reversión acciones/bonos de fin de mes; no se prueban otras ventanas, umbrales ni ETFs.
