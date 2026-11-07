# P26 — Valor en FX (tipo de cambio real vs su promedio de 5 años): criterio declarado ANTES de medir (7-nov-2026)

**Hipótesis (Asness-Moskowitz-Pedersen 2013; Menkhoff-Sarno-Schmeling-Schrimpf 2017):** las monedas que en
términos REALES (ajustado por inflación) están lejos por debajo de su promedio de largo plazo tienden a
recuperarse en los meses siguientes, y las caras a devolver. Es el tercer premio clásico del FX junto a carry
(P11/P14, medido) y momentum (Fase 4 E4, loop P22, medido); el único que este proyecto nunca midió.
Tipo **A** de la escalera (`docs/fuentes_de_ventaja_2026-11-04.md`): premio por riesgo de horizonte largo,
no adivina dirección intradía; costo despreciable frente al movimiento mensual.

## Datos (públicos, FRED, vía `tools/hyp_data.py`, sin MT5)
- **Tipo de cambio real efectivo amplio del BIS** (mensual, 1994 →): RBXMBIS (EUR), RBJPBIS, RBGBBIS,
  RBCHBIS, RBCABIS, RBAUBIS, RBNZBIS. Verificado antes de declarar que existen (no se miró ningún retorno).
  Se usa el REER y no PPP bilateral con IPC porque las series de IPC de la OCDE en FRED están discontinuadas
  y el REER ya es el tipo de cambio deflactado por precios (subir = la moneda se encarece).
- **Precio:** fixing diario de FRED (DEXUSEU, DEXJPUS, …), último dato del mes.
- **Tasas a 3 meses** (IR3TIB01xxM156N) para el diferencial; si la serie termina antes, se arrastra el último.
- **Costo:** `COST_PIPS` de `hyp_data` (0,8-1,3 pips ida y vuelta) cobrado sobre la rotación de cada mes.

## Regla (fija, sin parámetros que buscar)
- Universo: EUR, JPY, GBP, CHF, CAD, AUD, NZD contra USD.
- **Señal** de la moneda i al cierre del mes t: `v_i = ln(REER_i) − media de ln(REER_i) en los 60 meses previos`,
  usando el REER del mes **t−2** (publicación del BIS con margen; el FRED actual va todavía más atrasado,
  pero la señal es lenta).
- **Cartera:** largo las **2 más baratas** (v más bajo) contra USD y corto las **2 más caras**, pesos iguales.
  Neutral al dólar por construcción. Rebalanceo mensual.
- **Retorno del mes t+1** de cada pata = retorno del precio en USD por unidad de moneda + diferencial de tasas
  (tasa_i − tasa_USD)/12 conocido en t (exceso de retorno, como en los papers). Cartera = media de largos −
  media de cortos, menos costo por la rotación.

## Muestras
- **Descubrimiento:** 1999-01 → 2014-12. **Reserva:** 2015-01 → último mes con datos. Se miran las dos en la
  misma corrida (la regla está congelada acá; no hay nada que ajustar entre una y otra).

## Control (placebo)
Mismo calendario, mismos costos, pero cada mes las 7 monedas se ordenan **al azar** (2000 repeticiones) →
percentil 95 de la media mensual neta en la muestra completa. Responde: ¿la señal elige mejor que cualquier
cartera 2 contra 2?

## Criterios (PASA = los 5)
1. n ≥ 150 meses en descubrimiento y ≥ 100 en reserva.
2. Descubrimiento: media mensual neta > 0 y extremo inferior del CI95 (bootstrap por bloques de 12 meses) > 0.
3. Reserva: media mensual neta > 0.
4. Media mensual neta de la muestra completa > percentil 95 del control.
5. Las dos mitades cronológicas de la muestra completa con media neta > 0.

## Descriptivo (no decide)
- Solo precio (sin diferencial de tasas): separa valor de carry.
- Correlación mensual con una cartera de carry 2 contra 2 (mismas monedas): si es alta, es carry disfrazado.
- Señal con REER de t−4 (robustez al rezago de publicación).
- Retorno anual, Sharpe, caída máxima, por año.

## Si PASA
No se activa (AIdan opera EUR/USD intradía y la cuenta es chica). Siguiente paso a proponer al user: sumar
`value_5y_z` al catálogo de P22 y un shadow mensual en papel con la regla congelada.
## Si NO PASA
Cerrar valor REER 5 años en G8 con esta regla. No buscar otra ventana (3/10 años), otro número de patas ni otro
rezago.
