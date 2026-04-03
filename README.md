# AIdan v3.4 - Asistente de Scalping EUR/USD con IA + Auto-Optimizacion

Sistema de trading asistido que monitorea noticias financieras en tiempo real, analiza estructura de mercado en multiples temporalidades (H1, M15, M5), genera senales de trading para EUR/USD usando inteligencia artificial, y **optimiza sus propios parametros automaticamente** aprendiendo de resultados pasados.

**Un solo ejecutable de ~25MB - Portable, gratis y privado.**

---

## Que hay de nuevo en v3.4

- **Login de usuarios**: pantalla de ingreso con usuario y clave al abrir AIdan. Solo usuarios autorizados pueden acceder
- **Cambio de clave**: cada usuario puede cambiar su clave desde el dashboard (clic en su nombre)
- **Aprendizaje Compartido**: multiples instancias de AIdan sincronizan trades anonimizados a la nube (Supabase) para aprender entre todos
- **Conexion automatica**: al loguearse, el shared learning se activa automaticamente sin configuracion extra
- **Datos anonimizados**: no se comparten precios exactos, titulos de noticias ni datos de cuenta MT5
- **Ejecucion MT5 mejorada**: sync de posiciones, cierre automatico, deteccion de huerfanas, reconexion automatica

---

## Instalacion

### Usuarios

1. Ejecuta `AIdan.exe`
2. Se abre solo en el navegador en `http://localhost:8000`
3. Ingresa con tu usuario y clave
4. El aprendizaje compartido se activa automaticamente al loguearse

**Requisitos:**
- Windows 10/11
- 4GB de RAM minimo
- Conexion a internet (usa Groq API en la nube, no requiere modelos locales)

### Desarrolladores

```bash
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan
pip install -r requirements.txt
python AIdan_TodoEnUno.py
```

