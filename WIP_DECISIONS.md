# WIP_DECISIONS.md — sesión 19 Ago 2026

> Escrito PRIMERO por riesgo de apagado de la PC. **La PC no se apagó: el trabajo se
> completó.** Estado final abajo, en "Qué quedó hecho". Se deja el documento como registro
> de las decisiones tomadas y de lo que quedó pendiente.

## ⚠️ VERIFICACIÓN CONTRA EL CÓDIGO VIVO (v3.56.0) — el brief está parcialmente VIEJO

El `AUDIT_REPORT.md` es del **31 Jul (v3.47.1)** y **v3.48.0 ya implementó la Ola 1**. Medido
hoy, 19 ago, antes de tocar nada:

| Item del brief | Estado real | Acción |
|---|---|---|
| `setup_type` NULL en 546/546 | ❌ **YA ARREGLADO** — 61 filas pobladas, todas las nuevas | nada |
| Suite de tests rota (5F/24E) | ❌ **YA VERDE — 75 passed** | nada |
| Sacar creds de `config.py` para arreglar la suite | ❌ premisa falsa (suite verde CON las keys). Además hay **decisión previa del user de NO tocarlas** (repo privado, key trivial de regenerar) | **no se toca** — se avisa |
| Backup de DB / logs a disco | ❌ **YA EXISTEN** (`tools/backup_db.py`, `%APPDATA%\AIdan\backups\*.db`, `logs\aidan.log` rotado) | nada |
| Gemma escribe `recommended_sl_pips`/`tp_pips` en `post_trade_analysis` | ❌ **esas columnas NO EXISTEN**. El advice de SL/TP vive en `learning_insights` → `sl_tp_advice` y **ya se consume** en `compute_adaptive_sl_tp` (4 call-sites) | replantear |
| `adjust_setup_confidence` nunca invocado (`change_manager.py:322`) | ✅ **CONFIRMADO**: `get_confidence_adjustment_for_signal` no se llama desde ningún lado (`is_signal_blocked_by_meta_filters` sí, `db.py:1225`) | **hacer** |
| `directional_lessons` | no existe ninguna tabla lesson/retro/decision | **crear** |

**Dato clave para el diseño (verificado leyendo el código):** todos los gates de
`min_confidence` viven **dentro de los detectores**, antes de `add_auto_strategy`; y el `lot`
sale de `sl_pips`, **no** de la confianza (`mt5_executor.py:212+`). ⇒ **un nudge de confianza
aplicado en `add_auto_strategy` es frecuencia-neutro y tamaño-neutro POR CONSTRUCCIÓN.**
Eso satisface la restricción #1 sin depender de disciplina. **Contrapartida honesta: hoy el
nudge es INERTE sobre la ejecución** — su valor inmediato es (a) dejar registro estructurado
y (b) generar la muestra con la que después se decide si el veredicto discrimina. No vender
esto como "ya mejora el PnL".

**Composición de tracks hoy (desde 1-jul, broker-truth):** `news` n=24 −$22,80 · `h1` n=25
−$11,62 · `smc` n=7 −$11,20 || `structure` n=34 **+$7,50** · `m15` n=70 **+$9,03**. El patrón
del audit se sostiene: los 3 perdedores (−$45,62) se comen a los 2 buenos (+$16,53).

## Objetivo del pedido (user, 19 ago)

Mejorar la **toma de decisiones** de AIdan para empezar a ganar, **sin bajar frecuencia**.
El core: que AIdan pueda razonar retrospectivamente *"esta señal era CALL y no PUT por X
razones"* **ANTES** de tomar la próxima decisión.

## Restricciones duras (no negociables)

1. **No reducir frecuencia.** Todo cambio de confianza es *ajuste* (nudge), nunca filtro binario.
2. **Todo reversible**, detrás de flag inicialmente **OFF**. Excepciones (van ON):
   - bugfix de `setup_type` (solo escritura)
   - wireado de `adjust_setup_confidence` (ya validado por shadow)
