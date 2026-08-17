# Fase 1b — predicción REGISTRADA antes de medir

**17 Ago 2026. Escrito y commiteado ANTES de correr el backtest sobre los 6 pares
out-of-sample.** Si esto se escribiera después, no valdría nada.

## De dónde viene la hipótesis (y por qué hace falta este test)

Fase 1 midió 20 pares y **refutó** que el edge de D1 generalice (8/15 positivos,
pooled −0,48p neto de swap, criterio pedía ≥13/20). Mirando la tabla apareció un
patrón: los 7 que pierden **pierden ya en bruto**, antes de costos, y son pares
conocidos por ser rangosos (EURGBP, EURCHF, EURCAD, EURAUD, EURNZD, GBPCHF, GBPJPY).

**Ese patrón es POST-HOC**: lo encontré mirando resultados que ya había visto. El
universo de Fase 1 estaba pre-declarado, este corte no. Por eso no se puede tomar
como hallazgo, y por eso hace falta un test sobre datos que no vi.

Ojo con el atajo fácil: "majors vs crosses" **no** es el discriminador. Los dos
mejores en bruto son GBPAUD (+23,14) y USDJPY (+23,01) — uno es cross. Y EURGBP,
el par más BARATO de operar (comisión 0,52p), es el segundo peor. No es costos.

## La hipótesis, en mecanismo

**H1b:** `detect_structure_signals` es un detector de ruptura/continuación ⇒ gana
donde el precio persiste en una dirección y pierde donde vuelve sobre sus pasos.
Entonces una medida de **tendencialidad calculada solo desde precio** debería
predecir el signo del resultado bruto, en cualquier instrumento.

Esto es la misma idea que ya se midió dentro de un par: m15 saca 27,8% de WR con
ATR ≤8p y 51,6% con ATR >8p. Si el principio es real, tiene que valer también
ENTRE instrumentos.

## La métrica (declarada)

**Efficiency Ratio de Kaufman**, ventana **W=20** días, promediado sobre todas las
ventanas rolling de 2000 velas D1:

    ER(20) = |close[t] − close[t−20]| / Σ|close[i] − close[i−1]|

Se calcula en `tools/trendiness_er.py`, que **no lee ningún resultado de
estrategia** — por construcción no puede estar contaminado. W=20 = 2× el hold de
10 velas del track D1: el setup necesita que la dirección persista más allá del
horizonte de salida. W=10 y W=40 se reportan solo como robustez; **la predicción
usa W=20 y nada más.**

## Relación in-sample sobre los 15 ya vistos (esto NO es evidencia, es el ajuste)

    ganadores en bruto (n=8): ER20 medio 0,218888
    perdedores        (n=7): ER20 medio 0,209414
    AUC 0,804 · Spearman rho +0,529 (p=0,043) · Mann-Whitney p=0,027
    5 de 15 rompen el patrón (GBPJPY y EURNZD tienen ER alto y pierden;
    GBPAUD, AUDUSD y EURJPY tienen ER bajo y ganan)

**UMBRAL declarado = punto medio de las dos medias = 0,214151.**
Regla: `ER20 > 0,214151` ⇒ se predice **bruto POSITIVO**. Si no, **NEGATIVO**.

## Las 6 predicciones (out-of-sample, nunca medidos con la estrategia)

| par | ER20 | predicción |
|---|---|---|
| CHFJPY | 0,2205 | **POSITIVO** |
| NZDJPY | 0,2148 | **POSITIVO** (margen <0,001) |
| GBPNZD | 0,2142 | **POSITIVO** (margen <0,001) |
| NZDCHF | 0,2125 | **NEGATIVO** |
| NZDCAD | 0,2061 | **NEGATIVO** |
| GBPCAD | 0,2022 | **NEGATIVO** |

3 positivas y 3 negativas — a propósito no es un set de un solo signo, así que no
puede "acertar" por efecto de tasa base.

AUDCHF y CADCHF quedan EXCLUIDOS: 1,6 años de historia, no cumplen el criterio #3
de Fase 1 (≥2000 velas D1). Exclusión por historia, verificable en `span_days`,
**no** por resultado — y se decide antes de medirlos.

## Criterio de éxito, declarado ahora

- **≥5 de 6 signos correctos** ⇒ la tendencialidad predice, y vale seguir la línea.
  (Bajo la nula de 50%, P(≥5 de 6) = 0,109 — no es prueba fuerte con n=6, pero es
  la mejor evidencia disponible sin esperar meses.)
- **4 de 6** ⇒ no concluyente. No se sigue por acá sin más instrumentos.
- **≤3 de 6** ⇒ H1b refutada. El patrón era ruido post-hoc y el track D se archiva.

Además se reporta, sin que cambie el veredicto: la correlación ER20 vs bruto en los
6, y el pooled de los 6.

## Lo que este test NO puede decir

n=6 instrumentos. Aun acertando 6/6, esto **no** habilita operar: dice que vale
seguir investigando la línea, con el swap y el tamaño de cuenta todavía sin
resolver. Los caveats del backtest siguen todos en pie (solo `structure`, sin
filtros del loop vivo, sin slippage, infla 20-30%).
