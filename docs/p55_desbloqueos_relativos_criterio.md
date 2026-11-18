# P55 — Desbloqueos de tokens en versión RELATIVA, solo en la reserva 2025-26: criterio declarado ANTES de medir (18-nov-2026)

**De dónde sale:** en P49 (descubrimiento 2022-24, NO PASA) la semana previa a un desbloqueo rindió ~2,3 puntos mejor
que una semana normal de la misma moneda, pero el mercado de alts subiendo se comía el corto absoluto. Neutralizar el
mercado es lo que eso sugiere. Como la idea sale de MIRAR el descubrimiento, **se mide una sola vez sobre 2025 →
oct-2026**, que nadie miró (la reserva de P49 nunca se corrió). Sin reintentos ni variantes. Tipo **B**.

## Datos
Los mismos de P49: calendario de DefiLlama (`tools/p49_unlocks_data.py`, mismos eventos elegibles: cliff ≥ 1% con
insiders o privateSale, sin solapar a 7 días) y velas diarias + funding de los perpetuos de Binance (`.cache_p49/px/`).

## Regla (fija)
- Por cada evento del día D en 2025-01-01 → 2026-10-15: **corto** el perpetuo de la moneda del open de D−7 al open de
  D, y **largo por el mismo monto** una cesta de igual peso de las OTRAS monedas del universo de P49 que tengan vela en
  D−7 y D y **ningún evento elegible en ±14 días de D**.
- Resultado = −r_moneda + funding cobrado por el corto + r_cesta − funding pagado por la cesta − costo.
- **Costo:** 0,20% ida y vuelta por pata ⇒ **0,40%** total. Pesimista: **0,80%**.
- Si la cesta tiene < 5 monedas, el evento se descarta y se cuenta.

## Control (placebo)
Misma moneda, mismo año, ventanas de 7 días sin evento propio en ±14 días, con la misma construcción relativa (la cesta
de esa ventana); 2000 repeticiones de la media de n ventanas ⇒ percentil 95.

## Criterios (reserva, un solo disparo; PASA = los 6)
1. n ≥ 50 eventos.
2. Media neta > 0 y extremo inferior del CI95 > 0, bootstrap agrupado por semana calendario (5000).
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > percentil 95 del control.
5. Media neta > 0 con el costo pesimista.
6. Mediana neta > 0.

## Descriptivo (no decide)
Pata corta sola (= P49 en la reserva), pata cesta sola, funding de cada pata, por tamaño del desbloqueo, peor evento.

## Límites
- Supervivencia: el universo son monedas con perpetuo listado hoy (igual que P49).
- El calendario de DefiLlama es el de hoy (igual que P49).
- No hay segunda muestra limpia: si pasa, el paso siguiente solo puede ser papel en vivo.

## Si PASA
No se activa. Propuesta de papel en vivo (corto + cesta con lote mínimo) con el peor caso en USD, para el OK del user.
## Si NO PASA
Cerrar desbloqueos de tokens del todo (absoluto y relativo). No probar otras ventanas, tamaños ni cestas.
