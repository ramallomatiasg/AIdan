# P49 — Desbloqueos grandes de tokens (oferta forzada): criterio declarado ANTES de medir (17-nov-2026)

**Hipótesis:** los que reciben un desbloqueo grande de tokens (equipo, inversores) venden o se cubren antes de la
fecha; el mercado lo sabe por calendario pero el corto paga poco. Tipo **B** (flujo forzado). Prior medio-bajo (lo
conocido suele estar en el precio).

## Datos (verificado antes de declarar: solo el calendario, **ningún precio**)
- Calendario: `defillama-datasets.llama.fi/emissions/<slug>` (público). `tools/p49_unlocks_data.py` mapea el slug al
  símbolo (protocols → parentProtocols → chains) y exige que exista `<SYM>USDT` perpetuo en Binance. 2022-01-01 →
  2026-10-15: 1.605 eventos "cliff" ≥ 1% en 109 monedas (sin filtrar categoría ni solapamiento).
- Precios: velas diarias del perpetuo y funding de Binance (`fapi`, públicos), cache `.cache_p49/`.

## Eventos (fijos)
- Desbloqueo tipo **cliff** cuya suma de tokens del día es ≥ **1%** de lo desbloqueado el día previo (DefiLlama), y
  que incluye la categoría **insiders o privateSale** (los vendedores de la hipótesis).
- Misma moneda con otro evento elegible en los 7 días previos ⇒ se queda solo el primero (sin solapar).
- El perpetuo tiene que tener vela en D−7 y en D; si no, se descarta y se cuenta.

## Regla
- **Corto** del perpetuo del open de la vela diaria de D−7 (00:00 UTC) al open de la vela del día D del desbloqueo.
- Resultado = −(P_D / P_{D−7} − 1) + funding cobrado por el corto en (D−7, D] − costo.
- **Costo:** taker 0,05% × 2 + deslizamiento 0,05% × 2 = **0,20%** ida y vuelta. Pesimista: 0,40%.

## Control (placebo)
Misma moneda, **mismo año**, ventanas de 7 días que arrancan en días sin evento elegible de esa moneda en ±14 días;
2000 repeticiones de la media de n ventanas (una por evento) ⇒ percentil 95. Saca la deriva de cada moneda.

## Muestra
- **Descubrimiento:** eventos 2022-2024. **Reserva:** 2025 → 15-oct-2026, solo si pasa el descubrimiento.

## Criterios (descubrimiento; PASA = los 6)
1. n ≥ 150 eventos.
2. Media neta > 0 y extremo inferior del CI95 > 0, con bootstrap **agrupado por semana calendario** (los eventos de
   la misma semana comparten el mercado: la lección de P51).
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > percentil 95 del control.
5. Media neta > 0 con el costo pesimista.
6. Mediana neta > 0 (que no sean 3 derrumbes).

**Reserva:** media neta > 0, CI agrupado inferior > 0 y > control p95.

## Descriptivo (no decide)
Bruto, funding aparte, por año, por categoría, por tamaño (1-3% / 3-10% / >10%), D−7→D+7.

## Límites
- El calendario de DefiLlama es el de hoy: los cliffs de equipo/inversores se publican al lanzar el token, pero algún
  cambio posterior (un desbloqueo postergado) puede no reflejar lo que se sabía entonces.
- Supervivencia: solo monedas con perpetuo listado hoy en Binance (las deslistadas, que suelen caer más, faltan).
- Mapeo por símbolo: alguna moneda puede quedar mal mapeada (se reporta la lista).

## Si PASA
No se activa. Reserva; después papel en vivo con el peor caso en USD (un corto de alt con lote mínimo).
## Si NO PASA
Cerrar desbloqueos de tokens. No probar otros tamaños, ventanas, categorías ni largo después del desbloqueo.
