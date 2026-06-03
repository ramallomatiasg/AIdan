# AIdan — Market Playbook (registro de regímenes y acción ideal)

**Propósito**: catalogar los tipos de mercado que AIdan enfrenta, qué señales/contexto los identifican, y cómo *debería* accionar en cada uno. Documento VIVO — se actualiza con cada hallazgo.

**Regla de oro (no negociable)**: lo que está marcado `[HIPÓTESIS]` NO se implementa como filtro hasta pasar el gate de significancia (`src/optimizer/significance.py`): n≥25 y que el subset se distinga del baseline 37.4% (binomial + Wilson CI 95%). Lo marcado `[EVIDENCIA]` ya está validado o es comportamiento confirmado. Esto evita convertir el playbook en una lista de parches sin datos (el error recurrente del proyecto: hour gate, late breakout 3p, gates v3.34.0 — todos removidos por ruido).

**Cómo leer las señales** (endpoints `/market-state`, `/smc-state`):
- `trend` + `trend_strength`: dirección M5 (bullish/bearish/neutral × strong/moderate/weak)
- `htf_bias`: dirección macro (H1+M15 combinados, vía SMC)
- `regime`: trending / ranging / uncertain (+ `regime_score`)
- `avg_range_pips` (ATR): volatilidad. Pisos actuales: M5 2.0p, M15 5p, H1 10p. Techo 6p.
- `rsi` + `rsi_zone`
- alineación M5 vs HTF: el eje clave para el riesgo del trade

---

## Régimen 1 — Lateral muerto / quiet  `[EVIDENCIA: acción correcta]`
- **Identificar**: ATR < 2.0p, regime ranging/uncertain, velas promedio 1-2p, RSI neutral. Típico: feriados (lun 25 May US/UK), madrugada, post-cierre NY.
- **Qué hace AIdan**: nada (ATR floor 2.0p bloquea). ✓ correcto.
- **Acción ideal**: NO operar. La comisión (~0.7p) se come cualquier movimiento de 1-2p. Esperar.
- **Evidencia**: semana 25-26 May (ATR 1.5-2.3p) → 0-1 trades/día, correcto. Bajar el floor a <2.0 sería regalar plata.

## Régimen 2 — Tendencia fuerte alineada (M5 + HTF de acuerdo)  `[EVIDENCIA: mejor caso]`
- **Identificar**: ATR 3-5p, regime trending, trend_strength strong/moderate, M5 y HTF en la MISMA dirección.
- **Qué hace AIdan**: opera a favor. ✓
- **Acción ideal**: tomar los trades alineados con la tendencia. Es el escenario más rentable.
- **Evidencia**: lun 1 Jun → 4/4 wins (+$20.70), news+structure+smc todos a favor del movimiento.
- **Ojo**: SIM A bloquea trades "fully-aligned" extremos (M5+HTF+regime todos máximos) por exhaustion — eso es correcto, no confundir con esto.

## Régimen 3 — Ranging / chop (rango chico, sin dirección)  `[EVIDENCIA + HIPÓTESIS]`
- **Identificar**: ATR ~2.0-2.7p (apenas sobre el floor), regime ranging, RSI ~45-55 (neutral), precio oscilando en banda <12p, trend_strength weak.
- **Qué hace AIdan**: a veces espera (✓), a veces toma "breakouts" que son falsos y revierten (✗).
- **Acción ideal `[HIPÓTESIS a verificar]`**: en ranging, los breakouts son falsos (toca nivel y vuelve). Requerir confirmación más fuerte o no operar breakouts. El precio que *toca* resistencia ≠ la *rompe*.
- **Evidencia**: lun 1 Jun tarde + vie 29 May tarde → AIdan esperó correctamente. Pero hay días donde el chop genera entradas perdedoras.
- **A verificar el viernes**: ¿los trades en regime=ranging pierden significativamente vs trending?

