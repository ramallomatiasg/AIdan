# P51 — Cierre del gap de apertura semanal en FX: criterio declarado ANTES de medir (17-nov-2026)

**Hipótesis:** el gap entre el cierre del viernes y la apertura del domingo nace con liquidez mínima y tiende a
cerrarse en las horas siguientes. Tipo **B** (liquidez). Nunca medido acá (grep `gap`: 0 en registro e historial).
Riesgo declarado: que el gap sea información del fin de semana (no ruido) y que el spread del arranque se lo coma.

## Datos
- `.cache_fase2/M5_500000/` (MT5 ICMarkets) vía `load_pair` de `backtest_fase4_planes.py`, los **20 pares de
  descubrimiento** (los de Fase 2 menos `RESERVADOS`). dic-2019 → ago-2026, ~345 semanas por par.
- Antes de declarar solo se miró el largo del cache (500.000 velas por par) y las specs. **Ningún precio.**
- Los 4 reservados que quedan sin usar (GBPNZD, NZDCHF, NZDCAD, GBPCAD) solo se abren si pasa el descubrimiento.

## Definiciones (fijas)
- **Corte de semana:** dos velas M5 consecutivas separadas por más de 24 h. Cierre del viernes `F` = close de la
  última vela antes del corte; apertura `A` = open de la primera vela después.
- **Gap** = `A − F`. **Tamaño de referencia:** ADR14 de la casa (`P['adr']`: rango medio de los 14 días server
  previos al día de la primera vela; es el "ATR(D1)" de la cola, misma métrica que Fase 4).
- **Señal:** `|gap| > 0,5·ADR14`.

## Regla
- **Entrada:** open de la primera vela con hora UTC ≥ hora de `A` + 60 min (la vela de apertura tiene spread de
  ~16p, medido en Fase 4). Si en esa primera hora el precio ya tocó `F`, no hay operación (se cuenta como "cerrado
  en la 1ra hora", descriptivo).
- **Dirección:** hacia `F` (gap hacia arriba ⇒ corto; hacia abajo ⇒ largo).
- **Salida:** al tocar `F` (low/high de la vela, desde la vela de entrada) se sale en `F` (orden límite, sin
  deslizamiento: optimista, declarado); si no, open de la primera vela con hora ≥ entrada + 24 h. Sin stop.
  Si no hay vela de salida (fin de datos), se descarta y se cuenta.
- **Costo:** comisión de la spec + spread de la vela de entrada (mínimo de la vela ⇒ cota optimista) + swap real
  (`swap_pips` de Fase 4). Pesimista: +0,3 pips.

## Control (placebo)
Mismas semanas con señal, misma entrada, mismo horizonte de 24 h y objetivo a la **misma distancia** que `F`, pero
en dirección al azar (moneda). 2000 repeticiones de la media neta ⇒ percentil 95. Mide si "ir hacia el viernes"
tiene información o si cualquier objetivo a esa distancia da lo mismo.

## Criterios (PASA = los 6, 20 pares juntos, en pips netos por operación)
1. n ≥ 150 operaciones (no sé cuántos gaps > 0,5·ADR hay; si son menos, NO PASA por muestra).
2. Media neta > 0 y extremo inferior del CI95 bootstrap > 0.
3. Las dos mitades cronológicas con media neta > 0.
4. Media neta > percentil 95 del control.
5. Media neta > 0 con el costo pesimista.
6. Al menos 12 de los pares con n ≥ 5 tienen media neta > 0.

## Descriptivo (no decide)
Bruto, % que toca `F` antes de 24 h, % cerrados en la 1ra hora, por año, por par; umbral 0,25·ADR.

## Si PASA
No se activa. Fuera de muestra en los 4 reservados (GBPNZD, NZDCHF, NZDCAD, GBPCAD) con la misma regla: exige
media neta > 0 (y CI inferior > 0 si n ≥ 40). Después, papel en vivo con el peor caso en USD.
## Si NO PASA
Cerrar el gap semanal en FX. No probar otros umbrales, horas de entrada, stops ni subconjuntos de pares.
