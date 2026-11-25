# P72 — Re-correr P56, P59 y P63 con el funding completo: criterio declarado ANTES de re-medir (24-nov-2026)

**Qué pasó:** los tools de P56, P59 y P63 pedían el funding de Binance con `startTime=0`; en ese caso la API devuelve
solo los últimos ~333 días ⇒ en los caches `.cache_p56/px`, `.cache_p59/px` y `.cache_p63/px` el funding de 2020-2024
quedó vacío y el backtest lo tomó como CERO. Los tres dieron NO PASA con ese dato roto.

## Qué se hace (y nada más)
1. `tools/fix_p72_funding.py`: para cada archivo de esos tres caches, vuelve a pedir el funding desde la **primera vela**
   del archivo hasta el **último funding que ya tenía** (mismo final, para no agregar datos nuevos). Las velas no se
   tocan. El archivo viejo se guarda en `<cache>/px_funding_viejo/` (reversible).
2. Los tres tools se corrigen en UNA línea cada uno (el `t = 0` inicial del loop de funding pasa a la primera vela), para
   que una descarga futura no repita el error. Ningún otro cambio: misma regla, mismo período, misma semilla.
3. Se re-corre cada uno en descubrimiento con su criterio original:
   - P56 `docs/p56_listados_nuevos_criterio.md`
   - P59 `docs/p59_wikipedia_atencion_criterio.md`
   - P63 `docs/p63_fees_defi_criterio.md`

## Cómo se lee
- Cada uno se juzga con **su propio criterio**, tal cual estaba. Se reporta viejo vs nuevo (neto, CI, criterios).
- Si alguno pasa a PASA en descubrimiento, recién ahí se mira su reserva como dice su criterio (y P72 no "pasa" por sí:
  es una corrección de datos). Si siguen NO PASA, se cierran de nuevo con el dato bueno.
- Control de sanidad (fail-loud): después del arreglo, en cada archivo con velas antes de 2024 el primer funding tiene
  que caer a ≤ 2 días de la primera vela; si no, se reporta cuántos no cumplen.

## Límites
- Si la API no devuelve funding para algún perpetuo cerrado, queda como estaba y se cuenta.
