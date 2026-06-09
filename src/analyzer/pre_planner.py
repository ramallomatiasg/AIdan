"""
Pre-Planner — Groq + Gemma 4 planifican estrategias para eventos de alto impacto del dia siguiente.

Ejecuta durante horario off-market (20:00-23:00 UTC).
Fetch calendario economico del dia siguiente, filtra HIGH impact EUR/USD,
y para cada evento AMBAS IAs analizan y votan:

  Groq (Llama 70B) = palabra mayor (modelo mas grande/inteligente)
  Gemma 4 (local)  = segunda opinion

  Ambos de acuerdo operar  -> crear estrategia (conf +10 bonus)
  Groq opera, Gemma no     -> crear estrategia (Groq manda)
  Groq skip, Gemma opera   -> NO operar (Groq manda)
  Ambos skip               -> NO operar

Las estrategias se crean con status='planned' y se activan automaticamente
5 minutos antes del evento.
"""

import logging
import json
import requests
from datetime import datetime, timezone, timedelta
from src.common.config import Config

logger = logging.getLogger("analyzer")

PLANNING_TIMEOUT = 60  # v3.25.0: subido de 30s a 60s para permitir deepseek-r1 reasoning
GROQ_TIMEOUT = 15
OLLAMA_URL = Config.OLLAMA_URL or "http://localhost:11434"
# v3.25.0 — modelo dedicado para pre-planner (razonamiento estrategico)
GEMMA_MODEL = Config.get_llm_model('pre_planner')

PLANNING_PROMPT = """Eres un planificador de trading EUR/USD en timeframe M5.
Manana hay este evento economico de alto impacto:

Evento: {event_name}
Hora: {event_time} UTC
Moneda: {currency}
Impacto esperado: {impact}
Consenso/Forecast: {forecast}
Anterior: {previous}

Contexto actual del mercado:
- Tendencia H1: {h1_trend}
- RSI actual: {rsi}
- Volatilidad actual: {volatility}
- Sesion del evento: {event_session}

Historial de eventos similares (si disponible):
{historical_context}

Genera una estrategia pre-calculada. Responde SOLO en JSON valido:
{{"should_trade": true, "direction": "CALL", "confidence": 55, "reasoning": "explicacion corta", "sl_pips": 5, "tp_pips": 15, "entry_strategy": "breakout", "risk_level": "normal"}}

Reglas:
- should_trade: true si vale la pena operar, false si mejor evitar
- direction: "CALL" o "PUT" (basado en expectativa del evento)
- confidence: entre 40 y 85 (ser conservador, no es analisis en tiempo real)
- sl_pips: entre 3 y 8 (scalping M5)
- tp_pips: entre 8 y 25 (scalping M5)
- entry_strategy: "breakout" (esperar quiebre) | "fade" (operar en contra del spike) | "momentum" (seguir la direccion)
- risk_level: "conservative" | "normal" | "aggressive"
- reasoning: maximo 2 oraciones explicando la logica
"""


def _get_event_session(hour_utc):
    """Determine trading session from hour UTC."""
    if 7 <= hour_utc < 12:
        return 'london'
    elif 12 <= hour_utc < 14:
        return 'overlap'
    elif 14 <= hour_utc < 17:
        return 'ny'
    elif 17 <= hour_utc < 21:
        return 'late_ny'
    else:
        return 'off'


def _fetch_tomorrow_high_impact():
    """Fetch tomorrow's HIGH impact EUR/USD events from Forex Factory."""
    try:
        resp = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10)
        if resp.status_code != 200:
            return []

        all_events = resp.json()
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')

        high_impact = []
        for ev in all_events:
            country = ev.get('country', '')
            impact = ev.get('impact', '')
            if country not in ('USD', 'EUR'):
                continue
            if impact != 'High':
                continue

            event_date = ev.get('date', '')[:10]
            if event_date != tomorrow:
                continue

            event_time = ev.get('date', '')[11:16] if len(ev.get('date', '')) > 15 else '00:00'
            try:
                hour_utc = int(event_time.split(':')[0])
            except (ValueError, IndexError):
                hour_utc = 12

            high_impact.append({
                'date': ev.get('date', ''),
                'time': event_time,
                'hour_utc': hour_utc,
                'currency': country,
                'event': ev.get('title', ''),
                'impact': impact,
                'forecast': ev.get('forecast', ''),
                'previous': ev.get('previous', ''),
                'session': _get_event_session(hour_utc),
            })

        logger.info(f"Pre-planner: found {len(high_impact)} HIGH impact events for {tomorrow}")
        return high_impact

    except Exception as e:
        logger.error(f"Pre-planner: failed to fetch calendar: {e}")
        return []


