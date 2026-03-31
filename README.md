# AIdan v3.0 - Asistente de Scalping EUR/USD con IA + Auto-Optimizacion

Sistema de trading asistido que monitorea noticias financieras en tiempo real, analiza estructura de mercado en multiples temporalidades (H1, M15, M5), genera senales de trading para EUR/USD usando inteligencia artificial, y **optimiza sus propios parametros automaticamente** aprendiendo de resultados pasados.

**Un solo ejecutable de ~25MB - Portable, gratis y privado.**

---

## Que hay de nuevo en v3.0

- **AutoTuner**: optimizador autonomo que ajusta parametros cada 4 horas analizando el historial de trades
- **Bloqueo automatico de setups perdedores**: si un tipo de senal tiene <35% win rate en 8+ trades, se desactiva solo
- **Filtro de sesiones**: detecta si operar fuera de London/NY es rentable y bloquea esas horas si no lo es
- **Minimo de pips para win**: no cuenta como win un trade que se movio <1.5 pips (evita falsos positivos)
- **Snapshots estaticos de graficos**: las estrategias guardan las velas del momento de creacion, ya no se mueven
- **Ventana estable en Windows**: no se cierra al cambiar de ventana, aparece en la barra de tareas
- **Notificaciones toast**: popup tipo Windows con grafico y Entry/TP/SL cuando se genera una nueva estrategia
- **Filtro HTF obligatorio**: bloquea senales contra la tendencia del timeframe mayor (no mas CALL en mercado bearish fuerte)
- **Anti-contradiccion**: no genera CALL y PUT al mismo tiempo (consensus + dedup en DB)
- **Datos persistentes**: la base de datos y configuracion se guardan en %APPDATA%/AIdan/ (sobrevive a cierres)

---

## Instalacion

### Usuarios

1. Descomprime `AIdan_Portable.rar`
2. Ejecuta `AIdan_TodoEnUno.exe`
3. La primera vez descarga 2 modelos de IA (~8GB total) - tarda 10-15 min segun tu internet
4. Listo. Se abre solo en el navegador en `http://localhost:8000`

**Requisitos:**
- Windows 10/11
- 8GB de RAM minimo (16GB recomendado)
- 10GB de disco libre (para los modelos de IA)
- Conexion a internet

### Desarrolladores

```bash
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan
pip install -r requirements.txt
ollama pull llama3.1:8b
ollama pull llava
python AIdan_TodoEnUno.py
```

---

## Como funciona

AIdan corre 4 servicios en paralelo dentro de un solo proceso:

### 1. Collector (cada 10 min)
Busca noticias en Bloomberg, Reuters, Financial Times y otras fuentes RSS financieras. Las guarda en una base de datos SQLite local.

### 2. Analyzer (cada 2 min)
Analiza todo lo que tiene disponible:

- **NewsAnalyzer**: usa Groq (Llama 3.3 70B) u Ollama local para evaluar si una noticia afecta EUR/USD, con que direccion y confianza
- **TechnicalAnalyzer**: calcula RSI, Medias Moviles, Bollinger Bands, soportes/resistencias. Detecta breakouts, reversiones RSI, cruces de MA, expansiones de momentum
- **MTFAnalyzer**: analiza velas en H1, M15 y M5 simultaneamente. Detecta swings (HH, HL, LH, LL) y estructura de mercado
- **SMCEngine**: Smart Money Concepts - identifica zonas de demanda/oferta y espera confirmacion del timeframe menor
- **AutoTuner**: optimiza parametros cada 4 horas analizando el historial de trades

### 3. API (FastAPI en localhost:8000)
Servidor web que sirve el dashboard y expone endpoints para datos en tiempo real.

### 4. Strategy Watcher
Thread que monitorea nuevas estrategias y muestra notificaciones toast en Windows.

---

## Dashboard

### Barra superior
- **AIdan / SCALPING EUR/USD** - nombre del sistema
- **Reloj** - hora actual
- **Activo** (verde) - servicios corriendo
- Chips con estadisticas: NOTICIAS, ALERTAS, ULTIMA HORA, WIN RATE, HISTORIAL (W/L)

### Pestana DASHBOARD

**Grafico EUR/USD** - velas en tiempo real (TradingView) con MA 9, Bollinger Bands, RSI y Volumen. Timeframes: 1m, 5m, 15m, 1h.

**Chat AIdan** - chat con IA sobre trading. Acepta imagenes de graficos. Usa datos en tiempo real + analisis SMC para responder. Actua como coach de disciplina.

**Alertas de Trading** - noticias analizadas con direccion (CALL/PUT/NEUTRAL), confianza, score e instruccion de operar o no. Filtros por direccion, confianza y periodo.

