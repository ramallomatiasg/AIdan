# PROGRESS.md — sesión autónoma del 19 Ago 2026

**Estado: Ola 1 + core de Ola 2 CERRADOS.** `AIdan.exe` rebuildeado y corriendo en **v3.57.2**,
MT5 conectado. Suite **136 tests en verde** (arrancó en 75). 7 commits locales, **sin push**.

---

## 1. Lo primero que hay que saber: el brief estaba parcialmente viejo

El `AUDIT_REPORT.md` es del **31 Jul (v3.47.1)** y **v3.48.0 ya había implementado la Ola 1**.
Medí todo contra el código vivo antes de escribir una línea:

| Item del brief | Estado real medido | Qué hice |
|---|---|---|
| `setup_type` NULL en 546/546 | **Ya arreglado** — 61 filas pobladas, todas las nuevas | nada |
| Suite rota (5F/24E) | **Ya verde: 75 passed** | nada |
| Sacar creds de `config.py` | Premisa falsa (la suite pasa **con** las keys) + decisión previa tuya de no tocarlas | **no lo hice** — ver §5 |
| Backup de DB / logs a disco | **Ya existen** y funcionan | usé el backup, no lo reescribí |
| Gemma escribe `recommended_sl_pips` en `post_trade_analysis` | **Esas columnas no existen**; el advice vive en `sl_tp_advice` y **ya se consume** en 4 call-sites | replanteado — ver §5 |
| `adjust_setup_confidence` nunca invocado | **Confirmado** — era el único item real de Ola 1 | hecho |

---

## 2. Qué hice

### v3.57.0 — core del pedido
- **`src/analyzer/pre_trade_retrospective.py`**: antes de crear el trade compara la señal contra
  los trades similares y, si la dirección opuesta era la que pagaba, emite `contrarian` + delta
  negativo de confianza. **Nunca bloquea, nunca invierte.**
- **`directional_lessons`**: el post-trade escribe "hubiera sido mejor la opuesta", la
  retrospectiva lo lee en la próxima señal del mismo setup.
- **Cableado de `adjust_setup_confidence`** (muerto desde v3.31.0).
- **Perilla `ENABLE_NEWS_TRACK`** (default **ON**, no la giré).
- **`news_latency_min`** en `entry_context`, clasificado en el momento.

### v3.57.1 — la lección deja de depender de Ollama
La derivación vivía **solo** dentro de `analyze_closed_trade`, que devuelve `None` ante cualquier
problema del LLM (timeout, HTTP≠200, GPU ocupada, JSON inválido). Un lazo **100 % determinista**
quedaba de rehén de un 7B: con Ollama caído `directional_lessons` deja de crecer y la retrospectiva
se queda ciega **sin que nada falle**. Es la clase de bug que ya mató a M15 dos semanas, a SMC y al
reversal. Ahora se deriva **también** en `archive_trade`.

### v3.57.2 — el lazo pasa a ser bidireccional
Faltaba la mitad del pedido: el post-trade nunca veía lo que la entrada había mirado, así que no
podía decir *"el PUT era correcto pero por Y razón que no considerabas"*. Ahora el prompt recibe la
comparación histórica y devuelve **`missed_factor`** (lista cerrada, **columna propia**).

### Extra pedido en el turno anterior
- **Research de mercado**: `docs/research_mercado_2026-08-19.md`.
- **`tools/measure_news_latency.py`**: midió que el cuello de botella de news es el **feed**
  (mediana 8,9 min), **no el LLM** (0,2 min).

---

## 3. Decisiones que tomé solo, y por qué

| Bifurcación | Decisión | Razón |
|---|---|---|
| ¿El nudge arranca ON u OFF? | **`RETRO_MODE=shadow`** (calcula, registra, delta 0) | No hay **una** medición de que el veredicto discrimine. Activarlo sería creer la hipótesis antes de medirla. |
| Ventana de trades similares | **N=40**, mínimo 6, máximo por lado 3, tope del delta **±8** | 40 ≈ 8 días de historia a 5 trades/día: suficiente para el bucket y corto para no arrastrar régimen viejo. El delta escala con la muestra: n=6 casi no mueve. |
| ¿Comparar por `setup_type` exacto? | **No: por FAMILIA dirección-neutra** | `setup_type` **codifica la dirección** (`trend_continuation_bull` es siempre CALL) ⇒ el lado opuesto tenía n=0 **siempre** y la pregunta era inrespondible. Lo descubrí ejecutándolo, no leyéndolo. |
| ¿Quién decide "hubiera sido mejor la opuesta"? | **Código, no el LLM** | El A/B de v3.53.7 mostró que el 7B pone `entry_quality='good'` en el **93 % de los perdedores**. Criterio: perdió **y** nunca se puso a favor (<20 % del TP) **y** pegó el SL — las tres juntas. |
| ¿Segundo hook en `update_mt5_close`? | **No** | El ~8 % que se archiva sin `mt5_pnl` no genera lección, pero engancharse ahí es escribir en el path del P&L, que el proyecto trata como verdad ("no shipear junto con nada"). El backfill idempotente es la red. |
| ¿Al post-trade se le pasa el veredicto? | **No: solo los números** | Si leyera "la opuesta pagaba" lo repetiría como loro. Hay un test que falla si alguien mete el veredicto en el bloque. |
| Valor inválido de `missed_factor` | Cae a **`''`, no a `'ninguno'`** | Hay que distinguir "el modelo dijo que no faltaba nada" de "contestó cualquier cosa"; si colapsan, la adherencia es inauditable. |
| ¿`missed_factor` en JSON o columna? | **Columna** (migración guardada) | Un campo que hay que sacar con `json_extract` no se agrega en la práctica — es el destino de los 10.736 insights del LearningEngine. |
| ¿Giro el toggle de news? | **No** | Tu decisión del 7-ago ("news no se apaga, se arregla") + veredicto pre-declarado ~28 ago. Apagarlo ahora contamina esa lectura. Entrego la perilla. |

