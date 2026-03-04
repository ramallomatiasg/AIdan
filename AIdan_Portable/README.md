# 💱 AIdan v1.2 - Sistema de Trading EUR/USD con IA (100% Portable)

Sistema automatizado que monitorea noticias financieras 24/7 y genera señales de trading para EUR/USD utilizando análisis de IA local.

**❗ Versión 1.2 - Ahora completamente portable, NO requiere Python instalado**

## 🎯 Características

- **Monitoreo 24/7** de Bloomberg, Reuters, Financial Times, etc.
- **Análisis con IA** (Ollama/Llama 3.1) de cada noticia
- **Señales claras**: CALL / PUT / NO OPERAR
- **Dashboard en tiempo real** con alertas
- **Chat con IA** para consultar estrategias
- **100% local y gratuito** (sin APIs pagas)

## 🚀 Instalación Rápida

### ✅ Opción 1: Ejecutable Portable (Recomendado)

1. Descarga y descomprime `AIdan_Portable.zip`
2. Doble click en `AIdan_Launcher.exe`
3. ¡Listo!

**Ventajas:**
- ✅ NO necesita Python instalado
- ✅ 100% portable
- ✅ Incluye 4 ejecutables optimizados
- ✅ Instalación automática de Ollama

### Opción 2: Desarrollo (Requiere Python)

```powershell
# 1. Clonar repositorio
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan

# 2. Instalar Ollama
# Descargar: https://ollama.com/download/windows
ollama pull llama3.1:8b

# 3. Instalar dependencias Python
pip install -r requirements.txt

# 4. Iniciar en modo desarrollo
python AIdan_Launcher.py
```

## 📦 Distribución

Para crear un paquete portable listo para compartir:

```powershell
# Compilar todos los ejecutables
.\build_exe.bat

# Crear paquete portable
.\crear_paquete.bat
```

Esto genera `AIdan_Portable.zip` con todo lo necesario:

```
AIdan_Portable/
├── AIdan_Launcher.exe   ⭐ Maestro (inicia todo)
├── AIdan_Collector.exe  📰 Recolector de noticias
├── AIdan_Analyzer.exe   🤖 Analizador con IA
├── AIdan_API.exe        🌐 Servidor dashboard
├── config/
│   └── sources.yaml
├── static/              (recursos visuales)
├── dashboard_*.html     (páginas web)
└── LEEME.txt
```

**Para compartir:** Solo envía el .zip - NO necesita Python instalado.

## 🛠️ Desarrollo

```powershell
# Estructura del proyecto
src/
├── collector/    # Recolección RSS (AIdan_Collector.exe)
├── analyzer/     # Análisis con IA (AIdan_Analyzer.exe)
├── admin/        # API + Dashboard (AIdan_API.exe)
└── common/       # Utilidades compartidas

# Compilar ejecutables individuales
pyinstaller AIdan_Collector.spec
pyinstaller AIdan_Analyzer.spec
pyinstaller AIdan_API.spec
pyinstaller AIdan_Launcher.spec

# O compilar todos
.\build_exe.bat
```

## 📊 Arquitectura

- **4 Ejecutables independientes** que se comunican entre sí
- **AIdan_Launcher.exe**: Orquestador maestro, gestiona Ollama y lanza servicios
- **AIdan_Collector.exe**: Descarga y procesa noticias RSS cada 10 min
- **AIdan_Analyzer.exe**: Analiza noticias con Ollama (IA local)
- **AIdan_API.exe**: Servidor FastAPI + dashboard web (puerto 8000)

## 📝 Licencia

Ver [LICENSE](LICENSE)

## 👤 Autor

Matias Ramallo
