import json
import os


class NewsAnalyzer:
    def __init__(self, logger):
        self.logger = logger
        self.ai_mode = self._detect_ai_mode()
        self.logger.info(f"Analyzer initialized in {self.ai_mode.upper()} mode")

        # Technical analyzer for cross-referencing
        try:
            from src.analyzer.technical import TechnicalAnalyzer
            self.technical = TechnicalAnalyzer(logger)
        except Exception as e:
            self.logger.warning(f"Technical analyzer not available: {e}")
            self.technical = None

        # === KEYWORD CLASSIFICATION RULES ===
        # Tier 1: Direct macro data that moves EUR/USD (score 80-95)
        self.tier1_keywords = {
            'nfp': 92, 'non-farm': 92, 'payrolls': 90,
            'cpi data': 90, 'inflation data': 88, 'core cpi': 90,
            'rate decision': 95, 'rate hike': 92, 'rate cut': 92,
            'fed decision': 95, 'ecb decision': 95, 'fomc': 88,
            'gdp growth': 85, 'gdp data': 85, 'pce price': 88,
            'unemployment rate': 85, 'jobless claims': 80,
        }

        # Tier 2: Fed/ECB statements, PMI (score 55-79)
        self.tier2_keywords = {
            'fed chair': 75, 'powell': 72, 'lagarde': 72,
            'ecb president': 72, 'fed governor': 65, 'ecb member': 65,
            'pmi': 68, 'manufacturing pmi': 70, 'services pmi': 68,
            'consumer confidence': 62, 'retail sales': 65,
            'trade balance': 60, 'current account': 58,
            'treasury yield': 65, 'bond yield': 62,
            'minutes': 68, 'monetary policy': 70,
            'inflation': 65, 'disinflation': 65, 'deflation': 65,
            'dollar index': 60, 'dxy': 60,
        }

        # Tier 3: Geopolitical with indirect forex impact (score 35-54)
        self.tier3_keywords = {
            'oil price': 50, 'crude oil': 50, 'brent': 48,
            'middle east': 45, 'war': 45, 'conflict': 42,
            'sanctions': 48, 'tariff': 50, 'trade war': 52,
            'china trade': 48, 'trump': 42, 'biden': 40,
            'geopolit': 42, 'embargo': 45, 'supply chain': 40,
        }

        # Corporate/irrelevant keywords (score 5-30)
        self.corporate_keywords = [
            'ipo', 'merger', 'acquisition', 'earnings', 'profit',
            'revenue', 'stock', 'shares', 'ceo', 'board',
            'startup', 'venture', 'funding', 'valuation',
            'buyback', 'dividend', 'quarterly', 'annual report',
            'listing', 'delisting', 'bourse',
        ]

        # Direction hints
        self.usd_bullish = [
            'strong dollar', 'dollar surge', 'dollar rally',
            'rate hike', 'hawkish fed', 'hot inflation', 'cpi above',
            'nfp beat', 'payrolls beat', 'unemployment fell',
            'treasury yield rise', 'bond sell',
        ]
        self.usd_bearish = [
            'weak dollar', 'dollar fall', 'dollar drop',
            'rate cut', 'dovish fed', 'cool inflation', 'cpi below',
            'nfp miss', 'payrolls miss', 'unemployment rose',
            'treasury yield fall', 'easing',
        ]
        self.eur_bullish = [
            'ecb hawkish', 'euro surge', 'euro rally',
            'eurozone growth', 'strong euro', 'ecb rate hike',
        ]
        self.eur_bearish = [
            'ecb dovish', 'euro fall', 'euro drop',
            'eurozone recession', 'weak euro', 'ecb rate cut',
        ]

    def _detect_ai_mode(self):
        """Detecta qué modo de IA usar: deepseek > ollama > claude > keywords"""
        if os.getenv('GROQ_API_KEY'):
            return 'groq'
        elif self._check_ollama():
            return 'ollama'
        elif os.getenv('ANTHROPIC_API_KEY'):
            return 'claude'
        else:
            return 'keywords'

    def _check_ollama(self):
        """Verifica si Ollama está disponible"""
        try:
            import requests
            response = requests.get('http://localhost:11434/api/tags', timeout=3)
            if response.status_code == 200:
                models = response.json().get('models', [])
                has_llama = any('llama' in m.get('name', '').lower() for m in models)
                if has_llama:
                    return True
                else:
                    self.logger.warning("Ollama corriendo pero sin modelo Llama")
                    return False
            return False
        except Exception:
            return False

    def analyze(self, news_id, title, summary, entities, tags):
        """Analyze news: keyword pre-score → Ollama for direction → technical validation."""
        try:
            text = f"{title} {summary or ''}".lower()

            # STEP 1: Keyword pre-classification (deterministic score)
            pre_score, category = self._classify_by_keywords(text)
            self.logger.info(f"Pre-classify #{news_id}: score={pre_score} cat={category}")

            # STEP 2: If corporate/irrelevant, skip Ollama entirely
            if category == 'corporate' or pre_score < 30:
                self.logger.info(f"⏭️ #{news_id}: Corporativa/irrelevante (score={pre_score}). Skip.")
                return {
                    'news_id': news_id,
                    'impact_score': pre_score,
                    'level': 'BAJA',
                    'explanation': self._auto_explain(title, category),
                    'eur_usd_impact': 'Sin impacto en EUR/USD',
                    'market_implications': 'NO OPERAR — noticia sin relevancia forex',
                    'analysis_method': 'keywords',
                    'should_operate': False,
                    'direction': 'NEUTRAL',
                    'confidence': pre_score * 0.3,
                    'should_alert': True,
                }

            # STEP 3: Keyword-based direction hint
            kw_direction = self._detect_direction_keywords(text)

            # STEP 4: Use AI for direction + short explanation
            ai_result = None
            if self.ai_mode == 'groq':
                ai_result = self._ask_groq_direction(news_id, title, summary, category, pre_score)
            elif self.ai_mode == 'ollama':
                ai_result = self._ask_ollama_direction(news_id, title, summary, category, pre_score)

            # Merge: use AI direction if available, else keyword direction
            if ai_result:
                direction = ai_result.get('direction', kw_direction)
                explanation = ai_result.get('explanation', '')
                eur_usd_impact = ai_result.get('eur_usd_impact', '')
                # Use AI confidence only as a modifier, not absolute
                ai_conf_raw = ai_result.get('confidence', 50)
                # Blend: 60% keyword-based + 40% AI
                confidence = pre_score * 0.6 + ai_conf_raw * 0.4
            else:
                direction = kw_direction
                explanation = self._auto_explain(title, category)
                eur_usd_impact = self._auto_impact(title, direction, pre_score)
                confidence = pre_score * 0.7

            # STEP 5: Technical validation
            tech_validation = None
            if self.technical and pre_score >= 50:
                try:
                    market_state = self.technical.get_market_state()
                    tech_validation = self.technical.validate_signal(direction, confidence, market_state)
                    if tech_validation:
                        old_dir = direction
                        old_conf = confidence
                        direction = tech_validation['adjusted_direction']
                        confidence = tech_validation['adjusted_confidence']
                        tech_reason = tech_validation['reason']
                        if old_dir != direction or abs(old_conf - confidence) > 10:
                            self.logger.info(f"📊 Técnico ajustó #{news_id}: {old_dir}→{direction} conf {old_conf:.0f}→{confidence:.0f} | {tech_reason}")
                        if tech_reason:
                            eur_usd_impact = f"{eur_usd_impact} | Técnico: {tech_reason}"
                except Exception as e:
                    self.logger.warning(f"Technical validation failed: {e}")

            # STEP 6: Final decisions
            if direction == 'NEUTRAL':
                confidence = min(confidence, 50)

            should_operate = (
                pre_score >= 75 and
                confidence >= 60 and
                direction in ('CALL', 'PUT') and
                category in ('tier1', 'tier2')
            )

            level = 'ALTA' if pre_score >= 75 else ('MEDIA' if pre_score >= 50 else 'BAJA')
            should_alert = True  # Show ALL analyzed news as alerts

            # Build market implications
            if should_operate:
                market_impl = f"OPERAR {direction} — {explanation[:60]}"
                if tech_validation and tech_validation.get('technical_agrees'):
                    market_impl += " | Técnico confirma"
            else:
                reasons = []
                if pre_score < 75:
                    reasons.append(f"score bajo ({pre_score})")
                if confidence < 60:
                    reasons.append(f"confianza baja ({confidence:.0f}%)")
                if direction == 'NEUTRAL':
                    reasons.append("sin dirección clara")
                if category == 'corporate':
                    reasons.append("noticia corporativa")
                if tech_validation and tech_validation.get('technical_agrees') is False:
                    reasons.append("técnico contradice")
                market_impl = f"NO OPERAR — {', '.join(reasons) if reasons else 'sin setup'}"

            self.logger.info(
                f"{'✅' if should_operate else '⏭️'} #{news_id}: Score={pre_score} Conf={confidence:.1f}% "
                f"Dir={direction} Cat={category} Operar={should_operate}"
            )

            return {
                'news_id': news_id,
                'impact_score': pre_score,
                'level': level,
                'explanation': explanation[:120],
                'eur_usd_impact': eur_usd_impact[:150],
                'market_implications': market_impl[:150],
                'analysis_method': 'ollama' if ai_result else 'keywords',
                'should_operate': should_operate,
                'direction': direction,
                'confidence': round(confidence, 2),
                'should_alert': should_alert,
            }

        except Exception as e:
            self.logger.error(f"Error analyzing news {news_id}: {e}")
            return None

    def _classify_by_keywords(self, text):
        """Deterministic classification by keyword matching. Returns (score, category)."""
        # Check corporate first (exclusion)
        corp_hits = sum(1 for kw in self.corporate_keywords if kw in text)
        if corp_hits >= 2:
            return (10 + corp_hits * 3, 'corporate')

        # Check tier 1
        best_t1 = 0
        for kw, score in self.tier1_keywords.items():
            if kw in text:
                best_t1 = max(best_t1, score)
        if best_t1 > 0:
            return (best_t1, 'tier1')

        # Check tier 2
        best_t2 = 0
        for kw, score in self.tier2_keywords.items():
            if kw in text:
                best_t2 = max(best_t2, score)
        if best_t2 > 0:
            return (best_t2, 'tier2')

        # Check tier 3
        best_t3 = 0
        for kw, score in self.tier3_keywords.items():
            if kw in text:
                best_t3 = max(best_t3, score)
        if best_t3 > 0:
            return (best_t3, 'tier3')

        # Single corporate hit
        if corp_hits == 1:
            return (20, 'corporate')

        # Unknown — low score
        return (25, 'unknown')

    def _detect_direction_keywords(self, text):
        """Keyword-based direction detection."""
        bull_score = sum(1 for kw in self.usd_bearish if kw in text)  # USD weak = EUR/USD up = CALL
        bull_score += sum(1 for kw in self.eur_bullish if kw in text)
        bear_score = sum(1 for kw in self.usd_bullish if kw in text)  # USD strong = EUR/USD down = PUT
        bear_score += sum(1 for kw in self.eur_bearish if kw in text)

        if bull_score > bear_score:
            return 'CALL'
        elif bear_score > bull_score:
            return 'PUT'
        return 'NEUTRAL'

    def _ask_groq_direction(self, news_id, title, summary, category, pre_score):
        """Ask Groq API (Llama 70B) for direction + explanation. Much better than local 8B."""
        try:
            import requests
            api_key = os.getenv('GROQ_API_KEY', '')
            if not api_key:
                return None

            prompt = f"""Analista forex EUR/USD. Lee esta noticia y respondé SOLO con JSON.

NOTICIA: {title}
{(summary or '')[:400]}

Categoría detectada: {category} (score pre-calculado: {pre_score}/100)

Respondé JSON puro:
{{"direction": "CALL o PUT o NEUTRAL", "confidence": <número 0-100>, "explanation": "<máximo 15 palabras>", "eur_usd_impact": "<máximo 10 palabras>"}}

Reglas:
- CALL = EUR/USD sube (USD débil o EUR fuerte)
- PUT = EUR/USD baja (USD fuerte o EUR débil)
- NEUTRAL = no se puede determinar
- Si es noticia corporativa/IPO/acciones: SIEMPRE NEUTRAL, confidence < 30
- Si es geopolítica sin dato económico: confidence < 50
- explanation y eur_usd_impact deben ser CORTOS y DIRECTOS"""

            self.logger.info(f"Asking Groq direction for #{news_id}...")

            resp = requests.post('https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'),
                    'messages': [{"role": "user", "content": prompt}],
                    'temperature': 0.2,
                    'max_tokens': 200,
                    'stream': False
                },
                timeout=30
            )

            if resp.status_code != 200:
                self.logger.warning(f"Groq error {resp.status_code}")
                return None

            result_text = resp.json()['choices'][0]['message']['content']
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(result_text[json_start:json_end])
                direction = result.get('direction', 'NEUTRAL')
                if '/' in direction:
                    direction = 'NEUTRAL'
                if direction not in ('CALL', 'PUT', 'NEUTRAL'):
                    direction = 'NEUTRAL'
                return {
                    'direction': direction,
                    'confidence': min(float(result.get('confidence', 50)), 95),
                    'explanation': (result.get('explanation', '') or '')[:120],
                    'eur_usd_impact': (result.get('eur_usd_impact', '') or '')[:100],
                }
            return None

        except Exception as e:
            self.logger.warning(f"Groq direction failed: {e}")
            return None

    def _ask_ollama_direction(self, news_id, title, summary, category, pre_score):
        """Ask Ollama ONLY for direction + short explanation. Simple task for small model."""
        try:
            import requests

            prompt = f"""Analista forex EUR/USD. Lee esta noticia y respondé SOLO con JSON.

NOTICIA: {title}
{(summary or '')[:400]}

Categoría detectada: {category} (score pre-calculado: {pre_score}/100)

Respondé JSON puro:
{{"direction": "CALL o PUT o NEUTRAL", "confidence": <número 0-100>, "explanation": "<máximo 15 palabras>", "eur_usd_impact": "<máximo 10 palabras>"}}

Reglas:
- CALL = EUR/USD sube (USD débil o EUR fuerte)
- PUT = EUR/USD baja (USD fuerte o EUR débil)
- NEUTRAL = no se puede determinar
- Si es noticia corporativa/IPO/acciones: SIEMPRE NEUTRAL, confidence < 30
- Si es geopolítica sin dato económico: confidence < 50
- explanation y eur_usd_impact deben ser CORTOS y DIRECTOS"""

            self.logger.info(f"Asking Ollama direction for #{news_id}...")

            response = requests.post('http://localhost:11434/api/generate',
                json={
                    'model': 'llama3.1:8b',
                    'prompt': prompt,
                    'stream': False,
                    'format': 'json',
                    'options': {
                        'temperature': 0.2,
                        'num_predict': 200,
                        'repeat_penalty': 1.3
                    }
                },
                timeout=45
            )

            if response.status_code != 200:
                return None

            result_text = response.json().get('response', '')
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(result_text[json_start:json_end])
                direction = result.get('direction', 'NEUTRAL')
                # Sanitize direction
                if '/' in direction:
                    direction = 'NEUTRAL'
                if direction not in ('CALL', 'PUT', 'NEUTRAL'):
                    direction = 'NEUTRAL'
                return {
                    'direction': direction,
                    'confidence': min(float(result.get('confidence', 50)), 95),
                    'explanation': (result.get('explanation', '') or '')[:120],
                    'eur_usd_impact': (result.get('eur_usd_impact', '') or '')[:100],
                }
            return None

        except Exception as e:
            self.logger.warning(f"Ollama direction failed: {e}")
            return None

    def _auto_explain(self, title, category):
        """Generate auto explanation when AI is not used."""
        cat_map = {
            'tier1': 'Dato macro directo — relevante para EUR/USD',
            'tier2': 'Declaración/indicador secundario — impacto moderado',
            'tier3': 'Geopolítica — impacto indirecto en forex',
            'corporate': 'Noticia corporativa — sin impacto forex',
            'unknown': 'Relevancia forex no determinada',
        }
        return cat_map.get(category, 'Sin clasificar')

    def _auto_impact(self, title, direction, score):
        """Generate auto impact text."""
        if direction == 'CALL':
            return f"EUR/USD podría subir (score {score})"
        elif direction == 'PUT':
            return f"EUR/USD podría bajar (score {score})"
        return f"Sin dirección clara (score {score})"

    def _analyze_with_claude(self, news_id, title, summary, entities, tags):
        """Analiza con Claude AI (requiere ANTHROPIC_API_KEY)"""
        self.logger.warning("Claude analysis not implemented yet")
        return None