---

## 4. Cómo verificar que está vivo (2 comandos)

```bash
python tools/score_retrospective_shadow.py
```

Imprime los veredictos, la comparación que decide, el **gate pre-declarado de 4 condiciones**, la
salud del loop de lecciones y la **adherencia de `missed_factor`**.

```bash
python tools/verify_retro_path.py
```

Prueba end-to-end el camino completo contra una **copia** de la DB (producción intacta, con assert).

**Hoy `pre_trade_retrospective` tiene 0 filas y es correcto**: la última señal (#913) es previa al
rebuild. Escribe una fila por señal creada, así que debería empezar a poblarse solo.

---

## 5. Qué NO hice, y por qué (para que no lo busques)

- **Sacar las credenciales de `config.py`.** La razón del brief era "arreglar la suite", y la suite
  ya estaba verde **con** las keys. Además tenés decisión previa de no tocarlas. Moverlas es
  riesgoso (si el `.env` no carga, muere el LLM) por un problema que no existe. **No es un bloqueo
  técnico: si lo querés igual, es media hora.**
- **El agregador de `recommended_sl_pips`/`tp_pips`.** Esas columnas no existen, y el `tighten`
  emite 0 **a propósito**: apretar el SL ya se midió y no reduce la pérdida en dólares (el sizing es
  riesgo$/(SL×10)), solo baja el WR. Cablear un promedio ponderado encima sería reabrir algo
  refutado.
- **Platt scaling (Ola 3).** Ya se intentó el 5-ago y **no pasó su gate** (Brier 0,2522 vs 0,2424).
  Repetirlo hoy es el mismo experimento con +60 trades y sin `setup_type` limpio acumulado.
  Corresponde en 3-4 semanas, declarando el gate antes.
- **`adjust_min_confidence_per_track`** sigue sin cablear **a propósito**: ese change_type mueve un
  piso de confianza, o sea que **es un filtro** y reduciría frecuencia. Choca con la restricción #1.

**BLOQUEOS: ninguno.** No hubo nada que me impidiera avanzar.

---

## 6. Expectativa honesta para las próximas 2-3 semanas

**Esto no te va a mover el PnL todavía, y decirte lo contrario sería venderte humo.** Los gates de
`min_confidence` viven **dentro** de los detectores y el lote sale de `sl_pips`, no de la confianza
⇒ el nudge es frecuencia- y tamaño-neutro, pero **hoy inerte sobre la ejecución**. Lo que producen
estas semanas es **la muestra** con la que se decide si el veredicto sirve.

**Control de daño (si esto falla, revertí):**
- Frecuencia por track debe quedar **plana**. Si baja, algo se volvió filtro → `RETRO_MODE=off`
  (env, sin rebuild).
- Veredictos `error` en la tabla: si aparecen seguido, el subsistema falla (no "no encuentra
  patrón") → mirar WARNING en `aidan.log`.

**Lo que decide (criterio escrito antes de ver números):** n≥25 `contrarian` cerrados · WR por
debajo del comparador · CI95 de Wilson que **no cruza** · PnL/trade negativo y peor. **Si con n≥40
no separa → `RETRO_MODE=off`.** Trampa a evitar: que `aligned` rinda bien **no es evidencia** —
arrastra el sesgo de que lo que venía ganando sigue ganando.

**Salud del loop:** que `directional_lessons` crezca por el path vivo (hoy 19, todas del backfill) y
que `lesson_hits > 0` en algunas señales. **0 consultas = loop muerto.**

---

## 7. Lo próximo que yo haría (ranking completo en `docs/research_mercado_2026-08-19.md`)

1. **Piso de ATR por PERCENTIL** en vez de pips fijos. Único candidato que **protege** la frecuencia
   en vez de recortarla, y arregla algo que ya está pasando: en el agosto muerto m15 perdió **59 %**
   de su frecuencia por un umbral que no se autoajusta. **No superponerlo a la lectura del ~1 sep.**
2. **TCA**: costo esperado vs realizado (spread al enviar, pedido vs fill). Es lo único que
   distingue "la estrategia empeoró" de "la ejecución empeoró". **Bloqueante antes de cuenta real.**
3. Bajar a **refutado** el hilo del pullback-entry: lo refutaron tu Fase 2 **y** un estudio externo.

---

## 8. Commits de la sesión (locales, sin push)

```
6dc2299  v3.57.2: el post-trade ve el razonamiento de la entrada
961e4af  v3.57.1: la leccion direccional deja de depender de que Ollama este arriba
e19b392  WIP_DECISIONS: estado final + verificador end-to-end
89aa8f1  research de mercado + news_latency_min
b39a9bb  v3.57.0: perilla ENABLE_NEWS_TRACK (default ON)
ec5e859  v3.57.0: retrospectiva PRE-decision en shadow + cableado
```

Backups de la DB tomados antes de cada cambio de schema/datos:
`pre_v3570_retro_*.db` y `pre_v3571_lessons_*.db` en `%APPDATA%\AIdan\backups\`.