**Calendario Economico** - eventos de la semana para EUR y USD (impacto medio y alto).

### Pestana ESTRATEGIAS

**Panel Multi-Temporalidad SMC** - estado de H1, M15 y M5 con tendencia, swings, estructura y badge de confirmacion:
- Verde "CONFIRMADO": setup valido, se puede operar
- Amarillo "ESPERANDO": en zona pero sin confirmacion de M5
- Azul "BUSCANDO ZONA": hay tendencia pero precio no esta en zona
- Gris "SIN SETUP": sin tendencia clara

**Estrategias Auto-Generadas** - se generan de 3 formas:
1. **NOTICIA** (azul): noticia de alto impacto con direccion clara
2. **ESTRUCTURA** (violeta): breakouts, RSI extremo, cruces MA, momentum
3. **SMC** (rosa): confirmacion completa HTF + zona + LTF

Cada estrategia muestra grafico de velas estatico (snapshot del momento de creacion), Entry/TP/SL, confianza, y se auto-evalua al expirar.

**Parametros** - configura filtros (score minimo, confianza minima, direccion, SL/TP en pips, expiracion). Podes guardar perfiles con distintas configuraciones.

---

## AutoTuner - Optimizacion Autonoma

El AutoTuner es el cerebro de autoaprendizaje de AIdan. Corre automaticamente cada 4 horas.

### Que hace
1. **Lee los ultimos 200 trades** evaluados (win/loss) de la base de datos
2. **Evalua el rendimiento actual** con los parametros vigentes
3. **Prueba variaciones** de cada parametro (RSI thresholds, distancias, confianzas base, etc.)
4. **Adopta las mejoras** si una variacion sube el win rate en >1%
5. **Bloquea setups malos** con <35% win rate en 8+ trades
6. **Analiza sesiones** y bloquea horarios no rentables

### Parametros que optimiza
| Categoria | Parametros |
|-----------|-----------|
| RSI | Oversold (25-35), Overbought (65-75), proximidad a S/R |
| Bollinger | Proximidad a banda y a S/R |
| Breakout | Distancia maxima al nivel |
| Momentum | Rango de consolidacion, multiplicador de expansion |
| Confianza base | Por cada tipo de setup |
| Sesiones | Horarios London/NY, bloqueo fuera de sesion |
| Auto-eval | Pips minimos para contar como win |

### Endpoints
- `GET /tuner-status` - estado actual, parametros, setups bloqueados
- `POST /tuner-run` - forzar ciclo de optimizacion manual
- `GET /blocked-setups` - tipos de setup bloqueados por bajo rendimiento

### Requisitos
Necesita **minimo 10 trades evaluados** para empezar a optimizar. A mas trades, mejor optimiza. No necesita intervencion manual.

---

## Metodologia de Trading

### Smart Money Concepts (SMC)

1. **Tendencia HTF (H1/M15)**: si H1 es alcista, solo CALL
2. **Zona de demanda/oferta**: esperar que el precio llegue a una zona de reaccion previa
3. **Confirmacion LTF (M5)**: en la zona, M5 forma HH (para CALL) o LL (para PUT)
4. **Entrada**: solo con confirmacion completa

### Cuando OPERAR
- Badge "CONFIRMADO" en el panel SMC
- H1 y M15 alineados
- Noticia de alto impacto + score y confianza sobre el umbral del perfil
- Analisis tecnico no contradice

### Cuando NO OPERAR
- Badge "ESPERANDO CONFIRMACION" - sin confirmar en M5
- Noticias corporativas (no mueven forex)
- Contra la tendencia HTF
- Precio ya salio de la zona - no perseguir

---

## Arquitectura

```
AIdan_TodoEnUno.exe (~25MB)
  |
  +-- Collector (thread) --> RSS cada 10 min
  |     Bloomberg, Reuters, Financial Times
  |
  +-- Analyzer (thread) --> Analiza cada 2 min
  |     +-- NewsAnalyzer: Groq/Ollama analiza noticias
  |     +-- TechnicalAnalyzer: RSI, MA, BB, S/R (Yahoo Finance)
  |     +-- MTFAnalyzer: velas H1/M15/M5, swings, estructura
  |     +-- SMCEngine: zonas demanda/oferta + confirmacion LTF
  |     +-- StructureScanner: breakouts, reversiones, cruces MA
  |     +-- AutoTuner: optimiza parametros cada 4h
  |
  +-- API (thread) --> FastAPI en localhost:8000
  |     Dashboard HTML + Chat + Graficos TradingView
  |
  +-- Strategy Watcher (thread) --> Toast notifications
```