## Régimen 4 — Conflicto M5 vs HTF (señales opuestas)  `[HIPÓTESIS — el más peligroso]`
- **Identificar**: M5 trend en una dirección, htf_bias en la OPUESTA. Mercado indeciso.
- **Qué hace AIdan**: se apoya en HTF para operar contra el M5 → suele perder cuando el M5 domina el día.
- **Acción ideal `[HIPÓTESIS a verificar]`**: cuando M5 contradice fuerte al HTF, favorecer la dirección del M5 (el corto plazo manda intradía) o quedarse afuera. NO comprar contra la tendencia M5 vigente.
- **Evidencia**: mar 2 Jun → htf_bias bullish todo el día PERO M5 bearish todo el día. AIdan tomó 4 CALLs (con HTF, contra M5) → todas perdieron. El único win fue el PUT a favor del M5.
- **Filtros existentes relacionados**: counter-both (M5+HTF ambos contra el trade → block) ya existe; counter-HTF news ≥60. Pero el caso "M5 manda y HTF estorba" no está cubierto.

## Régimen 5 — Falling knife / sobrevendido en caída fuerte  `[HIPÓTESIS — recurrente, documentado]`
- **Identificar**: trend bearish strong/moderate + RSI < 30 (sobrevendido). (O el espejo: bullish strong + RSI > 70.)
- **Qué hace AIdan**: ve "RSI bajo = barato = va a rebotar" y compra CALL → el precio sigue cayendo. "Agarra el cuchillo que cae."
- **Acción ideal `[HIPÓTESIS a verificar]`**: RSI sobrevendido NO es señal de compra en tendencia bajista fuerte — confirma que la tendencia es fuerte. Evitar CALLs cuando trend=bearish strong y RSI<30 (y espejo para PUTs).
- **Evidencia**: mar 2 Jun → #560 (RSI 29), #561 (RSI 27), #562 (RSI 22) — 3 CALLs sobrevendidos en caída, todas perdieron. Patrón documentado hace tiempo en CLAUDE.md (glosario "catch-the-falling-knife").
- **A verificar el viernes**: ¿CALLs con trend=bearish strong & RSI<30 pierden significativamente? (juntar más casos).

## Régimen 6 — News stale (noticia vieja)  `[EVIDENCIA: acción correcta]`
- **Identificar**: noticia con published_at mucho antes del fetched_at (>30 min de antigüedad al procesarse).
- **Qué hace AIdan**: la saltea (freshness gate, price_at_alert=0). ✓
- **Acción ideal**: NO operar — el mercado ya reaccionó horas antes. Entrar es perseguir un movimiento que ya pasó.
- **Evidencia**: mar 2 Jun → news#3507 publicada 12:11 UTC, recolectada 14:05 UTC (~2h tarde) → correctamente saltada.
- **A vigilar**: si llegan MUCHAS news tarde, es latencia del colector (problema de infra, no de lógica).

## Régimen 7 — Volatilidad extrema / spike de news  `[EVIDENCIA]`
- **Identificar**: ATR > 6p, spread ensanchado.
- **Qué hace AIdan**: ATR ceiling 6p saltea (el SL queda muy pegado vs el ruido → SL hit por rebotes). + spread gate (skip si spread > 50% del SL).
- **Acción ideal**: esperar a que la volatilidad baje a rango operable (2-6p). Operar SL pegado en spike = SL hit garantizado.