def _get_historical_context(event_name, currency):
    """Get historical context from learning engine for similar events."""
    try:
        from src.common.db import get_trade_archive
        archive = get_trade_archive(200)
        relevant = []
        event_lower = event_name.lower()

        keywords = event_lower.split()[:3]
        for trade in archive:
            title = (trade.get('news_title', '') or '').lower()
            if any(kw in title for kw in keywords if len(kw) > 3):
                relevant.append(trade)

        if not relevant:
            return "No hay historial de eventos similares."

        wins = sum(1 for t in relevant if t.get('result') == 'win')
        total = len(relevant)
        avg_pips = sum(t.get('pips', 0) for t in relevant) / total if total > 0 else 0

        return f"{total} trades similares anteriores: {wins}/{total} wins ({wins/total*100:.0f}% WR), avg {avg_pips:+.1f}p"

    except Exception:
        return "No hay historial disponible."


def _build_prompt(event, market_context):
    """Build the planning prompt for both AIs."""
    ctx = {
        'event_name': event['event'],
        'event_time': event['time'],
        'currency': event['currency'],
        'impact': event['impact'],
        'forecast': event.get('forecast', 'N/A'),
        'previous': event.get('previous', 'N/A'),
        'h1_trend': market_context.get('trend', 'unknown'),
        'rsi': market_context.get('rsi', 50),
        'volatility': market_context.get('volatility', 'normal'),
        'event_session': event.get('session', 'unknown'),
        'historical_context': _get_historical_context(event['event'], event['currency']),
    }
    return PLANNING_PROMPT.format(**ctx)


def _parse_plan_response(result):
    """Parse and validate a plan response dict."""
    valid_strategies = ('breakout', 'fade', 'momentum')
    valid_risk = ('conservative', 'normal', 'aggressive')

    plan = {
        'should_trade': bool(result.get('should_trade', False)),
        'direction': result.get('direction', 'CALL') if result.get('direction') in ('CALL', 'PUT') else 'CALL',
        'confidence': max(40, min(85, int(result.get('confidence', 55)))),
        'reasoning': str(result.get('reasoning', ''))[:500],
        'sl_pips': max(3, min(8, float(result.get('sl_pips', 5)))),
        'tp_pips': max(8, min(25, float(result.get('tp_pips', 15)))),
        'entry_strategy': result.get('entry_strategy', 'breakout') if result.get('entry_strategy') in valid_strategies else 'breakout',
        'risk_level': result.get('risk_level', 'normal') if result.get('risk_level') in valid_risk else 'normal',
    }

    # Sanity check: reasoning vs direction contradiction
    # v3.31.4 — expandida lista por bug observado: 'movimiento a la baja' /
    # 'impacto negativo' NO se detectaban con la lista anterior, causaba que
    # CALL se ejecutara cuando LLM razono bearish.
    if plan['should_trade']:
        reasoning_lower = plan['reasoning'].lower()
        bearish_words = (
            # Originales
            'seguir cayendo', 'caer', 'bearish', 'bajista', 'bajar', 'debilitar',
            # v3.31.4: agregadas
            'a la baja', 'movimiento a la baja', 'impacto negativo', 'negativo en el eur',
            'caída', 'caida', 'descenso', 'declive', 'baja del', 'baja de',
            'corrección', 'correccion', 'venta', 'sell', 'short', 'bear ',
            'cae', 'baja en', 'presión bajista', 'presion bajista',
        )
        bullish_words = (
            # Originales
            'subir', 'alcista', 'bullish', 'rally', 'fortalecer', 'alza',
            # v3.31.4: agregadas
            'a la alza', 'al alza', 'impacto positivo', 'positivo en el eur',
            'subida', 'ascenso', 'avance', 'sube', 'sube del', 'sube de',
            'compra', 'buy', 'long', 'bull ', 'presión alcista', 'presion alcista',
            'fortalece', 'apreciación', 'apreciacion',
        )
        is_bearish_reasoning = any(w in reasoning_lower for w in bearish_words)
        is_bullish_reasoning = any(w in reasoning_lower for w in bullish_words)

        if plan['direction'] == 'CALL' and is_bearish_reasoning and not is_bullish_reasoning:
            logger.warning(f"Pre-planner: contradiction detected — CALL with bearish reasoning, flipping to PUT")
            plan['direction'] = 'PUT'
        elif plan['direction'] == 'PUT' and is_bullish_reasoning and not is_bearish_reasoning:
            logger.warning(f"Pre-planner: contradiction detected — PUT with bullish reasoning, flipping to CALL")
            plan['direction'] = 'CALL'

    return plan


