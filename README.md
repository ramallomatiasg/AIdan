# AIdan v1.1 - Financial News Analysis System

Sistema inteligente de análisis de noticias financieras enfocado en el par EUR/USD para trading de opciones binarias. Utiliza IA (Claude) para analizar noticias en tiempo real y generar señales de trading.

**Desarrollado por Matias Ramallo**

## 📋 Características

- **Dashboard Retro Terminal**: Interfaz estilo Matrix con efectos CRT
- **Análisis con IA**: Procesamiento con Claude (Anthropic) para evaluar impacto en EUR/USD
- **Señales de Trading**: Recomendaciones CALL/PUT con probabilidad y timeframes (1-5 min)
- **Scoring 0-100**: Sistema de puntuación de impacto en el mercado
- **Alertas en Tiempo Real**: Solo muestra noticias de ALTO impacto (score >= 80)
- **Feeds RSS**: Recolección automática de Bloomberg, Reuters, Financial Times
- **Versión Desktop**: Ejecutable standalone sin necesidad de navegador
- **Timezone Argentina**: Horarios ajustados automáticamente a UTC-3

## 🎯 Uso Principal

Este sistema está diseñado para traders de opciones binarias en el par EUR/USD:

- Monitorea noticias económicas 24/7
- Analiza impacto potencial con IA
- Genera señales direccionales (CALL/PUT)
- Sugiere timeframes óptimos (1-5 minutos)
- Muestra probabilidad de acierto con indicadores visuales 🟢🟡🔴

## 📋 Características Técnicas

- **Collector**: Fetch automático de feeds RSS cada 10 minutos
- **Analyzer**: Análisis de impacto con Claude AI y scoring 0-100
- **Admin API**: Dashboard REST con FastAPI en puerto 8000
- **Database**: SQLite para persistencia de noticias y alertas
- **Data Cleanup**: Limpieza automática de datos antiguos (72h)

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────┐
│     Collector (cada 10 min)             │
│   - Fetch RSS feeds (Bloomberg, etc)    │
│   - Normalizar noticias                 │
│   - Detectar idioma                     │
│   - Guardar a BD                        │
└──────────────────┬──────────────────────┘
                   │
┌─────────────────────────────────────────┐
│     Analyzer (cada 2 min)               │
│   - Analizar con Claude AI              │
│   - Calcular impacto EUR/USD (0-100)    │
│   - Generar señales CALL/PUT            │
│   - Determinar probabilidad             │
└──────────────────┬──────────────────────┘
                   │
┌─────────────────────────────────────────┐
│     Admin API (FastAPI :8000)           │
│   - Dashboard Retro Terminal            │
│   - /stats (estadísticas)               │
│   - /recent-alerts (solo ALTA)          │
│   - /about (perfil desarrollador)       │
└─────────────────────────────────────────┘
```

## 📁 Estructura del Proyecto

```
AIdan/
├── src/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── config.py          # Config general (env vars)
│   │   ├── logging_setup.py   # Logging con JSON
│   │   └── db.py              # SQLite utilities
│   ├── collector/
│   │   ├── __init__.py
│   │   ├── feed_fetcher.py    # Fetch + parseo de RSS
│   │   └── main.py            # Loop principal del collector
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── news_analyzer.py   # Cálculo de impacto
│   │   └── main.py            # Loop principal del analyzer
│   └── admin/
│       ├── __init__.py
│       └── main.py            # API FastAPI
├── config/
│   └── sources.yaml           # Lista de feeds RSS
├── scripts/
│   ├── run_collector.bat/.sh
│   ├── run_analyzer.bat/.sh
│   └── run_admin.bat/.sh
├── data/                      # JSONL files por hora (YYYY/MM/DD/HH/news.jsonl)
├── state/                     # SQLite database
├── requirements.txt
├── .env.example
├── docker-compose.yml
├── Dockerfile                 # Admin service
└── README.md
```

## 🚀 Instalación y Ejecución

### Opción 1: Versión Desktop (Recomendada) 💻

La forma más sencilla de usar AIdan es con la **versión desktop standalone**:

#### 1. Descargar el ejecutable
- Descarga **AIdan_Desktop.exe** desde [Releases](https://github.com/ramallomatiasg/AIdan/releases)
- Descarga también las carpetas **config/** y **static/**

#### 2. Configurar variables de entorno
- Crea un archivo `.env` en la misma carpeta del ejecutable con:
```
ANTHROPIC_API_KEY=tu_api_key_aqui
```

#### 3. Ejecutar
- Doble click en **AIdan_Desktop.exe** o ejecuta `start_desktop.bat`
- Se abrirá una ventana nativa con el dashboard
- **No requiere navegador ni instalación de Python**

### Opción 2: Con Python local

#### 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

#### 2. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con tu ANTHROPIC_API_KEY
```

#### 3. Iniciar sistema
```bash
# Windows
start_system.bat

# Linux/Mac
./start_system.sh
```

Esto inicia los 3 servicios automáticamente. Luego accede a: http://localhost:8000

### Opción 3: Con Docker Compose

```bash
docker compose up --build
```

Acceder a: http://localhost:8000/docs

### Opción 4: Compilar tu propia versión

```bash
# Instalar PyInstaller
pip install pyinstaller

# Compilar todos los ejecutables
build_exe.bat  # Windows
./build_exe.sh # Linux/Mac
```

Esto genera en `dist/`:
- **AIdan_Desktop.exe** - Versión todo-en-uno (recomendada)
- AIdan_Admin.exe - Solo API/Dashboard
- AIdan_Collector.exe - Solo recolector
- AIdan_Analyzer.exe - Solo analizador