3. **Backup de la DB** antes de cualquier cosa que la toque.
4. **Un test unitario mínimo por cambio.** Antes: arreglar la suite sacando las credenciales
   hardcodeadas de `src/common/config.py` (también cierra el hallazgo 🔴 del audit).
5. **Commits atómicos, sin `Co-Authored-By`, SIN push.**
6. Rebuild de `AIdan.exe` al final (el user corre desde el exe).

## Orden de trabajo (no invertir)

### Paso 0 — piso técnico
- [ ] Leer `F:\AIdan\AUDIT_REPORT.md` completo y alinear al roadmap (Olas 1 y 2).
- [ ] `tools/backup_db.py` (o reusar el existente) → backup con timestamp de
      `%APPDATA%\AIdan\state\financial_news.db` antes de tocar nada.
- [ ] Sacar credenciales hardcodeadas de `src/common/config.py` → env vars con default
      seguro. Objetivo inmediato: que la suite de tests vuelva a correr.
- [ ] Logs a disco (rotados) para todo lo nuevo.

### Ola 1 — quick wins (no bajan frecuencia)
- [ ] **`setup_type` poblado en el path de ESCRITURA** de trades (`auto_strategies` →
      `trade_archive`). Hoy NULL en 546/546, lo que mata de una: paso 6 de `dynamic_conf`,
      `block_setup_type` y `adjust_setup_confidence`.
      ⚠️ **Solo escritura. NO habilitar el paso 6 de `dynamic_conf` todavía** — primero
      juntar data limpia para calibrar (regla del proyecto: no calibrar sobre data sucia).
- [ ] **Wirear `adjust_setup_confidence`** (`change_manager.py:322`, nunca invocado). ~5
      líneas. Ya implementado y validado por shadow ⇒ va ON.
- [ ] **Consumir las recomendaciones SL/TP de Gemma** que ya se persisten en
      `post_trade_analysis` y hoy se descartan:
      agregador en `db.py` que promedie las últimas N `recommended_sl_pips` /
      `recommended_tp_pips` **ponderadas por `mt5_pnl`**, aplicado como **nudge acotado a
      ±20% del profile**. Flag OFF al inicio.

