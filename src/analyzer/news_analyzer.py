import re
import json
import os
from datetime import datetime

class NewsAnalyzer:
    def __init__(self, logger):
        self.logger = logger
        self.ai_mode = self._detect_ai_mode()
        self.logger.info(f"Analyzer initialized in {self.ai_mode.upper()} mode")
        
        # Impact keywords
        self.high_impact_keywords = [
            'fed', 'interest rate', 'recession', 'crash', 'plunge',
            'emergency', 'historic', 'surge', 'bankruptcy', 'collapse',
            'breakthrough', 'merger', 'acquisition', 'earnings beat',
            'central bank', 'policy', 'inflation', 'inflation data', 'ecb'
        ]
        
        self.medium_impact_keywords = [
            'market', 'stock', 'trading', 'investor', 'analyst',
            'report', 'guidance', 'outlook', 'analyst rating'
        ]
        
        # EUR/USD specific keywords
        self.eur_usd_keywords = {
            'easing': 'EUR se fortalece (Fed baja tasas)',
            'tightening': 'EUR se debilita (Fed sube tasas)',
            'inflation': 'Impacto en paridad EUR/USD',
            'interest rate': 'Determinante clave para EUR/USD',
            'ecb': 'Impacto directo en EUR',
            'fed': 'Impacto directo en USD',
            'strong dollar': 'EUR/USD tiende a bajar',
            'weak dollar': 'EUR/USD tiende a subir',
            'eur/usd': 'Directamente sobre el par'
        }
    
    def _detect_ai_mode(self):
        """Detecta qué modo de IA usar: groq > ollama > keywords"""
        # Prioridad: Groq (nube, Llama 70B gratis) > Ollama (local) > Keywords (fallback)
        from src.common.config import Config

        if self._check_groq():
            return 'groq'
        elif self._check_ollama():
            return 'ollama'
        else:
            return 'keywords'

    def _check_groq(self):
        """Verifica si Groq API está disponible"""
        try:
            from src.common.config import Config
            api_key = Config.GROQ_API_KEY
            if not api_key:
                return False
            import requests
            resp = requests.get(
                'https://api.groq.com/openai/v1/models',
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=5
            )
            if resp.status_code == 200:
                self.logger.info("Groq API available (Llama 70B)")
                return True
            self.logger.warning(f"Groq API returned {resp.status_code}")
            return False
        except Exception as e:
            self.logger.warning(f"Groq check failed: {e}")
            return False
    
    def _check_ollama(self):
        """Verifica si Ollama está disponible"""
        try:
            import requests
            response = requests.get('http://localhost:11434/api/tags', timeout=3)
            if response.status_code == 200:
                models = response.json().get('models', [])
                # Verifica si hay algún modelo Llama disponible
                has_llama = any('llama' in m.get('name', '').lower() for m in models)
                if has_llama:
                    return True
                else:
                    self.logger.warning("Ollama está corriendo pero no tiene modelo Llama instalado")
                    self.logger.warning("Ejecutar: ollama pull llama3.1:8b")
                    return False
            return False
        except requests.exceptions.Timeout:
            self.logger.warning("Ollama timeout - no está respondiendo")
            return False
        except requests.exceptions.ConnectionError:
            self.logger.warning("Ollama no está corriendo en localhost:11434")
            return False
        except Exception as e:
            self.logger.error(f"Error verificando Ollama: {str(e)}")
            return False
    
    def analyze(self, news_id, title, summary, entities, tags):
        """Analyze news and calculate impact score with EUR/USD analysis - REQUIRES AI"""
        try:
            # SOLO USAR IA - NO KEYWORDS
            if self.ai_mode not in ['ollama', 'claude']:
                self.logger.error(f"AI NOT AVAILABLE - Ollama debe estar corriendo. No se analizará la noticia.")
                return None
            
            result = self._analyze_with_ai(news_id, title, summary, entities, tags)
            if result:
                return result
            
            # Si falla la IA, NO analizar
            self.logger.error(f"AI analysis failed for news {news_id} - Noticia NO procesada")
            return None
            
            # CÓDIGO KEYWORDS DESHABILITADO - SOLO IA
            # score = self._calculate_impact_score(title, summary, entities, tags)
            
            # Determine severity level
            if score >= 80:
                level = "ALTA"
            elif score >= 50:
                level = "MEDIA"
            else:
                level = "BAJA"
            
            # Generate explanations
            explanation = self._generate_explanation(title, summary, entities)
            eur_usd_impact = self._analyze_eur_usd_impact(title, summary)
            market_implications = self._generate_market_implications(title, summary, entities, tags)
            
            return {
                'news_id': news_id,
                'impact_score': score,
                'level': level,
                'explanation': explanation,
                'eur_usd_impact': eur_usd_impact,
                'market_implications': market_implications,
                'analysis_method': 'keywords',
                'should_alert': score >= 80  # Only ALTA alerts
            }
        except Exception as e:
            self.logger.error(f"Error analyzing news {news_id}: {str(e)}")
            return None
    
    def _calculate_impact_score(self, title, summary, entities, tags):
        """Calculate impact score based on multiple factors"""
        score = 50  # Base score
        
        full_text = f"{title} {summary}".lower()
        
        # Check high-impact keywords
        high_count = sum(1 for kw in self.high_impact_keywords if kw in full_text)
        score += min(30, high_count * 5)
        
        # Check medium-impact keywords
        med_count = sum(1 for kw in self.medium_impact_keywords if kw in full_text)
        score += min(20, med_count * 3)
        
        # Check entities
        if entities and len(entities) > 0:
            score += min(15, len(entities) * 5)
        
        # Check tags
        critical_tags = {'geopolitics', 'merger', 'earnings', 'market_volatility', 'monetary_policy'}
        if tags:
            tag_list = eval(tags) if isinstance(tags, str) else tags
            for tag in tag_list:
                if tag in critical_tags:
                    score += 10
        
        # Breaking news indicator
        if any(word in full_text for word in ['breaking', 'alert', 'emergency', 'urgent']):
            score += 20
        
        return min(100, score)
    
    def _generate_explanation(self, title, summary, entities):
        """Generate detailed explanation of the news"""
        explanation = f"📰 {title}\n\n"
        explanation += f"{summary[:200]}...\n\n"
        
        if entities:
            try:
                entity_list = eval(entities) if isinstance(entities, str) else entities
                explanation += f"🎯 Entidades: {', '.join(entity_list)}"
            except:
                pass
        
        return explanation
    
    def _analyze_eur_usd_impact(self, title, summary, max_length=400):
        """Analyze specific EUR/USD impact with clear direction and probability"""
        full_text = f"{title} {summary}".lower()
        
        impact_analysis = "💱 **IMPACTO EUR/USD:**\n\n"
        
        # Fed rate hikes/cuts (más importante para USD)
        if 'fed' in full_text or 'federal reserve' in full_text:
            if 'raise' in full_text or 'hike' in full_text or 'increase' in full_text:
                impact_analysis += "🔴 EUR/USD VA A BAJAR\n"
                impact_analysis += "   Probabilidad: ALTA (80-90%)\n\n"
                impact_analysis += "¿Por qué? La Fed sube tasas → Dólar más fuerte → EUR vale menos\n"
                impact_analysis += "Ejemplo: Si está en 1.0800, puede bajar a 1.0700 o menos"
            elif 'cut' in full_text or 'lower' in full_text or 'reduce' in full_text or 'easing' in full_text:
                impact_analysis += "🟢 EUR/USD VA A SUBIR\n"
                impact_analysis += "   Probabilidad: ALTA (80-90%)\n\n"
                impact_analysis += "¿Por qué? La Fed baja tasas → Dólar más débil → EUR vale más\n"
                impact_analysis += "Ejemplo: Si está en 1.0800, puede subir a 1.0900 o más"
            else:
                impact_analysis += "🟡 EUR/USD IMPACTO MODERADO\n"
                impact_analysis += "   Probabilidad: MEDIA (50-60%)\n\n"
                impact_analysis += "Noticia de la Fed sin cambio claro de tasas. Esperar datos concretos."
        
        # ECB news (más importante para EUR)
        elif 'ecb' in full_text or 'european central bank' in full_text:
            if 'raise' in full_text or 'hike' in full_text or 'tighten' in full_text:
                impact_analysis += "🟢 EUR/USD VA A SUBIR\n"
                impact_analysis += "   Probabilidad: ALTA (75-85%)\n\n"
                impact_analysis += "¿Por qué? BCE sube tasas → Euro más fuerte → EUR vale más vs USD"
            elif 'cut' in full_text or 'lower' in full_text or 'easing' in full_text:
                impact_analysis += "🔴 EUR/USD VA A BAJAR\n"
                impact_analysis += "   Probabilidad: ALTA (75-85%)\n\n"
                impact_analysis += "¿Por qué? BCE baja tasas → Euro más débil → EUR vale menos vs USD"
            else:
                impact_analysis += "🟡 EUR/USD IMPACTO MODERADO\n"
                impact_analysis += "   Probabilidad: MEDIA (50-60%)\n\n"
                impact_analysis += "Noticia del BCE. Puede mover el par dependiendo del tono del anuncio."
        
        # Inflation news
        elif 'inflation' in full_text:
            if 'rising' in full_text or 'higher' in full_text or 'surge' in full_text:
                impact_analysis += "🟡 EUR/USD VOLÁTIL\n"
                impact_analysis += "   Probabilidad: MEDIA (60-70%)\n\n"
                impact_analysis += "Inflación alta → Bancos centrales pueden subir tasas\n"
                impact_analysis += "Si es inflación USA: EUR/USD baja. Si es inflación Europa: EUR/USD sube."
            else:
                impact_analysis += "🟢 EUR/USD PUEDE SUBIR\n"
                impact_analysis += "   Probabilidad: BAJA-MEDIA (40-60%)\n\n"
                impact_analysis += "Inflación baja → Menos presión para subir tasas → Dólar más débil"
        
        # Risk-off/Risk-on (general market sentiment)
        elif 'recession' in full_text or 'crash' in full_text or 'crisis' in full_text:
            impact_analysis += "🔴 EUR/USD VA A BAJAR\n"
            impact_analysis += "   Probabilidad: ALTA (70-80%)\n\n"
            impact_analysis += "Pánico en mercados → Todos compran dólares (moneda refugio)\n"
            impact_analysis += "EUR/USD cae porque USD se fortalece por miedo."
        
        # Earnings/Corporate (menos impacto directo)
        elif 'earnings' in full_text or 'profit' in full_text:
            impact_analysis += "🟡 EUR/USD IMPACTO BAJO\n"
            impact_analysis += "   Probabilidad: BAJA (20-40%)\n\n"
            impact_analysis += "Noticias corporativas afectan poco a EUR/USD directamente.\n"
            impact_analysis += "Solo si hay efecto cascada en economía general."
        
        # Default case
        else:
            impact_analysis += "⚪ EUR/USD IMPACTO MÍNIMO\n"
            impact_analysis += "   Probabilidad: BAJA (10-30%)\n\n"
            impact_analysis += "Esta noticia no tiene impacto directo en el par EUR/USD.\n"
            impact_analysis += "Puede afectar indirectamente si mueve sentimiento general del mercado."
        
        return impact_analysis[:max_length]
    
    def _generate_market_implications(self, title, summary, entities, tags, max_length=500):
        """Generate market implications focused on EUR/USD binary options trading"""
        implications = "⚡ **SEÑAL PARA TRADING BINARIO EUR/USD:**\n\n"
        
        full_text = f"{title} {summary}".lower()
        
        # Fed / Interest rates (IMPACTO MÁS FUERTE)
        if 'fed' in full_text or 'federal reserve' in full_text:
            if 'raise' in full_text or 'hike' in full_text:
                implications += "📉 **PUT (VENTA)** - EUR/USD va a bajar\n"
                implications += "🎯 Probabilidad: 85%\n"
                implications += "⏰ Ventana: 30-60 minutos\n"
                implications += "🔥 Volatilidad: ALTA\n\n"
                implications += "💡 Estrategia:\n"
                implications += "   → Opción PUT de 2-5 minutos\n"
                implications += "   → Entrar apenas salga la noticia\n"
                implications += "   → Stop si sube más de 10 pips\n"
            elif 'cut' in full_text or 'lower' in full_text or 'easing' in full_text:
                implications += "📈 **CALL (COMPRA)** - EUR/USD va a subir\n"
                implications += "🎯 Probabilidad: 85%\n"
                implications += "⏰ Ventana: 30-60 minutos\n"
                implications += "🔥 Volatilidad: ALTA\n\n"
                implications += "💡 Estrategia:\n"
                implications += "   → Opción CALL de 2-5 minutos\n"
                implications += "   → Entrar apenas salga la noticia\n"
                implications += "   → Stop si baja más de 10 pips\n"
            else:
                implications += "⚠️ **ESPERAR** - Sin señal clara\n"
                implications += "🎯 No operar hasta tener dirección\n"
        
        # ECB news (IMPACTO FUERTE)
        elif 'ecb' in full_text or 'european central bank' in full_text:
            if 'raise' in full_text or 'hike' in full_text:
                implications += "📈 **CALL (COMPRA)** - EUR/USD va a subir\n"
                implications += "🎯 Probabilidad: 80%\n"
                implications += "⏰ Ventana: 30-90 minutos\n"
                implications += "🔥 Volatilidad: ALTA\n\n"
                implications += "💡 Estrategia:\n"
                implications += "   → Opción CALL de 3-5 minutos\n"
                implications += "   → BCE sube tasas = Euro más fuerte\n"
            elif 'cut' in full_text or 'lower' in full_text or 'easing' in full_text:
                implications += "📉 **PUT (VENTA)** - EUR/USD va a bajar\n"
                implications += "🎯 Probabilidad: 80%\n"
                implications += "⏰ Ventana: 30-90 minutos\n"
                implications += "🔥 Volatilidad: ALTA\n"
        
        # Inflation (IMPACTO MEDIO)
        elif 'inflation' in full_text:
            if 'us' in full_text or 'united states' in full_text:
                implications += "📉 **PUT (VENTA)** - EUR/USD baja\n"
                implications += "🎯 Probabilidad: 70%\n"
                implications += "⏰ Ventana: 60 minutos\n"
                implications += "💡 Inflación USA alta → Fed sube tasas → USD fuerte\n"
            elif 'euro' in full_text or 'europe' in full_text:
                implications += "📈 **CALL (COMPRA)** - EUR/USD sube\n"
                implications += "🎯 Probabilidad: 70%\n"
                implications += "⏰ Ventana: 60 minutos\n"
                implications += "💡 Inflación Europa alta → BCE sube tasas → EUR fuerte\n"
            else:
                implications += "⚠️ Esperar confirmación de qué zona es\n"
        
        # Risk-off (Crisis, recesión)
        elif 'recession' in full_text or 'crash' in full_text or 'crisis' in full_text:
            implications += "📉 **PUT (VENTA)** - EUR/USD baja por pánico\n"
            implications += "🎯 Probabilidad: 75%\n"
            implications += "⏰ Ventana: 2-4 horas\n"
            implications += "🔥 Volatilidad: MUY ALTA\n\n"
            implications += "💡 Crisis → Todos compran USD (refugio seguro)\n"
            implications += "⚠️ Cuidado: Movimientos bruscos\n"
        
        # Earnings/Corporate (IMPACTO BAJO)
        elif 'earnings' in full_text or 'profit' in full_text:
            implications += "⏸️ **NO OPERAR** - Impacto mínimo en EUR/USD\n"
            implications += "🎯 Noticias corporativas no mueven pares de divisas\n"
            implications += "💡 Esperar noticias macroeconómicas\n"
        
        # Default
        else:
            implications += "📊 **ANALIZAR** - Sin señal automática\n"
            implications += "🎯 Revisar gráfico EUR/USD en tiempo real\n"
            implications += "💡 Buscar niveles de soporte/resistencia\n"
            implications += "⏰ No operar sin confirmación\n"
        
        implications += "\n🌍 Horario NY: 9:30-16:00 (mayor volumen)\n"
        implications += "⚡ Mejor momento para opciones binarias corto plazo"
        
        return implications[:max_length]
    
    def _analyze_with_ai(self, news_id, title, summary, entities, tags):
        """Analiza noticia con IA (Groq > Ollama > Keywords fallback)"""
        try:
            if self.ai_mode == 'groq':
                result = self._analyze_with_groq(news_id, title, summary, entities, tags)
                if result:
                    return result
                # Fallback to Ollama if Groq fails
                self.logger.warning("Groq failed, falling back to Ollama")
                if self._check_ollama():
                    return self._analyze_with_ollama(news_id, title, summary, entities, tags)
                return None
            elif self.ai_mode == 'ollama':
                return self._analyze_with_ollama(news_id, title, summary, entities, tags)
        except Exception as e:
            self.logger.error(f"AI analysis error: {str(e)}")
            return None
    
    def _build_analysis_prompt(self, title, summary):
        """Build the analysis prompt (shared by Groq and Ollama)."""
        from src.common.db import get_learned_lessons
        lessons = ''
        try:
            lessons = get_learned_lessons()
            if lessons:
                lessons = f"\n\nAPRENDIZAJE DE TRADES ANTERIORES (usá esto para calibrar tu análisis):\n{lessons}"
        except Exception:
            pass

        return f"""Sos analista de trading de opciones binarias EUR/USD. Analizá esta noticia y decidí si OPERAR o NO OPERAR.

TÍTULO: {title}
CONTENIDO: {summary[:500]}
{lessons}
Responde SOLO con JSON válido (sin markdown, sin ```json). Cada campo debe ser ÚNICO para esta noticia específica:
{{
    "impact_score": <NÚMERO 0-100>,
    "level": "<BAJA|MEDIA|ALTA|CRITICA>",
    "should_operate": <true|false>,
    "direction": "<CALL|PUT|NEUTRAL>",
    "confidence": <NÚMERO 0-100 con 2 decimales>,
    "timeframe": "<duración sugerida>",
    "explanation": "<qué pasó y por qué importa - máx 3 líneas>",
    "eur_usd_impact": "<empezar con CALL/PUT/NEUTRAL y explicar impacto>",
    "market_implications": "<empezar con ACCIÓN: OPERAR o ACCIÓN: NO OPERAR>"
}}

GUÍA DE SCORES (impact_score - importancia de la noticia):
- 90-100: Cambio de tasas Fed/ECB, crisis financiera
- 75-89: Datos de inflación, empleo, PIB que sorprenden
- 50-74: Noticias económicas secundarias con poco impacto forex
- 20-49: Noticias corporativas, earnings, M&A (no mueven EUR/USD)
- 0-19: Noticias sin relación a forex

GUÍA DE CONFIDENCE (probabilidad de acertar la dirección):
- Evaluar: ¿la noticia indica CLARAMENTE una dirección para EUR/USD?
- 85-100: Señal clarísima (Fed sube tasas → USD fuerte → PUT seguro)
- 65-84: Señal probable pero con matices
- 40-64: Dirección incierta, depende de interpretación
- 0-39: No hay señal clara → direction debe ser NEUTRAL

IMPORTANTE:
- impact_score y confidence son INDEPENDIENTES. Una noticia puede ser importante (score=92) pero de dirección incierta (confidence=45)
- should_operate = true SOLO si score >= 75 Y confidence >= 60 Y direction es CALL o PUT
- Noticias sobre petróleo, oro, acciones, M&A: generalmente score < 50 para EUR/USD
- Si la noticia NO afecta directamente a USD o EUR: direction = NEUTRAL, score bajo
- NO copies valores de ejemplo. ANALIZA la noticia y genera scores ÚNICOS"""

    def _parse_ai_result(self, news_id, result_text, method):
        """Parse JSON result from AI response. Shared by Groq and Ollama."""
        json_start = result_text.find('{')
        json_end = result_text.rfind('}') + 1
        if json_start < 0 or json_end <= json_start:
            self.logger.error(f"No JSON found in {method} response")
            return None

        result = json.loads(result_text[json_start:json_end])

        should_operate = result.get('should_operate', False)
        impact_score = int(result.get('impact_score', 50))
        confidence = float(result.get('confidence', 50.0))

        should_alert = should_operate and impact_score >= 80

        self.logger.info(f"{method}: {result.get('level')} - {result.get('direction')} - score={impact_score} conf={confidence:.1f}% - operate={should_operate}")

        return {
            'news_id': news_id,
            'impact_score': impact_score,
            'level': result.get('level', 'MEDIA'),
            'explanation': result.get('explanation', ''),
            'eur_usd_impact': result.get('eur_usd_impact', ''),
            'market_implications': result.get('market_implications', ''),
            'analysis_method': method,
            'should_operate': should_operate,
            'direction': result.get('direction', 'NEUTRAL'),
            'confidence': confidence,
            'should_alert': should_alert
        }

    def _analyze_with_groq(self, news_id, title, summary, entities, tags):
        """Analiza con Groq API (Llama 70B en la nube - gratis y rápido)"""
        try:
            import requests
            from src.common.config import Config

            api_key = Config.GROQ_API_KEY
            if not api_key:
                return None

            prompt = self._build_analysis_prompt(title, summary)

            self.logger.info(f"Analizando noticia #{news_id} con Groq/Llama-70B...")

            resp = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': Config.GROQ_MODEL,
                    'messages': [
                        {'role': 'system', 'content': 'Sos un analista experto de forex EUR/USD. Respondé SOLO con JSON válido.'},
                        {'role': 'user', 'content': prompt}
                    ],
                    'temperature': 0.5,
                    'max_tokens': 500,
                    'stream': False
                },
                timeout=30
            )

            if resp.status_code != 200:
                self.logger.error(f"Groq HTTP error: {resp.status_code} - {resp.text[:200]}")
                return None

            result_text = resp.json()['choices'][0]['message']['content']
            self.logger.debug(f"Groq response: {result_text[:200]}")

            return self._parse_ai_result(news_id, result_text, 'groq')

        except Exception as e:
            self.logger.error(f"Groq analysis error: {str(e)}")
            return None

    def _analyze_with_ollama(self, news_id, title, summary, entities, tags):
        """Analiza con Llama local via Ollama (fallback)"""
        try:
            import requests

            prompt = self._build_analysis_prompt(title, summary)
            self.logger.info(f"Analizando noticia #{news_id} con Ollama/Llama-8B...")

            response = requests.post('http://localhost:11434/api/generate',
                json={
                    'model': 'llama3.1:8b',
                    'prompt': prompt,
                    'stream': False,
                    'format': 'json',
                    'options': {
                        'temperature': 0.5,
                        'top_p': 0.9,
                        'num_predict': 500
                    }
                },
                timeout=45
            )

            if response.status_code != 200:
                self.logger.error(f"Ollama HTTP error: {response.status_code}")
                return None

            result_text = response.json().get('response', '')
            self.logger.debug(f"Ollama response: {result_text[:200]}")

            return self._parse_ai_result(news_id, result_text, 'ollama')

        except Exception as e:
            self.logger.error(f"Ollama analysis error: {str(e)}")
            return None
    
    def _analyze_with_claude(self, news_id, title, summary, entities, tags):
        """Analiza con Claude AI (requiere ANTHROPIC_API_KEY)"""
        # Placeholder para futura implementación
        self.logger.warning("Claude analysis not implemented yet")
        return None

