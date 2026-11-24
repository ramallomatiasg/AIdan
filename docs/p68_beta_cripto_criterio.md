# P68 — Apostar contra la beta en cripto (semanal, beta-neutral): criterio declarado ANTES de medir (23-nov-2026)

**Hipótesis:** quien no puede o no quiere apalancarse compra lo de beta alta y lo encarece ⇒ lo de beta baja rinde más
por unidad de riesgo (Frazzini y Pedersen 2014, "Betting against beta"). En cripto los minoristas persiguen las alts de
beta alta. Tipo **A** (premio por riesgo). Nunca medido (grep beta: 0 en el registro).

## Datos (ningún precio mirado antes de declarar para esta prueba)
Los mismos de P67 (`tools/fetch_p67_perps.py`, `.cache_p67/disc`): velas diarias y funding de todos los perpetuos USDT
de Binance que existieron, incluidos los cerrados, mismo filtro de símbolos. Funding pedido desde la primera vela.
*Nota honesta: al correr P67 ya vi resultados agregados de esa data (carry por funding), no betas ni retornos por beta.*

## Regla (fija)
- Rebalanceo cada lunes 00:00 UTC (open diario). Semana = de ese open al del lunes siguiente. BTCUSDT es la referencia
  y no entra en la cartera.
- **Beta** de cada moneda: pendiente MCO de sus retornos diarios open→open contra los de BTCUSDT en los 90 días previos
  al lunes; se exigen ≥60 días con dato de las dos.
- **Elegible:** primera vela ≥90 días antes; volumen medio en USD (volumen × open) de los 7 días previos ≥ USD 10
  millones/día; vela con volumen > 0 el lunes; beta calculable.
- ≥10 elegibles. Quintil de beta más BAJA ⇒ largo; más ALTA ⇒ corto (`floor(N/5)` por pata, mínimo 2), peso igual
  dentro de cada pata.
- **Neutral a la beta y bruto 1:** con β_L y β_C las betas medias de cada pata (mínimo 0,1), pesos
  w_L = (1/β_L)/(1/β_L + 1/β_C) en la pata larga y w_C = (1/β_C)/(1/β_L + 1/β_C) en la corta.
- PnL por moneda: largo `r − Σfunding`, corto `−r + Σfunding` (funding real de la semana). Si deja de cotizar, se
  cierra en el último open con volumen.
- Retorno de la semana = w_L × media pata larga + w_C × media pata corta.
- **Costo:** 0,15% por lado operado × rotación en dólares (suma de |peso nuevo − peso viejo| por moneda, con los pesos
  ya multiplicados por w_L / w_C). Pesimista 0,30%.

## Placebo
200 placebos: a cada semana se le asignan las betas de otra semana al azar (semilla 20261123), con el universo elegible
de la semana real; mismo armado. Se compara el retorno BRUTO medio.

## Muestra
- **Descubrimiento:** lunes 6-abr-2020 → 25-dic-2023. **Reserva:** 1-ene-2024 → última semana completa, solo si pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥150 semanas con cartera.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000, semilla fija) inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Retorno bruto medio real > p95 de los 200 placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado, beta realizada de la cartera contra BTC en la semana (tiene que dar ≈0), peor semana (colas de squeeze),
caída máxima, por año, aporte de precio vs funding por pata, correlación semanal con P67.

## Límites
- La beta de 90 días es ruidosa y las alts de beta baja suelen ser poco líquidas (por eso el piso de volumen).
- Corto de alts de beta alta sin stop: colas feas (P55, P56) ⇒ se reporta la peor semana.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo y propuesta al user (Plan/Razón/Pros/Contras/Opinión).
## Si NO PASA
Cerrado apostar contra la beta en cripto; no se prueban otras ventanas, umbrales, quintiles ni el signo contrario.
