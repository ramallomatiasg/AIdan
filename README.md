# 💱 AIdan v1.1 - Sistema de Trading EUR/USD con IA

Sistema automatizado que monitorea noticias financieras 24/7 y genera señales de trading para EUR/USD utilizando análisis de IA local.

## 🎯 Características

- **Monitoreo 24/7** de Bloomberg, Reuters, Financial Times, etc.
- **Análisis con IA** (Ollama/Llama 3.1) de cada noticia
- **Señales claras**: CALL / PUT / NO OPERAR
- **Dashboard en tiempo real** con alertas
- **Chat con IA** para consultar estrategias
- **100% local y gratuito** (sin APIs pagas)

## 🚀 Instalación Rápida

### Opción 1: Ejecutable (Más fácil)

1. Descarga `AIdan_Launcher.exe` de la carpeta `dist/`
2. Doble click - ¡listo!

El ejecutable verificará e instalará Ollama automáticamente si no lo tenés.

### Opción 2: Desde código

```powershell
# 1. Instalar Ollama
# Descargar: https://ollama.com/download/windows
ollama pull llama3.1:8b

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar sistema
.\start_system.bat
```

## 📦 Para Compartir

Solo se necesita estos archivos:

```
AIdan/
├── AIdan_Launcher.exe  ⭐ (ejecutable principal)
├── config/
│   └── sources.yaml
├── static/             (imágenes/gifs)
└── LEEME.txt
```

**NO necesita Python** instalado.
**SÍ necesita Ollama** (el launcher lo instala automáticamente).

## 🛠️ Desarrollo

```powershell
# Compilar ejecutable
.\build_exe.bat

# Estructura del proyecto
src/
├── collector/    # Recolección RSS
├── analyzer/     # Análisis con IA
├── admin/        # API + Dashboard
└── common/       # Utilidades compartidas
```

## 📝 Licencia

Ver [LICENSE](LICENSE)

## 👤 Autor

Matias Ramallo
