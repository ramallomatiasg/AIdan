# Plan de Mejora Continua del "Cerebro" — acordado 12 Jun 2026

> **El diagnóstico que origina este plan** (checkpoint 12 Jun, broker-truth):
> el 94% de los fills son inmediatos y al precio planeado — y pierden igual.
> **La ejecución no es el problema; la DECISIÓN sí** (qué señala y cuándo).
> Este plan organiza cómo se corrige eso: no con UNA idea, sino con un LOOP.

---

## El principio: el cerebro no se "arregla" — se le construye un proceso

Las 3 veces que intentamos arreglarlo de un saque (ML predictor, entry gates,
hour gates) fueron espejismos sobre data sucia. Lo que SÍ movió la aguja fue el
loop que este mes construimos sin darle nombre:

```
PÉRDIDA → forense (broker-truth) → hipótesis → MEDICIÓN (gate adversarial)
   → shadow (clasificación en el momento) → activar UNO → re-medir → mantener/revertir
```

Casos que ya recorrieron el loop completo: cooldown 5min (activado 12 Jun),
bounce (en shadow, no concluyente — el loop evitó un error), bias rezagado
(refutado — el loop evitó otro error). **El plan = institucionalizar este loop.**

---

## El ritual semanal (la mecánica del loop)

**Lunes a jueves — el sistema corre, NADIE toca nada.**
- Los shadows acumulan clasificación limpia: bounce, event-window, calendar,
  PM log, cooldown skips.
- Solo se arreglan bugs de plomería (no de estrategia).

**Viernes — checkpoint (60-90 min):**
1. Re-correr la suite de medición (`tools/measure_entry_suspects.py` + lo que
   se vaya sumando). Son segundos.
2. Revisar cada experimento vivo contra su criterio de éxito ESCRITO.
3. Activar **a lo sumo UN cambio** — el de evidencia más fuerte que pase el
   gate (binomial + Wilson CI vs baseline; default = ruido).
4. Todo cambio activado lleva escrito ANTES: qué mide su éxito, y la condición
   de reversión (ej.: "si en 2 semanas el WR del subset no mejora → revert").

**Reglas duras del loop** (las lecciones pagadas):
- Outcomes REALES del broker, nunca simulados.
- Clasificación EN el momento (shadow), nunca reconstruida.
- n chico o CI que cruza el baseline = "no sé" = no actuar.
- Un cambio a la vez. La carga de la prueba la tiene el cambio.

---

## Las ideas, rankeadas por evidencia (el backlog del cerebro)

### YA en el pipeline (corriendo o activado)
| # | Idea | Estado | Decide |
|---|---|---|---|
| 1 | Cooldown 5min post-pérdida | **ACTIVO** (v3.40.15) | re-medir 26 Jun |
| 2 | PM: extender ganadores + cortar sangrías | **ACTIVO** (re-baseline 10 Jun) | 24 Jun (~2 sem) |
| 3 | Event-awareness (etiquetado + escudo shadow) | **SHADOW** | ~26 Jun-3 Jul |
| 4 | Straddle calendar | **SHADOW** (feed vivo 12 Jun) | con #3 |
| 5 | Bounce-skip | **SHADOW** | cuando n limpio alcance |

### Próximas a entrar (en orden — UNA por semana como máximo)
6. **Detector de régimen en vivo → gate por régimen** ← LA GRANDE del corto plazo.
   El playbook documenta 8 regímenes y el sangrado viene de chop/whipsaw, pero
   AIdan no SABE en qué régimen está. Construir un clasificador mecánico simple
   (ATR relativo, % de velas alternantes, distancia a eventos) y correrlo en
   SHADOW: etiquetar cada señal con su régimen → en 2-3 semanas medir WR por
   régimen × trigger → si "m15 en chop = 20% WR, n>30, gate pasa" → bloquear
   esa celda. Ataca el "CUÁNDO" directamente con el método que ya funciona.
7. ~~**Métrica de agotamiento ("¿cuánto ya corrió el precio?")**~~ ✅ MEDIDA 12 Jun
   → **DESPRIORIZADA**: ningún bucket de run-up crudo separa del baseline en la
   medición limpia (n=617 broker-truth). Bonus metodológico: el único bucket
   "significativo" (56% WR, p=0.010) era **lookahead de la vela en formación**
   — regla nueva permanente: toda medición retrospectiva sobre velas corta
   ≥300s antes del entry. El agotamiento que rima en los hallazgos es de
   ALINEACIÓN DE INDICADORES REZAGADOS (no de precio crudo) → solo medible con
   etiquetado en-el-momento; queda en backlog sin prioridad.
