# Fase 1 — lista de pares DECLARADA ANTES de correr el backtest

**Fecha/hora de declaración: 17 Ago 2026, antes de ejecutar `backtest_multi_symbol.py`.**

Este archivo existe por una sola razón: si elijo los pares DESPUÉS de ver los
resultados, el hallazgo no vale nada (p-hacking por selección de universo). Queda
escrito acá, se commitea antes de correr, y el resultado se reporta sobre ESTA lista
completa — incluidos los pares que salgan mal.

## Criterio de inclusión (a priori, NO por performance)

1. Solo monedas del G8: USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF.
2. Spread actual ≤ 15 points en la cuenta demo (liquidez razonable).
3. Al menos 2000 velas D1 disponibles en MT5.
4. Sin exóticos (TRY, ZAR, DKK, NOK, SEK, PLN, HKD, SGD, MXN) ni crypto:
   régimen de volatilidad y costo de financiamiento distintos.

## Los 20 pares

**Majors (7):** EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, USDJPY

**Crosses (13):** EURGBP, EURJPY, EURCHF, EURAUD, EURCAD, EURNZD,
GBPJPY, GBPCHF, GBPAUD, AUDJPY, AUDNZD, AUDCAD, CADJPY

## Qué se reporta, sí o sí

- El resultado de los **20**, ordenados, sin recortar los negativos.
- Cuántos dan positivo neto de comisión Y de swap.
- El agregado (pooled) de los 20, que es el número honesto: si 6 ganan y 14 pierden,
  el edge no generaliza aunque los 6 se vean lindos.
- Walk-forward por par (mitad vieja vs nueva).

## Hipótesis pre-declarada

**H1:** el edge de `structure` en velas diarias NO es específico de EUR/USD ⇒ la
mayoría de los 20 pares debería dar avg/trade positivo neto de comisión.

**H0 (lo que asumo si la evidencia no alcanza):** el +14p de EUR/USD era una
particularidad de ese par y/o de ese período ⇒ D1 no se activa y el track queda
en shadow o se archiva.

**Criterio de éxito declarado ANTES de correr:** para llamarlo "generaliza" pido
**≥13 de 20 pares** con avg/trade positivo neto de comisión **y** el pooled de los
20 positivo neto de comisión Y de swap. Menos que eso = no generaliza, y se dice.
