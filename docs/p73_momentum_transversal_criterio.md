# P73 — Momentum TRANSVERSAL de 3 semanas en perpetuos de Binance: criterio declarado ANTES de medir (25-nov-2026)

**Hipótesis:** las monedas que más subieron en las 3 semanas previas siguen subiendo más que las que más bajaron la
semana siguiente (factor de momentum de Liu, Tsyvinski y Wu 2022, *Journal of Finance*, "Common risk factors in
cryptocurrency"). Tipo **A** (premio por riesgo / factor). Distinto de P40 (momentum en series de tiempo, cerrado) y
de P70 (reversión de 1 semana, cerrado: +0,04% bruto).

## Datos (ningún retorno mirado con esta señal antes de declarar)
- Los mismos de P67, sin bajar nada: `.cache_p67/disc` (descubrimiento) y `.cache_p67/full` (reserva). Universo,
  exclusiones, velas diarias (open, volumen) y funding (pedido desde la primera vela) idénticos a P67.

## Regla (fija)
- Rebalanceo cada lunes 00:00 UTC (open de la vela diaria del lunes). Semana = de ese open al del lunes siguiente.
- **Señal:** `open(lunes) / open(lunes − 21 días) − 1` (precio del perpetuo; sin saltear la última semana).
- **Elegible:** las reglas de P67 (≥30 días desde la primera vela, ≥15 cobros de funding en los 7 días previos,
  volumen medio ≥ USD 10 M/día en los 7 días previos, vela con volumen > 0 el lunes) **y** vela con volumen > 0
  exactamente en `lunes − 21 días`.
- Se necesitan ≥10 elegibles. Quintil de MAYOR retorno ⇒ largo; quintil de MENOR retorno ⇒ corto
  (`floor(N/5)` por pata, mínimo 2), peso igual.
- PnL, funding real, cierre si deja de cotizar, retorno por dólar de exposición bruta: igual que P67.
- **Costo:** 0,15% por lado × rotación (pesimista 0,30%), igual que P67.

## Placebo
200 placebos: a cada semana se le asigna la señal (retorno de 3 semanas por moneda) de otra semana al azar de la
muestra (semilla 20261125), con el universo elegible de la semana real. Se compara el retorno BRUTO medio.

## Muestra
- **Descubrimiento:** lunes del 6-ene-2020 al 25-dic-2023. **Reserva:** 1-ene-2024 → última semana completa, solo si
  pasa.

## Criterios (descubrimiento; PASA = los 5)
1. ≥150 semanas con cartera.
2. Neto medio > 0 y CI95 bootstrap por bloques de 4 semanas (5000, semilla fija) con inferior > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > 0 con el costo pesimista.
5. Retorno bruto medio > p95 de los 200 placebos.

**Reserva:** criterios 2 y 5.

## Descriptivo (no decide)
Anualizado, aporte de precio vs funding por pata, rotación, peor semana, caída máxima, por año, correlación semanal
con BTC y con P67.

## Límites
- Volumen aproximado (base × open). Pocas monedas en 2020.
- Si pasa: con USD 500-1.000 y 2 patas × ≥2 monedas, choca con los mínimos de orden ⇒ se reporta.

## Si PASA
No se activa nada. Reserva; si pasa, papel en vivo y propuesta al user.
## Si NO PASA
Cerrado el momentum transversal semanal en cripto; no se prueban otras ventanas (1, 2, 4 semanas), saltear la
última semana, deciles ni solo una pata.