**Modelos de IA:**
- **Groq API** (gratis) - `llama-3.3-70b-versatile` para chat y analisis (rapido, en la nube)
- `llama3.1:8b` (~4GB) - analisis local con Ollama (fallback si no hay internet)
- `llava` (~4GB) - analisis de imagenes/graficos en el chat (local)

**Datos persistentes** en `%APPDATA%/AIdan/`:
- `state/financial_news.db` - base de datos SQLite con noticias, alertas, estrategias, resultados y parametros optimizados
- `config/` - configuracion de fuentes y perfiles

---

## Build

```bash
pyinstaller AIdan_TodoEnUno.spec --clean
```

El ejecutable queda en `dist/AIdan_TodoEnUno.exe`.

---

## Historial de versiones

### v3.0 (26 Mar 2026)
- **AutoTuner**: optimizador autonomo de parametros basado en historial de trades
- Bloqueo automatico de setups con win rate <35%
- Filtro de sesiones (London/NY) con deteccion de horarios no rentables
- Snapshots estaticos de graficos en estrategias (ya no se mueven)
- Notificaciones toast tipo Windows con grafico + Entry/TP/SL
- Filtro HTF obligatorio: bloquea senales contra tendencia mayor
- Anti-contradiccion: consensus de direccion + dedup en DB (15 min)
- Rate limit global: 5 min entre estrategias
- Ventana tkinter estable (thread-safe, visible en taskbar)
- Datos persistentes en %APPDATA%/AIdan/
- Auto-evaluacion mejorada con minimo de pips para win
- Logging mejorado con uvicorn compatible con exe congelado

### v3.1.0 (31 Mar 2026)
- Deteccion de patrones de velas japonesas (hammer, engulfing, shooting star, doji, morning/evening star, marubozu)
- Boost/penalizacion de confianza segun patron confirme o contradiga la senal
- Calendar Pre-News Trading: genera estrategias straddle 30 min antes de datos High Impact
- Break Even automatico: SL se mueve a entry cuando precio alcanza 1:1 R:R
- Nuevo status auto_break_even (no cuenta como win ni loss)
- Dashboard segmentado por tipo: NEWS / ESTRUCTURA / SMC / CALENDARIO / PATRON
- Filtros por trigger_type en panel de estrategias
- Base de conocimiento profesional: VWAP, Order Flow, velas, break even, scalping EUR/USD
- Versionado semantico MAJOR.MINOR.PATCH

### v3.0.0 (31 Mar 2026)
- SL/TP adaptativo por ATR (ya no fijo 5/10 pips)
- Confirmacion de cierre de vela anti-mecha para breakouts
- Confianza dinamica por sesion de trading (London/NY boost, Asian penalty)
- Expiracion adaptativa 15-60 min segun volatilidad
- Gate de spread (no genera si spread > 25% del SL)
- Resolucion de conflictos entre fuentes (news vs structure vs SMC)
- Impact score basado en historial real de win rates
- Evaluacion de estrategias pendientes al reiniciar
- Calendario economico (Forex Factory) inyectado al news analyzer
- Deteccion de Groq API key expirada con fallback a Ollama mejorado
- Version centralizada en Config con endpoint /version
- Dashboard lee version del server dinamicamente

### v2.2 (20 Mar 2026)
- Smart Money Concepts (SMC): analisis multi-temporalidad H1/M15/M5
- Panel visual de tendencias con estructura HH/HL/LH/LL
- Zonas de demanda y oferta automaticas
- Confirmacion de entrada por M5
- Chat con coaching de disciplina SMC
- Groq API como modelo principal del chat

### v2.0 (20 Mar 2026)
- Tests unitarios con pytest
- Dashboard multi-tema (claro/oscuro)
- Mejoras en analisis y manejo de errores

### v1.3 (18 Mar 2026)
- Pestana Estrategias con graficos de velas
- Estrategias automaticas por noticias de alto impacto
- Analisis tecnico integrado
- Chat con imagenes (llava)
- Perfiles de configuracion

### v1.2 (02 Mar 2026)
- Dashboard con grafico TradingView
- Alertas con filtros
- Chat con IA
- Calendario economico
- Ejecutable portable

### v1.0
- Recolector RSS + analisis por keywords + dashboard minimo

---

## Licencia

MIT - Uso libre.

## Disclaimer

AIdan es una herramienta de asistencia, NO un sistema de trading automatico. Las senales son orientativas y no garantizan resultados. Opera bajo tu propio riesgo y criterio. Nunca arriesgues dinero que no puedas perder.