def _ask_gemma(prompt):
    """Ask Gemma 4 (local) for a plan."""
    try:
        # GPU-aware: si GPU ocupada por otro proceso, retorna None (caller fallback)
        try:
            from src.common.gpu_monitor import should_pause_llm
            if should_pause_llm():
                return None
        except Exception:
            pass

        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': GEMMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'keep_alive': '5m',  # v3.25.0: deepseek-r1:7b en pre-planner
                'options': {
                    'temperature': 0.3,
                    'top_p': 0.9,
                    'num_predict': 400,
                    'num_ctx': 2048,  # context limitado para deepseek-r1
                }
            },
            timeout=PLANNING_TIMEOUT
        )
        if response.status_code != 200:
            logger.warning(f"Pre-planner Gemma HTTP error: {response.status_code}")
            return None

        result_text = response.json().get('response', '')
        # v3.25.0 — strip DeepSeek-R1 <think> tags
        if '<think>' in result_text:
            after = result_text.split('</think>')
            if len(after) > 1:
                result_text = after[-1].strip()
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[\s\S]*\}', result_text)
            if match:
                result = json.loads(match.group())
            else:
                raise
        return _parse_plan_response(result)

    except requests.exceptions.Timeout:
        logger.warning(f"Pre-planner Gemma timeout ({PLANNING_TIMEOUT}s)")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Pre-planner Gemma: Ollama not reachable")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Pre-planner Gemma: invalid JSON — {e}")
        return None
    except Exception as e:
        logger.error(f"Pre-planner Gemma error: {e}")
        return None


def _ask_groq(prompt):
    """Ask Groq (Llama 70B, cloud) for a plan."""
    try:
        keys = Config.GROQ_API_KEYS if hasattr(Config, 'GROQ_API_KEYS') else [getattr(Config, 'GROQ_API_KEY', '')]
        keys = [k for k in keys if k]
        if not keys:
            logger.warning("Pre-planner Groq: no API keys configured")
            return None

        for i, api_key in enumerate(keys):
            try:
                resp = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    json={
                        'model': Config.GROQ_MODEL or 'llama-3.3-70b-versatile',
                        'messages': [
                            {'role': 'system', 'content': 'Eres un planificador experto de trading EUR/USD. Responde SOLO en JSON valido.'},
                            {'role': 'user', 'content': prompt}
                        ],
                        'temperature': 0.3,
                        'max_tokens': 400,
                    },
                    timeout=GROQ_TIMEOUT
                )

                if resp.status_code == 200:
                    result_text = resp.json()['choices'][0]['message']['content']
                    # Extract JSON from response (may have markdown wrapping)
                    if '```' in result_text:
                        result_text = result_text.split('```')[1]
                        if result_text.startswith('json'):
                            result_text = result_text[4:]
                    result = json.loads(result_text.strip())
                    return _parse_plan_response(result)
                elif resp.status_code == 429 and i < len(keys) - 1:
                    logger.warning(f"Pre-planner Groq key {i+1} rate limited, trying next...")
                    continue
                else:
                    logger.warning(f"Pre-planner Groq HTTP {resp.status_code}: {resp.text[:200]}")
                    if i < len(keys) - 1:
                        continue
                    return None

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f"Pre-planner Groq key {i+1} failed: {e}")
                if i < len(keys) - 1:
                    continue
                return None

        return None

    except json.JSONDecodeError as e:
        logger.warning(f"Pre-planner Groq: invalid JSON — {e}")
        return None
    except Exception as e:
        logger.error(f"Pre-planner Groq error: {e}")
        return None


