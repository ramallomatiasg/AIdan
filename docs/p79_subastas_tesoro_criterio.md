# P79 — Ciclo de subastas del Tesoro a 10 años → IEF: criterio declarado ANTES de medir (26-nov-2026)

**Hipótesis (Lou, Yan & Zhang 2013, *RFS*):** los dealers tienen que absorber la oferta nueva de cada subasta y cobran
por cargar el inventario: el rendimiento sube (el precio del bono baja) en los días previos a la subasta y se recupera
después. Tipo **B** (flujo forzado). Prior medio-bajo: el efecto está publicado desde 2013 y puede haberse arbitrado.

## Datos (solo se verificaron fechas; ningún retorno mirado con esta señal)
- Fechas de subasta: TreasuryDirect `TA_WS/securities/search?securityType=Note` (la API de fiscaldata daba 504 hoy),
  cache `.cache_p79/notes_all.json`. Se toman las filas con `type == 'Note'` (sin TIPS) y plazo `10-Year` o `9-Year …`
  (reaperturas de la nota a 10 años), fecha = `competitiveAuctionCloseDate`. 263 subastas 2003 → nov-2026
  (8 por año hasta 2008, 12 por año desde 2009).
- IEF (Tesoro 7-10 años), cierre ajustado diario de Yahoo (cache de P64, `.cache_p64/IEF.json`, desde dic-2003).

## Regla (fija)
- Para cada subasta con fecha A (si A no es día hábil de IEF, se salta): `t0` = 5 días hábiles de IEF antes de A,
  `t1` = A, `t2` = 5 días hábiles después de A.
- **Corto** IEF del cierre de `t0` al cierre de `t1`; **largo** del cierre de `t1` al cierre de `t2`.
  Retorno bruto por subasta = −r(t0→t1) + r(t1→t2).
- **Costo:** 4 lados por subasta (abrir corto, cerrar corto, abrir largo, cerrar largo) × 0,05% = 0,20%
  (pesimista 0,10% por lado = 0,40%). Si las ventanas de dos subastas se superponen, cada una se cuenta por separado
  (se reporta cuántas).

## Control (placebo)
200 placebos (semilla 20261126): cada subasta se reemplaza por un día hábil al azar del mismo período que esté a más de
7 días hábiles de cualquier subasta, y se calcula la misma operación. Se compara el retorno BRUTO medio.

## Muestra
- **Descubrimiento:** subastas de 2004-01-01 a 2014-12-31. **Reserva:** 2015 → nov-2026, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥80 subastas.
2. Neto medio > 0 y CI95 bootstrap (5000, por subasta) con inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Retorno bruto medio > p95 de los 200 placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Las dos patas por separado (antes / después), acierto, por año, IEF siempre largo en las mismas ventanas, nuevas vs
reaperturas.

## Si PASA
No se activa nada; reserva y propuesta al user. Automatizable con un ETF (IEF) y un calendario público.
## Si NO PASA
Cerrado el ciclo de subastas a 10 años con ETF; no se prueban otros plazos (2, 5, 30 años), ventanas ni TLT.
