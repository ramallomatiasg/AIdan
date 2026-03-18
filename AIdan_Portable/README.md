# 💱 AIdan v1.2 - Sistema de Trading EUR/USD con IA (100% Portable)

Sistema automatizado que monitorea noticias financieras 24/7 y genera señales de trading para EUR/USD utilizando análisis de IA local.

**✅ Completamente portable - Un solo ejecutable de 23MB**

## 🎯 Características

- **Monitoreo 24/7** de Bloomberg, Reuters, Financial Times, etc.
- **Análisis con IA** (Ollama/Llama 3.1) de cada noticia
- **Señales claras**: CALL / PUT / NO OPERAR
- **Dashboard en tiempo real** con alertas
- **Chat con IA** para consultar estrategias
- **100% local y gratuito** (sin APIs pagas)

## 🚀 Instalación Rápida

### ✅ Para Usuarios (Ejecutable Portable)

1. Descarga `AIdan_Portable.zip` de [Releases](https://github.com/ramallomatiasg/AIdan/releases)
2. Descomprime el archivo
3. Ejecuta `AIdan.exe`
4. ¡Listo! El sistema se encarga de todo automáticamente

**Requisitos:**
- Windows 10/11
- Ollama se instala automáticamente si no lo tenés

### 🛠️ Para Desarrolladores (Desde Código)

```powershell
# 1. Clonar repositorio
git clone https://github.com/ramallomatiasg/AIdan.git
cd AIdan

# 2. Instalar Ollama
# Descargar: hdependencias Python
pip install -r requirements.txt

# 3. Instalar Ollama
# Descargar: https://ollama.com/download/windows
ollama pull llama3.1:8b

# 4. Ejecutar (modo desarrollo)
python AIdan_TodoEnUno.py
```

## 📦 Crear Ejecutable Portable

```powershell
# Compilar ejecutable
pyinstaller AIdan_TodoEnUno.spec --clean

# Crear paquete para distribuir
.\crear_paquete.bat
```

Resultado: `AIdan_Portable.zip` (~24MB) listo para compartir
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
AIdan/
├── AIdan_TodoEnUno.py       # Ejecutable maestro (todo integrado)
├── AIdan_TodoEnUno.spec     # PyInstaller spec
├── crear_paquete.bat        # Script para crear .zip portable
├── requirements.txt         # Dependencias Python
├── config/
│   └── sources.yaml         # Fuentes RSS
├── src/
│   ├── collector/           # Módulo recolector de noticias
│   ├── analyzer/            # Módulo análisis con IA
│   ├── admin/               # Módulo API + Dashboard
│   └── common/              # Utilidades compartidas
└── static/                  # Recursos web
```

## 📊 Arquitectura

**Ejecutable Todo-En-Uno:**
- Un solo archivo `AIdan.exe` (23MB)
- 3 servicios integrados corriendo como threads:
  - **Collector**: Descarga noticias RSS cada 10 minutos
  - **Analyzer**: Analiza con Ollama (IA local)
  - **API**: Servidor FastAPI + dashboard web (puerto 8000)
- Ventana GUI para control y monitoreo