def _plan_single_event(event, market_context):
    """
    Both Groq (Llama 70B) and Gemma 4 analyze the event and vote.
    Groq has final say (bigger/smarter model).

    Voting:
      Both agree to trade  -> create strategy (conf +10 bonus)
      Groq trades, Gemma not -> create strategy (Groq decides)
      Groq skip, Gemma trades -> skip (Groq decides)
      Both skip -> skip
    """
    prompt = _build_prompt(event, market_context)
    event_name = event['event']

    # Ask both AIs
    logger.info(f"Pre-planner: analyzing '{event_name}' @ {event['time']} UTC with Groq + Gemma...")
    groq_plan = _ask_groq(prompt)
    gemma_plan = _ask_gemma(prompt)

    # Log individual votes
    groq_vote = groq_plan['should_trade'] if groq_plan else None
    gemma_vote = gemma_plan['should_trade'] if gemma_plan else None

    groq_label = f"{'TRADE' if groq_vote else 'SKIP'} {groq_plan['direction']} conf={groq_plan['confidence']}" if groq_plan else "UNAVAILABLE"
    gemma_label = f"{'TRADE' if gemma_vote else 'SKIP'} {gemma_plan['direction']} conf={gemma_plan['confidence']}" if gemma_plan else "UNAVAILABLE"

    logger.info(f"Pre-planner votes for '{event_name}': Groq=[{groq_label}] Gemma=[{gemma_label}]")

    # Voting logic — Groq has final say
    if groq_plan and groq_vote:
        # Groq says trade
        plan = groq_plan  # use Groq's plan as base

        if gemma_plan and gemma_vote:
            # Both agree -> confidence bonus
            bonus = 10
            plan['confidence'] = min(85, plan['confidence'] + bonus)
            # If both agree on direction, extra confidence. If not, use Groq's direction
            if gemma_plan['direction'] == groq_plan['direction']:
                logger.info(f"Pre-planner: UNANIMOUS AGREE on {plan['direction']} for '{event_name}' (conf +{bonus} bonus)")
            else:
                logger.info(f"Pre-planner: Both trade but disagree direction — Groq={groq_plan['direction']} Gemma={gemma_plan['direction']}. Using Groq's {plan['direction']}")
            # Merge reasoning
            plan['reasoning'] = f"[Groq+Gemma] {groq_plan['reasoning']} | Gemma: {gemma_plan['reasoning']}"
        else:
            # Only Groq says trade
            gemma_reason = gemma_plan['reasoning'] if gemma_plan else 'no disponible'
            logger.info(f"Pre-planner: Groq OVERRIDES Gemma skip for '{event_name}' — Gemma dijo: {gemma_reason}")
            plan['reasoning'] = f"[Groq decide] {groq_plan['reasoning']} | Gemma disiente: {gemma_reason}"

        return plan

    elif groq_plan and not groq_vote:
        # Groq says skip — final decision regardless of Gemma
        groq_reason = groq_plan.get('reasoning', '')
        if gemma_plan and gemma_vote:
            logger.info(f"Pre-planner: Groq VETOES Gemma trade for '{event_name}' — Groq: {groq_reason}")
        else:
            logger.info(f"Pre-planner: Both SKIP '{event_name}' — Groq: {groq_reason}")
        return None

    elif not groq_plan and gemma_plan:
        # Groq unavailable — Gemma decides alone
        if gemma_vote:
            logger.info(f"Pre-planner: Groq unavailable, Gemma alone says TRADE '{event_name}'")
            gemma_plan['reasoning'] = f"[Solo Gemma - Groq no disponible] {gemma_plan['reasoning']}"
            return gemma_plan
        else:
            logger.info(f"Pre-planner: Groq unavailable, Gemma says SKIP '{event_name}' — {gemma_plan['reasoning']}")
            return None

    else:
        # Both unavailable
        logger.warning(f"Pre-planner: both Groq and Gemma unavailable for '{event_name}' — skipping")
        return None