Requiere variable de entorno `GROQ_API_KEY` con una API key de [Groq](https://console.groq.com/) (gratis).

---

## Como funciona

AIdan corre 4 servicios en paralelo dentro de un solo proceso:

### 1. Collector (cada 10 min)
Busca noticias en Bloomberg, Reuters, Financial Times y otras fuentes RSS financieras. Las guarda en una base de datos SQLite local.

### 2. Analyzer (cada 1 min)
Analiza todo lo que tiene disponible:

- **NewsAnalyzer**: usa Groq (Llama 3.3 70B) para evaluar si una noticia afecta EUR/USD, con que direccion y confianza
- **TechnicalAnalyzer**: calcula RSI, Medias Moviles, Bollinger Bands, soportes/resistencias. Detecta breakouts, reversiones RSI, cruces de MA, expansiones de momentum
- **MTFAnalyzer**: analiza velas en H1, M15 y M5 simultaneamente. Detecta swings (HH, HL, LH, LL) y estructura de mercado
- **SMCEngine**: Smart Money Concepts - identifica zonas de demanda/oferta y espera confirmacion del timeframe menor
- **AutoTuner**: optimiza parametros cada 30 min analizando el historial de trades

### 3. API (FastAPI en localhost:8000)
Servidor web que sirve el dashboard y expone endpoints para datos en tiempo real.

### 4. Strategy Watcher
Thread que monitorea nuevas estrategias y muestra notificaciones toast en Windows.

---

## Tipos de Setup (Estrategias)

AIdan detecta **7 tipos de patrones tecnicos** automaticamente en el grafico EUR/USD. Cada uno busca algo diferente:

| Setup | Que busca | Ejemplo |
|-------|-----------|---------|
| **breakout** | Precio rompe un nivel de resistencia/soporte y sigue | Precio cruza 1.1550 hacia arriba con fuerza |
| **bb_rejection** | Precio toca una Banda de Bollinger y rebota hacia el centro | Precio toca BB inferior y sube |
| **rsi_reversal** | RSI en zona extrema (sobrecompra/sobreventa) + nivel clave | RSI < 30 + precio en soporte = probable rebote |
| **ma_crossover** | Cruce de medias moviles (9 y 21 periodos) | MA9 cruza por encima de MA21 = senal alcista |
| **momentum** | Explosion de volatilidad despues de un periodo de calma | Rango de velas se expande 2x despues de consolidar |
| **trend_continuation** | Precio retrocede al soporte en tendencia alcista (o resistencia en bajista) | En tendencia alcista, precio baja a soporte y rebota |
| **level_bounce/rejection** | Rebote o rechazo en un nivel de precio clave | Precio toca soporte historico y no lo rompe |

### Como decide cual usar

No elige uno — **los detecta todos en paralelo**. Cada minuto escanea el grafico y si encuentra algun patron, genera una estrategia. Puede generar varias en el mismo ciclo si el mercado muestra multiples senales.

Cada senal pasa por **filtros** antes de convertirse en estrategia:

1. **Confirmacion de cierre de vela**: no se dispara mid-candle, requiere que la vela anterior haya cerrado por encima/debajo del nivel (evita falsas rupturas por mechas)
2. **Filtro de mecha**: si la mecha es >60% del rango de la vela, penaliza confianza -15
3. **Confianza minima**: se calcula dinamicamente desde el contexto de mercado (tendencia, RSI, volatilidad, sesion horaria, win rate historico del setup)
4. **Spread gate**: si el spread estimado es >25% del SL, descarta la senal
5. **ATR gate**: si la volatilidad es demasiado baja (ATR < 2 pips), penaliza fuerte
6. **Conflicto entre fuentes**: si noticias dicen CALL pero estructura dice PUT, penaliza al de menor confianza
7. **Deduplicacion**: no genera si ya existe una estrategia similar (misma direccion, mismo nivel, ultimos 30 min)

### SL/TP Adaptativos

El Stop Loss y Take Profit no son fijos — se adaptan a la volatilidad actual:

- **SL** = max(perfil, ATR x 1.2) — nunca mas ajustado que el ruido del mercado
- **TP** = max(perfil, ATR x 2.0) — minimo 2:1 risk/reward
- El TP se limita al soporte/resistencia mas cercano (no pone TP detras de un muro)
- El SL se coloca detras del nivel estructural mas cercano
- Minimo 1.5:1 risk/reward siempre
- Caps: SL max 15 pips, TP max 30 pips (scalping)

### Expiracion Adaptativa

La expiracion de cada estrategia se calcula segun cuanto tardaria el precio en llegar al TP con la volatilidad actual:

```
expiry = max(15, min(60, tp_pips / avg_range_pips * 5))
```

Resultado: entre 15 y 60 minutos dependiendo del ATR.

---

## Ciclo de Aprendizaje

AIdan no es estatico. Cada operacion que hace le ensena algo:

```
  1. DETECTA senal    ->    2. CREA estrategia    ->    3. ESPERA que expire
        ^                                                      |
  6. AJUSTA params    <-    5. ANALIZA historial   <-    4. EVALUA resultado
```

### Paso 1: Detecta una senal
Cada minuto escanea el grafico buscando patrones. Si encuentra uno, calcula una **confianza** basada en: tendencia, RSI, volatilidad, sesion horaria, y el **win rate historico de ese patron**.

### Paso 2: Crea la estrategia
Si la confianza supera el umbral y pasa todos los filtros, crea la estrategia con entry, SL, TP adaptativos. Queda activa por 15-60 minutos.

### Paso 3: Espera que expire
Durante ese tiempo, revisa las velas cada minuto para ver si toco el TP (gano), el SL (perdio), o el Break Even (se movio a entry despues de alcanzar 1:1 R:R).

### Paso 4: Evalua el resultado
Cuando expira, guarda el resultado con **todo el contexto**: direccion, setup_type, tendencia, RSI, sesion, pips, alineacion con HTF.

### Paso 5: Analiza el historial (cada 30 min)
El **AutoTuner** lee las ultimas 200 operaciones y:

1. Calcula el win rate actual como baseline
2. Prueba variaciones de cada parametro (umbrales RSI, distancias, confianzas)
3. Si alguna variacion mejora el win rate en >1%, la adopta
4. **Bloquea setups** con <35% win rate en 5+ trades (ej: si breakout tiene 30% → lo desactiva)
5. Si operar fuera de horario tiene <35% → bloquea sesion asiatica/off-hours

### Paso 6: Ajusta parametros
Los nuevos parametros se aplican inmediatamente. Ademas, la IA (Groq) recibe un resumen de lecciones aprendidas en cada analisis de noticias:

```
LECCIONES APRENDIDAS (42 operaciones):
  - CALL: 62% acierto (26W/16L)
  - PUT: 58% acierto (15W/10L)
  BB Rejection: 80% (8W/2L)
  Breakout: 35% (3W/6L) <- EVITAR
  - A FAVOR de HTF: 68% acierto
  - CONTRA HTF: 44% acierto <- EVITAR
```

---

## Dashboard

### Barra superior
- **AIdan / SCALPING EUR/USD** - nombre del sistema
- Chips con estadisticas: NOTICIAS, ALERTAS, ULTIMA HORA, NOTICIAS WR, ESTRATEGIAS WR

### Pestana DASHBOARD

**Grafico EUR/USD** - velas en tiempo real con precio live.

**Chat AIdan** - chat con IA sobre trading. Acepta imagenes de graficos. Usa datos en tiempo real + analisis SMC para responder.

**Alertas de Trading** - noticias analizadas con direccion (CALL/PUT/NEUTRAL), confianza, score. Las alertas con direccion se auto-evaluan a los 30 min mostrando un badge WIN/LOSS/BE con los pips.

**Calendario Economico** - eventos de la semana para EUR y USD.

### Pestana ESTRATEGIAS

**Panel Multi-Temporalidad SMC** - estado de H1, M15 y M5 con tendencia, swings, estructura y badge de confirmacion.

**Estrategias Auto-Generadas** - se generan de 4 fuentes:
1. **NOTICIA** (azul): noticia de alto impacto con direccion clara
2. **ESTRUCTURA** (violeta): breakouts, RSI extremo, cruces MA, momentum, rebotes
3. **SMC** (rosa): confirmacion completa HTF + zona + LTF
4. **CALENDARIO** (amarillo): pre-posicionamiento antes de datos economicos High Impact

Cada estrategia muestra grafico de velas (snapshot del momento), Entry/TP/SL, tiempo de expiracion, y se auto-evalua al expirar.

---

## Reporte a Google Sheets

AIdan puede subir un reporte diario a Google Sheets via webhook (Google Apps Script). Incluye:
- **Resumen Diario**: fecha, estrategias generadas, W/L/BE, win rate, pips netos, mejor y peor setup
- **Trades**: detalle de cada operacion con comentario en espanol explicando que hizo
- **Setup Analysis**: win rate por tipo de setup

Configuracion: setear `GOOGLE_SHEETS_WEBHOOK` en las variables de entorno o en config.py.

---

## Aprendizaje Compartido

AIdan comparte lo que aprende entre todas las instancias conectadas.
Cuando vos y otros usuarios usan AIdan, cada uno aporta trades y el sistema aprende de todos.

### Como funciona

1. Al abrir AIdan, ingresa con tu usuario y clave
2. El aprendizaje compartido se activa automaticamente
3. Cada 2 horas, AIdan sube tus trades (anonimizados) a la nube
4. Al mismo tiempo, descarga insights de otros usuarios
5. Los insights remotos tienen peso reducido (0.5x) para que tu aprendizaje local tenga prioridad

No requiere configuracion extra — todo se conecta automaticamente al loguearse.

### Que se comparte y que NO

| Se comparte | NO se comparte |
|-------------|----------------|
| Direccion (CALL/PUT) | Precios exactos de entrada/salida |
| Resultado (win/loss) | Titulo de la noticia |
| Pips ganados/perdidos | Datos de tu cuenta MT5 |
| Tipo de setup | Tu nombre o datos personales |
| Sesion horaria | Tickets de operacion |
| Indicadores (RSI, tendencia) | Balance o equity |

Si no configuras Supabase, AIdan funciona 100% igual que siempre (solo aprendizaje local).

---

## Arquitectura

```
AIdan_TodoEnUno.exe (~25MB)
  |
  +-- Collector (thread) --> RSS cada 10 min
  |     Bloomberg, Reuters, Financial Times
  |
  +-- Analyzer (thread) --> Analiza cada 1 min
  |     +-- NewsAnalyzer: Groq analiza noticias + lecciones aprendidas
  |     +-- TechnicalAnalyzer: RSI, MA, BB, S/R, ATR (Yahoo Finance)
  |     +-- MTFAnalyzer: velas H1/M15/M5, swings, estructura
  |     +-- SMCEngine: zonas demanda/oferta + confirmacion LTF
  |     +-- StructureScanner: 7 tipos de setup con filtros
  |     +-- AutoTuner: optimiza parametros cada 30 min
  |     +-- Alert Evaluator: auto-evalua alertas CALL/PUT a los 30 min
  |
  +-- API (thread) --> FastAPI en localhost:8000
  |     Dashboard HTML + Chat + Graficos
  |
  +-- Strategy Watcher (thread) --> Toast notifications
```

**Modelos de IA:**
- **Groq API** (gratis) - `llama-3.3-70b-versatile` para chat y analisis

**Datos persistentes** en `%APPDATA%/AIdan/`:
- `state/financial_news.db` - base de datos SQLite con noticias, alertas, estrategias, resultados y parametros optimizados

---

## Build

```bash
pyinstaller AIdan_TodoEnUno.spec --clean
```

El ejecutable queda en `dist/AIdan_TodoEnUno.exe`.

---

## Historial de versiones

### v3.4.0 (03 Abr 2026)
- **Login de usuarios**: pantalla de ingreso con autenticacion contra Supabase. Solo usuarios autorizados
- **Cambio de clave**: desde el dashboard, clic en tu nombre de usuario
- **Aprendizaje Compartido**: se activa automaticamente al loguearse. Sync cada 2 horas
- Credenciales de Supabase hardcodeadas — zero configuracion para el usuario
- Datos anonimizados: no se comparten precios, titulos ni datos de cuenta

### v3.3.0 (03 Abr 2026)
- **Integracion MT5 mejorada**: sync de posiciones con deal history, cierre automatico al evaluar
- **Kill switch inteligente**: evalua estrategias con P&L real de MT5 en vez de cancelarlas
- **Deteccion de huerfanas**: cierra posiciones MT5 sin estrategia asociada
- **Reconexion MT5 automatica**: si se pierde conexion, reconecta sin reiniciar
- **Learning Engine mejorado**: deep analysis cada 2h online, trigger_type insights, pattern blocking

### v3.2.0 (31 Mar 2026)
- Auto-evaluacion de alertas de noticias (CALL/PUT se evaluan a los 30 min)
- Deduplicacion de estrategias (no repite mismo setup/nivel en 30 min)
- Reporte diario a Google Sheets via webhook (resumen + trades con comentarios + setups)
- Escaneo cada 1 minuto (antes 2 min)
- Expiracion visible en cards de estrategias del dashboard
- Cooldown de senales tecnicas ampliado a 30 min (evita spam de breakouts)

### v3.1.0 (31 Mar 2026)
- Deteccion de patrones de velas japonesas (hammer, engulfing, shooting star, doji, morning/evening star, marubozu)
- Calendar Pre-News Trading: genera estrategias 30 min antes de datos High Impact
- Break Even automatico: SL se mueve a entry cuando precio alcanza 1:1 R:R
- Dashboard segmentado por tipo: NEWS / ESTRUCTURA / SMC / CALENDARIO / PATRON
- Base de conocimiento profesional: VWAP, Order Flow, velas, break even, scalping EUR/USD

### v3.0.0 (31 Mar 2026)
- SL/TP adaptativo por ATR
- Confirmacion de cierre de vela anti-mecha para breakouts
- Confianza dinamica por sesion de trading
- Expiracion adaptativa 15-60 min segun volatilidad
- Gate de spread y resolucion de conflictos entre fuentes
- AutoTuner: optimizador autonomo de parametros
- Smart Money Concepts multi-temporalidad
- Datos persistentes en %APPDATA%/AIdan/

### v2.x (Mar 2026)
- Dashboard multi-tema, tests unitarios, analisis tecnico, chat con IA, estrategias automaticas

### v1.x (Mar 2026)
- Recolector RSS, dashboard basico, alertas, calendario economico

---

## Licencia

MIT - Uso libre.

## Disclaimer

AIdan es una herramienta de asistencia, NO un sistema de trading automatico. Las senales son orientativas y no garantizan resultados. Opera bajo tu propio riesgo y criterio. Nunca arriesgues dinero que no puedas perder.