## ⚙️ Configuración

### .env
```
ANTHROPIC_API_KEY=tu_api_key_de_claude_aqui
COLLECTOR_INTERVAL=600          # 10 minutos
ANALYZER_INTERVAL=120           # 2 minutos
DATA_RETENTION_HOURS=72
LOG_LEVEL=INFO
```

### config/sources.yaml
```yaml
sources:
  - name: "Financial Times"
    url: "https://feeds.ft.com/markets"
  - name: "Reuters"
    url: "https://feeds.reuters.com/reuters/businessNews"
  # ... más fuentes
```

## 📊 API Endpoints

### Health Check
```bash
GET /health
```

Respuesta:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-25T10:30:00"
}
```

### Estadísticas
```bash
GET /stats
```

Respuesta:
```json
{
  "status": "success",
  "data": {
    "total_news": 1250,
    "total_alerts": 45,
    "news_last_hour": 12
  }
}
```

### Alertas Recientes
```bash
GET /recent-alerts?limit=50
```

Respuesta:
```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "id": 42,
      "impact_score": 88,
      "sent_at": "2026-02-25T10:15:00",
      "title": "Federal Reserve Raises Interest Rates...",
      "url": "https://...",
      "level": "ALTA"
    }
  ]
}
```

### Noticias Recientes
```bash
GET /recent-news?limit=200
```

## 📈 Lógica de Scoring

El analyzer usa Claude AI para evaluar el impacto de cada noticia en EUR/USD (0-100):

**Niveles de Alerta:**
- **🔴 ALTA**: score ≥ 80 (se muestra en dashboard)
- **🟡 MEDIA**: 67 ≤ score < 80
- **🟢 BAJA**: score < 67 (no se muestra)

**Señales de Trading:**
- **CALL**: Se recomienda compra (expectativa alcista EUR/USD)
- **PUT**: Se recomienda venta (expectativa bajista EUR/USD)
- **Probabilidad**: Indicador visual 🟢 (alta), 🟡 (media), 🔴 (baja)
- **Timeframe**: Duración sugerida del trade (1-5 minutos)

## ⚠️ Advertencia Importante

Este sistema es una herramienta de análisis informativo. **NO ES ASESORAMIENTO FINANCIERO**:

- Las señales son generadas por IA y pueden ser incorrectas
- El trading de opciones binarias conlleva alto riesgo
- Siempre realiza tu propio análisis antes de operar
- Nunca inviertas más de lo que puedas permitirte perder
- Consulta con asesores financieros certificados

## 🔧 Desarrollo y Personalización

### Estructura de módulos

**common/config.py**: Configuración centralizada desde variables de entorno.

**common/db.py**: Operaciones SQLite (news, alerts, errors tables).

**collector/feed_fetcher.py**: Descarga RSS con feedparser + parsing HTML con BeautifulSoup.

**analyzer/news_analyzer.py**: Scoring, detección de entidades, generación de resúmenes.

**admin/main.py**: API REST con FastAPI para el dashboard.

### Extensiones futuras

- [ ] Análisis de múltiples pares de divisas
- [ ] Integración con brokers de opciones binarias
- [ ] Backtesting de señales históricas
- [ ] Machine Learning para mejorar precisión
- [ ] Alertas por email/Telegram
- [ ] Dashboard móvil responsive
- [ ] API para bots de trading automatizado
- [ ] Análisis de volumen y volatilidad

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo Licencia MIT. Ver archivo [LICENSE](LICENSE) para más detalles.

## 👨‍💻 Autor

**Matias Ramallo**
- Ingeniero Desarrollador de Software
- GitHub: [@ramallomatiasg](https://github.com/ramallomatiasg)
- LinkedIn: [Matias Ramallo](https://www.linkedin.com/in/ramallomatiasg/)

## 📞 Soporte

Si encuentras algún problema o tienes preguntas:
- Abre un [Issue](https://github.com/ramallomatiasg/AIdan/issues)
- Contacta vía LinkedIn

---

⭐ Si este proyecto te resulta útil, considera darle una estrella en GitHub!

## 📝 Logging

Todos los componentes usan logging estructurado en JSON:

```json
{
  "timestamp": "2026-02-25T10:30:00.123456",
  "level": "INFO",
  "logger": "collector.main",
  "message": "Fetched 5 news items"
}
```

## 🐛 Troubleshooting

### Port 8000 ya está en uso
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :8000
kill -9 <PID>
```

### Database locked
```bash
rm state/financial_news.db
# Se recrea automáticamente
```

### Feeds no se cargan
- Revisar archivo `config/sources.yaml`
- Verificar conexión a internet
- Chequear logs en `state/`

## 📄 Licencia

MIT License

## 👨‍💻 Autor

Creado como demostración de agente de monitoreo de noticias financieras con Python.

---

**Nota**: Este proyecto es una demostración educativa. Para uso en producción, se recomiendan mejoras en seguridad, escalabilidad y manejo de errores.
   ```bash
   docker-compose down
   ```

## Testing

To run tests, you can use pytest:
```bash
pytest
```

## Usage
- The collector runs every 10 minutes.
- The analyzer runs every 2 minutes or when new files are detected.
- The janitor cleans up old data every hour.

## Endpoints
- `/health`: Check service health.
- `/stats`: Get statistics on news and alerts.
- `/recent-alerts`: Get the latest alerts.
- `/recent-news`: Get the latest news items.

## Logging
Structured logging in JSON format is implemented throughout the services.

## Contributing
Feel free to submit issues and pull requests!