def plan_next_day_strategies(market_context=None):
    """
    Main entry: fetch tomorrow's HIGH impact events, plan strategies with Groq + Gemma 4.

    Returns:
        list of created strategy IDs
    """
    events = _fetch_tomorrow_high_impact()
    if not events:
        logger.info("Pre-planner: no HIGH impact events for tomorrow")
        return []

    market_ctx = market_context or {}
    created_ids = []
    # v3.37.2 — dedup por slot exacto (UTC YYYY-MM-DD HH:MM) en lugar de solo hora.
    # Antes: dedupeaba por hora con strptime '%Y-%m-%d %H:%M:%S', pero la DB guarda
    # ISO con timezone ('2026-05-28T08:30:00-04:00') → strptime fallaba silenciosamente
    # → planned_hours vacio → se creaban plans duplicados/contradictorios para el mismo evento.
    # Caso real 27 May: #539 CALL + #540 PUT ambos para 2026-05-28T08:30:00-04:00.
    # Fix: usar datetime.fromisoformat (entiende timezone) y dedupear por minuto exacto.
    planned_slots = set()

    try:
        import sqlite3
        from src.common.db import DB_PATH
        from datetime import datetime, timedelta, timezone as _tz
        _conn = sqlite3.connect(DB_PATH)
        _c = _conn.cursor()
        now_utc = datetime.now(_tz.utc)
        window_end = now_utc + timedelta(hours=48)
        # Buscamos pre_planned activos/planeados en proxima ventana (sin filtrar por string range
        # para evitar problemas con formatos heterogeneos en event_time).
        _c.execute("""
            SELECT event_time, status FROM auto_strategies
            WHERE trigger_type = 'pre_planned' AND event_time IS NOT NULL
              AND status IN ('planned', 'active', 'paused')
        """)
        for et, _st in _c.fetchall():
            try:
                et_dt = datetime.fromisoformat(str(et).replace('Z', '+00:00'))
                if et_dt.tzinfo is None:
                    et_dt = et_dt.replace(tzinfo=_tz.utc)
                et_utc = et_dt.astimezone(_tz.utc)
                if now_utc <= et_utc <= window_end:
                    # Slot exacto al minuto en UTC
                    planned_slots.add(et_utc.strftime('%Y-%m-%d %H:%M'))
            except Exception:
                continue
        _conn.close()
        if planned_slots:
            logger.info(f"Pre-planner: existing plans for slots UTC {sorted(planned_slots)} — will skip these")
    except Exception as _pde:
        logger.debug(f"Pre-planner dedup check: {_pde}")

    from datetime import datetime as _dt, timezone as _tz_evt
    from collections import defaultdict
    # v3.40.8 — Consolidar por SLOT (un evento = un solo movimiento de mercado). Un mismo
    # informe sale en varias lineas al MISMO horario (CPI y/y, m/m, Core y/y, Core m/m) ->
    # antes se generaba un plan por linea (4 planes, a veces contradictorios). Causa: la dedup
    # intra-run estaba ROTA -> la vieja l.523 hacia `planned_hours.add(event_hour)` (nombres de
    # un refactor viejo, ya inexistentes) -> NameError silencioso tragado por el try -> el set
    # `planned_slots` nunca se actualizaba dentro de la corrida. Fix: juntar los planes por slot
    # y crear UNO solo (el de mayor confianza = la senal mas fuerte del informe).
    slot_plans = defaultdict(list)  # slot UTC 'YYYY-MM-DD HH:MM' -> [(event, plan)]
    for event in events:
        _slot = None
        try:
            _evt_full = str(event.get('date', '')).replace('Z', '+00:00')
            if _evt_full:
                _slot_dt = _dt.fromisoformat(_evt_full)
                if _slot_dt.tzinfo is None:
                    _slot_dt = _slot_dt.replace(tzinfo=_tz_evt.utc)
                _slot = _slot_dt.astimezone(_tz_evt.utc).strftime('%Y-%m-%d %H:%M')
        except Exception:
            _slot = None
        # Dedup cross-run: ya hay un plan en la DB para este slot (corridas anteriores)
        if _slot and _slot in planned_slots:
            logger.info(f"Pre-planner: skipping '{event.get('event','?')}' — ya hay plan para slot {_slot} UTC")
            continue
        plan = _plan_single_event(event, market_ctx)
        if not plan:
            continue
        slot_plans[_slot or event.get('event', '?')].append((event, plan))

    # Un plan por slot: el de mayor confianza. Las lineas del mismo informe mueven el mercado
    # una sola vez; quedarse con la senal mas fuerte evita los planes contradictorios.
    for _slot, _items in slot_plans.items():
        if len(_items) > 1:
            _dir_counts = {}
            for _e, _p in _items:
                _dir_counts[_p['direction']] = _dir_counts.get(_p['direction'], 0) + 1
            _items = sorted(_items, key=lambda ep: ep[1].get('confidence', 0) or 0, reverse=True)
            logger.info(f"Pre-planner: slot {_slot} tenia {len(_items)} lineas {_dir_counts} -> consolido en 1 (mayor conf: {_items[0][1]['direction']} {_items[0][1].get('confidence')})")
        event, plan = _items[0]
        try:
            from src.common.db import add_planned_strategy
            strategy_id = add_planned_strategy(
                news_title=f"[PRE-PLAN] {event['event']}",
                direction=plan['direction'],
                confidence=plan['confidence'],
                sl_pips=plan['sl_pips'],
                tp_pips=plan['tp_pips'],
                trigger_type='pre_planned',
                event_time=event['date'],
                planning_reasoning=plan['reasoning'],
                entry_strategy=plan.get('entry_strategy', 'breakout'),
                risk_level=plan.get('risk_level', 'normal'),
            )
            if strategy_id:
                created_ids.append(strategy_id)
                if _slot:
                    planned_slots.add(_slot)
                logger.info(f"Pre-planner: created planned strategy #{strategy_id} for '{event['event']}' @ {event['time']}")
        except Exception as e:
            logger.error(f"Pre-planner: failed to create strategy for '{event['event']}': {e}")

    logger.info(f"Pre-planner: created {len(created_ids)} planned strategies for tomorrow")
    return created_ids
