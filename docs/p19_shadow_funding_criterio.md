# P19 — shadow en papel del carry de funding (P15) — criterio declarado ANTES de juntar

**Fecha:** 27-oct-2026 (rutina semanal, 1ra de la cola). **Tool:** `tools/shadow_funding.py` (read-only respecto de
AIdan: sin MT5, no toca la DB de AIdan, no tiene ninguna llamada que mande órdenes; escribe solo en su base
`%APPDATA%/AIdan/state/funding_shadow.db`). Datos PÚBLICOS de Binance, sin cuenta ni clave.

## Pregunta

P15 pasó (+4,8%/año, también fuera de muestra) pero 2025-26 rindió casi cero. **¿El premio sigue vivo HOY, con la
regla congelada, y la ejecución real (spread spot + perpetuo al momento de decidir) se parece a lo que asumió el
backtest?**

## Qué hace (sin cambiar nada de P15)

- **Libro en papel:** el MISMO motor `simulate` de `tools/backtest_p15_funding.py` (importado, no copiado), las 6
  principales (BTC, ETH, SOL, BNB, XRP, DOGE), reglas, umbrales y costos de P15 sin tocar, sobre datos de Binance
  desde **el 27-oct-2026 00:00 UTC** (con 7 días previos solo para calentar la señal). Se reconstruye entero en cada
  corrida desde los datos públicos ⇒ no depende de que la PC esté prendida a la hora de cada decisión.
- **Foto de ejecución** en cada corrida: bid/ask de spot y perpetuo, precio de marca, último funding y la decisión
  que tomaría la regla en ese momento. Mide el costo real de entrar (medio spread de cada pata) contra el
  deslizamiento que asumió P15 (0,02% por lado y pata).

## Criterio (pre-declarado, NO mover)

Lectura a los **90 días** (~25-ene-2027, 270 períodos de 8 h); decisión a los **180 días** (~25-abr-2027).

1. **Premio vivo:** rendimiento anualizado neto del libro en papel > tasa libre de riesgo (fed funds del último
   mes disponible en `docs/p11_policy_rates.csv`).
2. **Ejecución:** mediana de (medio spread spot + medio spread perpetuo) en las fotos ≤ 0,02% del nocional
   (lo asumido por P15 por lado; el 0,04% restante de P15 era comisión, que no se mide acá).
3. **Sin mirar el futuro en vivo:** las decisiones de las fotos coinciden con las del libro reconstruido en ≥ 95%
   de los casos comparables (si no, el backtest usaba información que en vivo no existe).

**Pasa (1+2+3) a los 180 días ⇒** proponer al user el paso siguiente (testnet o monto chico), con el riesgo de
exchange explícito. **No pasa (1) a los 180 días ⇒** cerrar la línea de funding y borrar la tarea. **(2) o (3)
fallan ⇒** el backtest de P15 no vale como estaba: re-medirlo con el costo/la señal observados antes de seguir.

## Límites

- 180 días es poco para un premio que depende del régimen (2021 vs 2025): un NO PASA dice "hoy no paga", no "nunca".
- Las fotos dependen de que la PC esté prendida; el libro no.
- Riesgo de exchange (quiebra, retiro bloqueado) no se mide en papel.
