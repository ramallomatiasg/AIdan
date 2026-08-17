# Fase 1 + 1b — RESULTADO: el edge de D1 no existe como fenómeno general

**17 Ago 2026.** Cierra la línea abierta el 13-ago con el track D. Todo read-only:
no se tocó producción, no se mandó ninguna orden.

## Qué se preguntó

El track D1 daba 2,3 señales/mes en EUR/USD ⇒ el gate de n=25 tardaba ~11 meses.
En vez de esperar, se corrió el MISMO detector sobre 21 pares y 7,3-7,7 años.
Lo único que cambia es el instrumento.

## Resultado

    21 pares · n=3.669 señales · 7,3-7,7 años cada uno

    positivos neto de comisión : 8 / 21
    POOLED neto de comisión    : -0,64 pips/trade   (PF 0,99)
    POOLED neto de comisión+swap: -3,76 pips/trade  (PF 0,93)

    ganan: AUDUSD, EURJPY, EURUSD, GBPAUD, GBPUSD, NZDUSD, USDCHF, USDJPY

**8 de 21 es MENOS que lo que daría el azar.** Con edge verdadero cero y ruido
simétrico se esperarían ~10,5 de 21. O sea: no hay ninguna señal de edge
entre instrumentos, ni antes de costos.

El +16 pips de EUR/USD que originó el track no era un hallazgo: era el primer par
que miramos. Con 21 intentos, que 8 salgan positivos es exactamente lo que pasa
cuando no hay nada.

## Fase 1b — el test registrado, y por qué también falla

El patrón post-hoc "los que pierden son los pares rangosos" se testeó en serio:
métrica de tendencialidad (Efficiency Ratio de Kaufman, W=20) calculada **solo
desde precio**, umbral ajustado sobre los 15 pares ya vistos, y **6 predicciones
registradas y commiteadas ANTES de medir** (commit `2269691`).

| par | ER20 | predicción | real | |
|---|---|---|---|---|
| CHFJPY | 0,2205 | POSITIVO | +0,76p | acertó |
| NZDJPY | 0,2148 | POSITIVO | −9,81p | **falló** |
| GBPNZD | 0,2142 | POSITIVO | −28,64p | **falló** |
| NZDCHF | 0,2125 | NEGATIVO | −3,61p | acertó |
| NZDCAD | 0,2061 | NEGATIVO | −3,56p | acertó |
| GBPCAD | 0,2022 | NEGATIVO | −9,76p | acertó |

**4 de 6.** Por la letra del criterio declarado eso es "no concluyente". Pero el
control lo mata:

- **5 de los 6 eran realmente negativos** ⇒ predecir "NEGATIVO" a todo daba **5/6**.
  El modelo de ER sacó 4/6: **peor que una constante.**
- Correlación ER20 vs bruto en los 6: **Spearman rho +0,086 (p=0,872)** — cero.
  In-sample era rho +0,529 (p=0,043). Ese colapso es la firma del overfit.

### Falla de diseño mía, para no repetirla

Puse 3 predicciones positivas y 3 negativas creyendo que eso protegía del efecto
de tasa base. Protege el balance de las PREDICCIONES, no el de los RESULTADOS: si
el conjunto out-of-sample sale casi todo negativo, acertar los negativos no
demuestra habilidad. **Un criterio de conteo de signos necesita SIEMPRE su
comparación contra la constante, declarada junto con él.** No lo declaré.

## Lo que quedó descartado en el camino

- **No es un artefacto de costos.** Los 7 perdedores de Fase 1 pierden ya EN BRUTO.
  Y EURGBP, el par más barato de operar (comisión 0,52p), es el segundo peor.
- **No es "majors vs crosses".** Los dos mejores en bruto son GBPAUD (cross, +23,14)
  y USDJPY (+23,01). EURJPY (cross) le gana a cuatro majors.
- **No es tendencialidad medible.** Es lo que acabó de refutar Fase 1b.

## Decisión

**El track D1 se archiva.** No se activa, y no tiene sentido seguir juntando las
2,3 señales/mes de shadow en EUR/USD: la pregunta que ese shadow iba a contestar en
11 meses ya está contestada, y la respuesta es no.

## La implicación grande, que va más allá de D1

El detector que se midió acá —`detect_structure_signals`— es **el mismo** que
alimenta structure (M5), m15 y h1 en vivo. Sobre 21 instrumentos y 7 años no
muestra edge ni antes de costos. Eso es consistente con el registro en vivo: 595
trades, −$472, PF 0,55, los cuatro tracks negativos.

Conclusión honesta: **el problema de AIdan no son los filtros, los umbrales ni la
gestión — es el generador de señal.** Los últimos meses de trabajo (piso de ATR,
break-even, expiry de news, castigo por nivel flojo) reducen el sangrado de un
motor que no tiene edge que proteger. Ninguna cantidad de ajuste sobre eso llega a
PF > 1,3.

Eso no dice "AIdan es imposible". Dice que el siguiente paso honesto no es otro
tweak, y hay que elegir explícitamente entre buscar generación de señal distinta
(con este mismo rigor y sabiendo que la mayoría de los intentos van a morir) o
parar. Es una decisión del user, no técnica.

## Reproducir

    python tools/backtest_multi_symbol.py --session off              # los 20 de Fase 1
    python tools/trendiness_er.py                                    # ER, solo precio
    python tools/backtest_multi_symbol.py --symbols CHFJPY,GBPCAD,GBPNZD,NZDCAD,NZDCHF,NZDJPY --session off

Declaraciones previas: `docs/fase1_pares_declarados.md` (commit `5a7d57e`),
`docs/fase1b_prediccion_registrada.md` (commit `2269691`).