8. **Exportar el patrón de `smc` a `structure`** — smc es el ÚNICO trigger +EV
   (PF 1.14) y es el paciente (zona + confirmación); structure es el ansioso
   (persigue el breakout) y el mayor sangrador (−$158). Hipótesis: exigirle a
   structure una confirmación tipo-smc (retest/cierre confirmatorio) lo acerca
   al patrón ganador. Primero MEDIR retrospectivo (¿breakouts con retest
   rinden mejor?), después shadow.
9. **Jugada de eventos** (la decisión de #3/#4): straddle vs momentum
   post-release (única con win vivo: #604 +5.30 a 7min del CPI) vs skip.

### La apuesta de mediano plazo (gated por data limpia)
10. **Calibración empírica del P(ganar)** — reemplazar el confidence mentiroso
    por probabilidad real (regresión logística, walk-forward, validación
    adversarial). **Gate: ~150 trades limpios** (al ritmo actual: fin de junio
    para el primer intento; ~300 a mediados de julio para el robusto).
    Si funciona → se convierte en EL número de decisión (gate + sizing).
    Si no funciona (posible: ML ya falló a n=276 sucio) → la conclusión es que
    el cerebro se gobierna por celdas régimen×trigger (idea 6) + guardrails,
    no por un score. Ambos resultados son progreso.
11. **Sizing por calidad** (solo DESPUÉS de 10): apostar más a las entradas
    de mayor P(ganar) y menos a las marginales. Kelly fraccionado. Hoy es
    imposible porque el número de confianza miente.

### La pregunta estructural (julio — no antes, no después)
12. **¿El juego es ganable?** Con el veredicto de la data limpia: si M5/M15
    scalping no paga la comisión (87% del drag) ni con cooldown + PM + régimen
    + eventos → decisión de pivot: swing H4/D1 (backlog #10, comisión se
    diluye, timing fino importa menos) o concentrar en el nicho +EV (smc
    paciente + eventos). Fecha tentativa de esa conversación: **checkpoint
    del 17 Jul** (con ~300 limpios).

### Lo que NO entra (y por qué)
- ❌ Más sofisticación del LLM de news ahora (es el evaluation gap — proyecto
  de medición aparte, no de cerebro).
- ❌ Más ML antes de la masa limpia (ya refutado 2 veces).
- ❌ Filtros estáticos nuevos sin pasar por el gate (hour gates, etc. — ya
  fueron y volvieron).
- ❌ Tocar `dynamic_conf` a mano (regla vigente).

---

## Calendario de checkpoints (próximas 6 semanas)

| Fecha | Decisiones |
|---|---|
| **19 Jun** | 1er read del cooldown (n chico, solo sanity). Activar shadow del detector de régimen (idea 6). Calendar: ¿escribió con la instrumentación v3.40.16? Reconciliar universos lifetime + query canónica del censo limpio. Decisión mt5_filled_at + #632 (pnl NULL). |
| **26 Jun** | Veredicto PM (2 sem de re-baseline): ¿avg_win subió? Keep/revert. Cooldown: 2 semanas de skips — ¿los skipeados eran perdedores? (medible: qué pasó después de cada skip). |
| **3 Jul** | Jugada de eventos (3 sem de event_window_log + calendar shadow). Primer intento de calibración si hay ~150 limpios. |
| **10 Jul** | Régimen: ¿hay celdas régimen×trigger bloqueables? (3 sem de shadow). |
| **17 Jul** | **LA GRANDE**: con ~300 limpios — calibración robusta + la pregunta estructural (¿el juego es ganable? ¿pivot?). |

---

## Cómo se ve "ganar" (criterios honestos)

- **Corto plazo (jul)**: PF sostenido >1.0 con los gates medidos puestos
  (= deja de perder). El baseline actual es PF ~0.55-0.75.
- **Mediano (ago)**: PF >1.3 sostenido 4+ semanas (el target original) →
  habilita la conversación de cuenta real (con los criterios de
  `project_real_account_goal.md`).
- **Si para el 17 Jul la data dice que no se puede**: el plan YA tiene la
  puerta de salida digna (pivot a swing o nicho), y todo lo construido
  (PM, event-awareness, loop de medición, data limpia) se lleva al pivot.

*Actualizar este doc en cada checkpoint. Regla: hilo cerrado → ✅ y fecha;
idea nueva → entra rankeada por evidencia, no por entusiasmo.*