### Ola 2 — CORE del pedido: retrospectiva PRE-decisión
- [ ] **`src/analyzer/pre_trade_retrospective.py`**: antes de disparar, comparar la señal
      actual contra los últimos N trades **similares** (mismo símbolo + setup_type + bucket
      de volatilidad/ADX). Detectar "cuándo este setup ganó vs cuándo perdió".
      Si el patrón histórico apunta a la dirección **opuesta** (ej. "los últimos 5 setups
      iguales con ADX>30: CALL perdió, PUT ganó") ⇒ **modular la confianza + emitir alerta
      estructurada. NO bloquear.**
- [ ] **Log de la razón de decisión** por trade (features usados + veredicto de la
      retrospectiva), en tabla propia, para que el post-trade pueda decir "el PUT era
      correcto pero por Y razón que no considerabas".
- [ ] **Cerrar el loop**: cuando `post_trade_analyzer` concluya "hubiera sido mejor CALL",
      persistir la lección en **`directional_lessons`**, que la retrospectiva pre-trade
      consulta en la próxima decisión del mismo setup.

### Ola 3 — calibración (después de Ola 1+2)
- [ ] **Platt scaling** como post-proceso del output de `dynamic_conf` (NO reemplazarla).
      Ajustar sobre los ~139 trades limpios, persistir coefs, re-entrenar cada N trades.
      Contexto: `conf/100` da Brier 0.369 vs 0.37 de la constante ⇒ la confianza **no es
      probabilidad**, nunca usarla como tal (p.ej. sizing).
      *Nota del proyecto: un intento previo de Platt (5-ago) NO pasó su gate pre-declarado
      (0.2522 vs 0.2424). Re-hacerlo con `setup_type` ya poblado y declarar el gate ANTES.*
- [ ] **Track `news` detrás de `enable_news_track=False`** (feature toggle, NO borrar el
      código; alternativa: fila en `blocked_setups`). Ya medido sin habilidad direccional.
      ⚠️ **Ojo conflicto con decisión previa del user (7 ago): "news NO se apaga, se
      arregla", y hay un veredicto pre-declarado agendado para ~28 ago (v3.51.0).**
      ⇒ Implementar el toggle, dejarlo en su valor actual (news ON) y **confirmar con el
      user** antes de flippearlo. Se implementa el mecanismo, no la decisión.

## Cómo se mide si esto sirvió (2-3 semanas)

- **Frecuencia** (control de daño): trades/día por track antes vs después. Debe quedar plana.
  Si baja, algo se volvió filtro sin querer ⇒ revertir.
- **Retrospectiva**: cuántas señales fueron marcadas "contra-histórico" y qué WR tuvieron vs
  las no marcadas. Criterio a declarar ANTES de leer: si las marcadas no tienen WR
  materialmente peor, la retrospectiva no discrimina y el nudge se apaga.
- **`directional_lessons`**: cuántas lecciones se generaron y cuántas fueron consultadas
  (si se consultan 0 veces, el loop está muerto como lo estaba `learning_engine`).
- **SL/TP nudge**: recorrido de ganadores/perdedores contra su propio SL/TP, antes vs después.
- Gate de siempre: `n≥20-30` y CI95 que no cruce el baseline. Con n chico ⇒ "no sé" ⇒ no tocar.

## Notas de riesgo (metodología del proyecto)

- El principio rector es **"un fix que no arregla nada, EMPEORA"**. Todo lo de arriba que
  toca decisiones nace OFF o como nudge acotado.
- La clase de bug que más daño hizo acá es **excepción tragada = subsistema muerto en
  silencio** (mató M15 2 semanas, SMC, el loop de aprendizaje meses). Todo lo nuevo va con
  **fail-loud**, nunca `except: pass` ni `logger.debug`.
- No calibrar sobre data sucia: por eso `setup_type` se puebla ahora y el paso 6 de
  `dynamic_conf` queda para cuando haya muestra limpia.


---

# ESTADO FINAL — v3.57.0 (19 Ago 2026)

## Qué quedó HECHO

| # | Cosa | Dónde |
|---|---|---|
| 1 | **Retrospectiva PRE-decisión** — nudge de confianza, nunca filtro. `RETRO_MODE=shadow` | `src/analyzer/pre_trade_retrospective.py` |
| 2 | **Familias de setup dirección-neutras** (el bug que hacía la pregunta inrespondible) | ídem, `SETUP_FAMILIES` |
| 3 | **Loop `directional_lessons`** — el post-trade escribe, la retrospectiva lee | `post_trade_analyzer.py`, `db.py` |
| 4 | **Cableado de `adjust_setup_confidence`** (muerto desde v3.31.0) | `db.py` en `add_auto_strategy` |
| 5 | **Registro de la decisión** por señal (features + veredicto + deltas) | tabla `pre_trade_retrospective` |
| 6 | **Perilla `ENABLE_NEWS_TRACK`** (default ON, NO se giró) | `AIdan_TodoEnUno.py` |
| 7 | **`news_latency_min`** en `entry_context`, clasificado en el momento | `AIdan_TodoEnUno.py` |
| 8 | Scorer del shadow + backfill de lecciones + medidor de latencia + verificador e2e | `tools/` |
| 9 | **Research de mercado** con lo accionable rankeado y lo descartado | `docs/research_mercado_2026-08-19.md` |
| 10 | 36 tests nuevos (suite **75 → 111**), incluidos tests de mutación y de call-site | `tests/*_v3570.py` |

Verificado end-to-end contra una copia de la DB (`tools/verify_retro_path.py`): el ajuste se
aplica, la fila se persiste, el loop de lecciones se consulta (`lesson_hits=1`) y producción
queda intacta. `AIdan.exe` rebuildeado, `/version` = 3.57.0, MT5 conectado.

## Qué NO se hizo, y por qué

| Item del brief | Por qué no |
|---|---|
| Sacar las credenciales de `config.py` | La premisa era "arregla la suite": **la suite ya está verde con las keys** (75 passed antes de tocar nada). Y hay **decisión previa del user de no tocarlas** (repo privado, key trivial de regenerar). Hacerlo sería un cambio riesgoso — si el `.env` no carga, muere el LLM — sobre un problema que no existe. **Si querés hacerlo igual, decímelo y lo hago**; es tu decisión, no un bloqueo técnico. |
| Poblar `setup_type` | Ya lo hizo v3.48.0. 61 filas pobladas y todas las nuevas. |
| Backup de DB + logs a disco | Ya existen (`tools/backup_db.py`, `%APPDATA%/AIdan/backups/`, `logs/aidan.log` rotado). Igual tomé un backup explícito antes de crear tablas. |
| Agregador de `recommended_sl_pips`/`tp_pips` de Gemma | **Esas columnas no existen** en `post_trade_analysis`. El advice de SL/TP vive en `learning_insights.sl_tp_advice` y **ya se consume** en `compute_adaptive_sl_tp` (4 call-sites). El `tighten` emite 0 **a propósito**: apretar el SL ya se midió y no reduce la pérdida en dólares (el sizing es riesgo$/(SL×10)), solo baja el WR. Cablear un promedio ponderado encima sería re-abrir algo ya refutado. |
| Platt scaling | **Se dejó afuera a propósito.** Ya se intentó el 5-ago y **no pasó su gate pre-declarado** (Brier 0,2522 vs 0,2424 de la constante). Repetirlo hoy sería el mismo experimento con +60 trades y sin `setup_type` limpio acumulado. Corresponde después de 3-4 semanas de la data nueva, con el gate declarado antes. |
| Apagar `news` | Es decisión tuya (ver arriba). La perilla está lista. |

## Cómo se mide en 2-3 semanas

**Control de daño primero (si esto falla, revertir):**
- **Frecuencia por track, antes vs después.** Debe quedar **plana**. Cualquier caída = algo se
  volvió filtro sin querer ⇒ `RETRO_MODE=off`.
- **Veredictos `error`** en `pre_trade_retrospective`. Si aparecen seguido, el subsistema está
  fallando (no "no encontrando patrón") ⇒ mirar los WARNING en `aidan.log`.

**Lo que decide si sirve** (`python tools/score_retrospective_shadow.py`):
- Gate de 4 condiciones, **declarado antes de tener números**: n≥25 `contrarian` cerrados · WR por
  debajo del comparador · CI95 de Wilson que **no cruza** · PnL/trade negativo y peor.
- **Si con n≥40 no separa ⇒ `RETRO_MODE=off`.** No buscarle la vuelta.
- Trampa a evitar al leer: que `aligned` rinda bien **no es evidencia** — arrastra el sesgo de que
  lo que venía ganando sigue ganando. Lo que tiene que demostrar es que **detecta lo malo**.

**Salud del loop de lecciones:** que `directional_lessons` crezca por el path vivo (hoy 19, todas
del backfill) y que `lesson_hits > 0` en algunas señales. **Si se consulta 0 veces, el loop está
muerto** — es el síntoma exacto de los 7 mecanismos de aprendizaje ya construidos y desconectados.

**Expectativa honesta:** hoy el nudge es **inerte sobre la ejecución** (los gates de confianza
están antes y el lote sale del SL). Estas 2-3 semanas producen **la muestra**, no la mejora de
PnL. Prometer lo contrario sería vender humo.

## Lo próximo que yo haría (del research, ver el ranking completo en `docs/`)

1. **Piso de ATR por PERCENTIL** en vez de pips fijos. Es el único candidato que **protege** la
   frecuencia en vez de recortarla, y arregla algo que ya está pasando: en el agosto muerto m15
   perdió 59 % de su frecuencia por un umbral que no se autoajusta. **No superponerlo a la lectura
   del ~1 sep** del piso fijo — rompería la atribución.
2. **TCA**: registrar costo esperado vs realizado (spread al enviar, pedido vs fill, comisión). Es
   lo único que distingue "la estrategia empeoró" de "la ejecución empeoró". **Bloqueante antes de
   cuenta real.**
3. Bajar a refutado el hilo del **pullback-entry**: ya lo refutaron Fase 2 propia **y** un estudio
   externo (80,7 % de stop-out).
