# Análisis Cualitativo M5 (8 May 2026)

**Sample**: 152 trades archived (Track A — M5 producción)
**WR**: 35.5%
**Total PnL**: -$167.51

---

## Hallazgos brutales

### 🔴 1. CALL pierde MUCHO MÁS que PUT

| Direction | Trades | WR | PnL |
|---|---|---|---|
| CALL | 66 | **25.8%** | **-$116.50** |
| PUT | 86 | **43.0%** | -$51.01 |

**CALLs son el bottom-tier**. PUTs son cerca de break-even. Esto sugiere sesgo del mercado en el período (bearish dominant) o problema con detección de setups bullish.

### 🔴 2. Confidence >70 es **ANTI-predictivo**

| Conf bucket | Trades | WR | PnL |
|---|---|---|---|
| **0-49** | 12 | **41.7%** | **+$5.90** ✅ |
| 50-59 | 22 | 36.4% | -$32.21 |
| 60-69 | 47 | 38.3% | -$41.50 |
| 70-79 | 47 | 36.2% | -$59.30 |
| 80-89 | 15 | **26.7%** | -$20.50 |
| 90-100 | 9 | **22.2%** | -$19.90 |

**Lectura**: la formula de confidence está inversamente correlacionada con outcome. Cuanto más "segura" la señal, más pierde. La única zona positiva (<50) está bloqueada por nuestro `min_confidence=60`.

### 🔴 3. HTF alignment NO ayuda

| HTF status | Trades | WR | PnL |
|---|---|---|---|
| Aligned | 100 | 34.0% | -$109.51 |
| Counter | 52 | **38.5%** | -$58.00 |

**Counter-HTF tiene MEJOR WR que aligned.** Lo opuesto de lo que asumíamos. Hace cuestionable nuestros filtros counter-HTF (v3.14.0, v3.16.0).

⚠️ Caveat: counter-HTF puede tener menos trades pero pierde menos absoluto, lo cual es coherente con que los filtros eliminaron los peores. Necesita analysis con SL hit detallado para conclusión robusta.

### 🟢 4. SMC es el ÚNICO trigger rentable en M5

| Trigger | Trades | WR | PnL | Avg/trade |
|---|---|---|---|---|
| **smc** | 19 | **42.1%** | **+$5.80** ✅ | +$0.31 |
| news | 32 | 40.6% | -$19.01 | -$0.59 |
| structure | 97 | 34.0% | -$129.30 | -$1.33 |
| pre_planned | 4 | **0.0%** | -$25.00 | **-$6.25** ❌ |

**SMC es el único trigger positivo.** Structure (el más usado) es el que más pierde.
**pre_planned es disastroso**: 4/4 losses, -$6.25/trade.

### 🔴 5. Hour UTC 14 (11 AR) es carnicería

Top 6 PnL por hora:

| UTC | AR | Trades | WR | PnL |
|---|---|---|---|---|
| 16h | 13h | 19 | 47.4% | **+$6.10** ✅ |
| 11h | 8h | 7 | 28.6% | +$2.40 |
| 19h | 16h | 10 | 30.0% | -$5.60 |
| ... | ... | ... | ... | ... |
| **14h** | **11h** | **18** | **22.2%** | **-$47.90** 🔴 |

Hora UTC 14 (11 AR) tuvo 18 trades y perdió 78%, -$47.90. Casi un tercio de la pérdida total M5 viene de esa hora.

⚠️ Recordatorio: removimos hour gate UTC 12/14/20 en v3.17. Esta data sugiere que UTC 14 sí es mala — pero la muestra incluye trades pre-fix con varios filtros distintos, **data contaminada**.

### ✅ 6. Expiry-loss NO domina en M5

| Cierre | Trades | % |
|---|---|---|
| SL hit | 86 | 57% |
| TP hit | 54 | 36% |
| Expired (timeout) | 12 | 8% |

Solo 8% expiran. El problema dominante en M5 es **SL hit** (57%), no expiry. Contradicen el discurso "expiry mata trades correctos" — eso era más visible en M15/H1.

---

## Hipótesis testables (con próximos 50+ trades)

| H | Hipótesis | Acción si confirmado |
|---|---|---|
| H1 | CALLs M5 estructuralmente peor que PUTs | Asymmetric filter: subir min_conf CALL a 70, mantener PUT 60 |
| H2 | Conf >80 anti-predictiva en M5 | Re-bajar conf_ceiling a 75 |
| H3 | SMC es el trigger más confiable | Considerar M5 = solo SMC trigger (eliminar structure/news/pre_planned) |
| H4 | pre_planned destructivo | **Desactivar pre_planned** ya (4 losses en 4 trades) |
| H5 | UTC 14 perdedora estructural | Re-activar hour gate específico para UTC 14 |
| H6 | M5 break-even si filtramos mejor | Posible salvar M5 con filtros direccionales |

---

## Comparación con M15+H1

| Track | Trades | WR | Net PnL | Trigger ganador |
|---|---|---|---|---|
| **M5** (152) | 35.5% | -$167.51 | smc only |
| **M15** (6) | 66.7% | +$3.72 | structure |
| **H1** (3) | 100% | +$3.58 | structure |

M5 tiene 25x más data que M15, 50x más que H1. **Su ineficiencia podría ser estructural del timeframe**, no falta de tuning.

---

## Recomendación a nivel sistema

**El M5 actual NO es salvable con tuning incremental.**

Los problemas son estructurales:
- CALL/PUT asimétrico
- Confianza inversa
- HTF alignment no funciona
- 57% de trades muere por SL hit

Las salidas reales son:
1. **Esperar M15/H1 confirmen ventaja** (1-2 semanas) → migrar tracks ganadores
2. **Reformular M5 a SOLO SMC trigger** (el único positivo) → reduce frecuencia 80% pero +EV
3. **Aceptar M5 como sandbox de aprendizaje** y operar real solo M15+H1

---

**Generado**: 9 May 2026
**Versión AIdan**: 3.24.0 (próxima)
**Siguiente análisis**: Mid-May post checkpoint M15