## Régimen 8 — Entrada contra un rebote (dirección correcta, timing malo)  `[HIPÓTESIS — entry quality]`
- **Identificar**: dirección del trade ALINEADA con la tendencia fuerte (ej: PUT en bajista fuerte) PERO entrando justo sobre una vela de rebote contra-tendencia + RSI extremo (ej: <20 sobrevendido para un PUT) + SL pegado (~1× ATR).
- **Qué hace AIdan**: entra en el medio del rebote (shortea la vela verde / compra la roja) → el rebote sigue un poco más → toca el SL pegado → DESPUÉS el precio va a donde AIdan predijo, pero ya sin nosotros.
- **Acción ideal `[HIPÓTESIS a verificar]`**: con dirección correcta, NO entrar sobre la vela de rebote — esperar que el rebote se agote (vela de rechazo/continuación) y entrar desde mejor precio. Y/o dar más aire al SL (≥1.5× ATR) para sobrevivir el coletazo del rebote. RSI extremo = más riesgo de rebote, no menos.
- **Evidencia**: mar 3 Jun → **#565 PUT**, dirección correcta (precio cayó de 1.16009 a 1.1599 después), pero entró en 1.16009 sobre una vela verde de rebote, RSI 19.7, SL a 3.7p (ATR 3.4p ≈ 1× ATR) → stopeado en 1 min a 1.16046, y luego el precio cayó como AIdan predijo. **Entrada y SL la mataron, no la dirección.**
- **Distinguir de Régimen 5**: #5 = dirección EQUIVOCADA (comprar la caída). #8 = dirección CORRECTA, entrada/SL malos. Diagnóstico y arreglo distintos — no confundir.
- **A verificar el viernes**: ¿entrar tras confirmación (no en la vela de rebote) mejora WR?
- **⚠️ ARREGLO REFUTADO (3 Jun) — ensanchar el SL NO funciona**: análisis sobre 208 trades del archive por ratio SL/ATR:
  - `<1.0×` (pegado, como #565): n=93, WR **42%**, avg -$0.78
  - `1.0-1.5×`: n=56, WR 39%, avg -$0.62
  - `1.5-2.0×` (ancho): n=30, WR **23%**, avg **-$1.78** (PEOR)
  - `>2.0×`: n=29, WR 31%, avg -$0.61
  El SL ancho rescata algún rebote PERO sangra más en los trades genuinamente equivocados → neto peor. El SL pegado es el de mejor WR. **No tocar el ancho del SL.** El #565 fue hindsight: para cada #565 salvado, varios otros pierden más. Queda como lección: la solución NO es el SL. Si hay arreglo, es el TIMING de entrada (esperar agotamiento del rebote), que es más difícil y la versión naive (gates v3.34.0) ya fue ruido.

---

## Resumen — matriz rápida

| Mercado | Señal clave | Acción AIdan | Estado |
|---|---|---|---|
| Lateral muerto | ATR <2p | No operar | ✓ evidencia |
| Tendencia fuerte alineada | ATR 3-5p, M5=HTF | Operar a favor | ✓ evidencia |
| Ranging/chop | ATR ~2-2.7p, regime ranging | Evitar breakouts | hipótesis |
| Conflicto M5 vs HTF | M5 ≠ HTF | Favorecer M5 o afuera | hipótesis |
| Falling knife | trend fuerte + RSI extremo contra | No comprar el rebote | hipótesis (recurrente) |
| News stale | >30min vieja | Saltear | ✓ evidencia |
| Volatilidad extrema | ATR >6p | Esperar | ✓ evidencia |
| Entrada contra rebote | dir correcta + entra en vela de rebote + SL ~1×ATR | Esperar agotamiento del rebote + SL ≥1.5×ATR | hipótesis (entry quality) |

## Cómo evoluciona este doc
Cada checkpoint (viernes) o hallazgo nuevo: agregar régimen o mover una `[HIPÓTESIS]` a `[EVIDENCIA]` SOLO si pasó el gate de significancia. Si una hipótesis se refuta (resulta ruido), anotarlo también — los "no funcionó" valen tanto como los "sí".

---
**Creado**: 2 Jun 2026 (tras día 1/6 que destapó los regímenes 4 y 5).
**Última actualización**: 3 Jun 2026 — +Régimen 8 (entry quality: #565 PUT dirección correcta pero entró sobre rebote con SL pegado → stopeada antes de acertar).
