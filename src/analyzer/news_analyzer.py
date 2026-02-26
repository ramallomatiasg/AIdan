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
        """Detecta qué modo de IA usar: ollama > claude > keywords"""
        # Prioridad: Ollama (local/gratis) > Claude (API/pago) > Keywords (fallback)
        
        if self._check_ollama():
            return 'ollama'
        elif os.getenv('ANTHROPIC_API_KEY'):
            return 'claude'
        else:
            return 'keywords'
    
    def _check_ollama(self):
        """Verifica si Ollama está disponible"""
        try:
            import requests
            response = requests.get('http://localhost:11434/api/tags', timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                # Verifica si hay algún modelo Llama disponible
                return any('llama' in m.get('name', '').lower() for m in models)
            return False
        except:
            return False
    
    def analyze(self, news_id, title, summary, entities, tags):
        """Analyze news and calculate impact score with EUR/USD analysis"""
        try:
            # Use AI analysis if available, fallback to keywords
            if self.ai_mode in ['ollama', 'claude']:
                result = self._analyze_with_ai(news_id, title, summary, entities, tags)
                if result:
                    return result
                # If AI fails, fallback to keywords
                self.logger.warning(f"AI analysis failed, using keywords fallback")
            
            # Keyword-based analysis (original logic)
            score = self._calculate_impact_score(title, summary, entities, tags)
            
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
        """Analiza noticia con IA (Ollama o Claude)"""
        try:
            if self.ai_mode == 'ollama':
                return self._analyze_with_ollama(news_id, title, summary, entities, tags)
            elif self.ai_mode == 'claude':
                return self._analyze_with_claude(news_id, title, summary, entities, tags)
        except Exception as e:
            self.logger.error(f"AI analysis error: {str(e)}")
            return None
    
    def _analyze_with_ollama(self, news_id, title, summary, entities, tags):
        """Analiza con Llama local via Ollama"""
        try:
            import requests
            
            prompt = f"""Eres un analista experto de mercados financieros especializado en EUR/USD y trading de opciones binarias.

Analiza esta noticia:
TÍTULO: {title}
CONTENIDO: {summary[:500]}

Evalúa el impacto en EUR/USD y genera una señal de trading.

Responde SOLO con un JSON válido (sin texto adicional, sin markdown):
{{
    "impact_score": 85,
    "level": "ALTA",
    "direction": "CALL",
    "confidence": 75,
    "timeframe": "3-5 minutos",
    "explanation": "Explica brevemente por qué",
    "eur_usd_impact": "Describe el impacto en el par",
    "market_implications": "Recomendación de trading específica"
}}

Reglas:
- impact_score: 0-100 (impacto en el mercado)
- level: ALTA (score>80), MEDIA (50-80), o BAJA (<50)
- direction: CALL (sube EUR/USD), PUT (baja EUR/USD), NEUTRAL
- confidence: 0-100 (probabilidad de acierto)
- timeframe: "1-5 minutos" ideal para binarias"""

            self.logger.info(f"Analizando noticia #{news_id} con Ollama/Llama...")
            
            response = requests.post('http://localhost:11434/api/generate', 
                json={
                    'model': 'llama3.1:8b',
                    'prompt': prompt,
                    'stream': False,
                    'format': 'json',
                    'options': {
                        'temperature': 0.2,
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
            
            # Extraer JSON de la respuesta
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(result_text[json_start:json_end])
            else:
                self.logger.error("No se encontró JSON válido en respuesta de Ollama")
                return None
            
            self.logger.info(f"✅ Ollama análisis exitoso: {result.get('level')} - {result.get('direction')}")
            
            # Formatear resultado
            return {
                'news_id': news_id,
                'impact_score': int(result.get('impact_score', 50)),
                'level': result.get('level', 'MEDIA'),
                'explanation': result.get('explanation', ''),
                'eur_usd_impact': result.get('eur_usd_impact', ''),
                'market_implications': result.get('market_implications', ''),
                'should_alert': result.get('level') == 'ALTA'
            }
            
        except Exception as e:
            self.logger.error(f"Ollama analysis error: {str(e)}")
            return None
    
    def _analyze_with_claude(self, news_id, title, summary, entities, tags):
        """Analiza con Claude AI (requiere ANTHROPIC_API_KEY)"""
        # Placeholder para futura implementación
        self.logger.warning("Claude analysis not implemented yet")
        return None

