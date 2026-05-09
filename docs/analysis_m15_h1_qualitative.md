# Análisis Cualitativo M15 + H1 (8 May 2026)

**Sample**: 9 trades cerrados (Track B M15: 6, Track C H1: 3)
**Período**: 5-8 May 2026
**Net PnL**: +$8.56 (Wins +$10.30, Losses -$1.74)
**WR**: 78% (7W/2L)

---

## Resumen al grano

| Métrica | Valor |
|---|---|
| Total trades | 9 |
| Wins | 7 (78% WR) |
| Losses | 2 |
| Net PnL | **+$8.56** |
| Direction split | **9 CALLs, 0 PUTs** ⚠️ |
| Avg win | +$1.47 |
| Avg loss | -$0.87 |
| **TP capture promedio** | **17% del TP nominal** ⚠️ |

## Hallazgos críticos

### 1. ⚠️ El TP nominal está demasiado lejos

| # | Trigger | Capturó | TP nominal | % capturado |
|---|---|---|---|---|
| 403 | m15_structure | 6.5p | 18p | **36%** (mejor) |
| 410 | h1_structure | 11.9p | 48p | 25% |
| 406 | m15_structure | 4.7p | 19p | 25% |
| 412 | h1_structure | 6.5p | 48p | 14% |
| 411 | m15_structure | 1.9p | 18p | 11% |
| 404 | m15_structure | 0.9p | 18p | 5% |
| 413 | h1_structure | 1.5p | 48p | 3% |

**Promedio: 17% del TP capturado**. El sistema cierra los wins ANTES del TP — probablemente por expiry timer (M15 45min, H1 180min) o trailing.

**Implicación**: el TP nominal está **5-6x más lejos de lo necesario**. Si reducimos TP a ~30% del actual:
- M15: TP 18p → **6p** (más cerca del breakeven post-comm 0.7p)
- H1: TP 48p → **15p**

Esto subiría dramáticamente el WR (más TPs hit) pero bajaría avg win. Net effect: probablemente **mejor PF**.

### 2. 🔴 Bug detectado: duplicados en mismo level

| Level | Trades | Outcomes |
|---|---|---|
| **1.17769** (resistencia) | #412, #413 | win, win |
| 1.17716 (resistencia) | #404, #405 | win, loss |

**#412 y #413 son el MISMO setup** (breakout sobre 1.17769) ejecutado 2 veces. El sistema no deduplica por level + dirección. **Ambos ganaron por suerte** — pero pudieron haber perdido ambos.

Necesita: dedup por `(level, direction)` con cooldown ~30min H1.

### 3. ⚠️ Confidence NO predice outcome

| Conf | Trades | Outcome |
|---|---|---|
| 90 | 1 | LOSS |
| 87 | 2 | win, win (mismo setup duplicado) |
| 81 | 1 | win |
| 80 | 1 | win |
| 70 | 1 | win |
| 69 | 1 | LOSS |
| 64 | 1 | win |
| 60 | 1 | win |

**Conf 90 perdió, conf 64 ganó.** En este sample, confidence no es predictivo. Podría ser ruido (muestra chica) o señal de que el formula de confidence está calibrada para M5 y no M15/H1.

### 4. ⚠️ ZERO PUTs en muestra

**Todos los 9 trades son CALL.** El sistema no tomó PUTs M15/H1 durante el período. Razones posibles:
- HTF bullish dominante en estos días → counter-both filter bloqueó PUTs
- Mercado en uptrend, structure scanner detectó solo continuation/breakout alcista

**No hemos validado el comportamiento bearish de M15/H1.** Esperar sesión bearish para confirmar simetría.

### 5. ✅ Setups por tipo

| Setup | Trades | WR | PnL | Avg win |
|---|---|---|---|---|
| **Continuación (rebote en soporte)** | 4 | 75% | +$6.38 | +$2.65 |
| **Breakout (sobre resistencia)** | 5 | 80% | +$2.18 | +$0.59 |

**Continuación es más rentable** (mayor avg win). Breakout es más estable pero capturas chicas.

### 6. Distribución horaria (AR)

| Hora AR | Trades | WR | PnL |
|---|---|---|---|
| 11:00 | 2 | 100% | +$3.72 |
| 12:00 | 2 | 50% | +$1.98 |
| 13:00 | 1 | 0% | -$1.56 |
| 14:00 | 1 | 100% | +$2.24 |
| 15:00 | 1 | 100% | +$0.84 |
| 17:00 | 2 | 100% | +$1.34 |

**Hora 13:00 AR (UTC 16) — único loss directional**. Posible patrón si se sostiene con más data.

---

## Hipótesis testables (para validar con próximos 20+ trades)

| H | Hipótesis | Acción si confirmado |
|---|---|---|
| H1 | TP nominal está 5x demasiado lejos | Reducir TP M15: 18p → 6p, H1: 48p → 15p |
| H2 | Duplicados en mismo level → no son trades independientes | Dedup por (level, direction) con cooldown |
| H3 | Conf no predictiva en M15/H1 | Recalibrar conf formula para tracks B/C |
| H4 | Continuación > Breakout | Reweight scanner: priorizar continuation |
| H5 | Sistema falla en bearish | Esperar sesión bearish para validar |

---

## NO actuar todavía

**TODAS las hipótesis arriba son sobre 9 trades.** Son patterns *sugestivos*, no concluyentes. **NO cambiar nada hasta tener 30+ trades por track**.

Pero hay un bug real para arreglar: **la deduplicación de levels** (#412/#413 mismo breakout). Eso SÍ se puede fijar sin necesidad de muestra mayor.

---

**Generado**: 8 May 2026 23:15 AR
**Versión AIdan**: 3.22.0
**Próximo análisis**: 15 May 2026 (después del checkpoint M15 30 trades)
