════════════════════════════════════════════════════════════════════════════════
  📦 FINANCIAL NEWS MONITOR - VERSIÓN PORTABLE
  💱 Sistema de Señales para Trading Binario EUR/USD
════════════════════════════════════════════════════════════════════════════════

📋 CONTENIDO DEL PAQUETE:

  dist/
    ├── AIdan_Admin.exe       (Dashboard Web - Puerto 8000)
    ├── AIdan_Collector.exe   (Recolector de Noticias RSS)
    └── AIdan_Analyzer.exe    (Analizador EUR/USD)

  config/
    └── sources.yaml          (Fuentes RSS de noticias financieras)

  start_system_portable.bat   (⭐ EJECUTAR ESTE ARCHIVO)
  stop_system_portable.bat    (Detener el sistema)
  dashboard.html              (Interfaz web del dashboard)


🚀 CÓMO USAR:

  1. Haz doble clic en "start_system_portable.bat"
  2. Espera a que se abra el navegador automáticamente
  3. Verás el dashboard en http://localhost:8000


📊 QUÉ HACE EL SISTEMA:

  ✅ Recolecta noticias financieras cada 10 minutos de fuentes RSS
  ✅ Analiza el impacto de cada noticia en el par EUR/USD
  ✅ Genera señales CALL (Compra) o PUT (Venta) para trading binario
  ✅ Muestra probabilidades tipo semáforo (🟢🟡🔴)
  ✅ Orientado a operaciones de 1-5 minutos en horario NY


⚙️ CONFIGURACIÓN (OPCIONAL):

  Si quieres cambiar las fuentes de noticias:
    → Edita config/sources.yaml
    → Agrega o quita URLs de feeds RSS


⚠️ REQUISITOS:

  ✅ Windows 10/11
  ✅ Conexión a Internet
  ✅ Puerto 8000 disponible
  ❌ NO requiere Python instalado


🛑 DETENER EL SISTEMA:

  Opción 1: Ejecuta "stop_system_portable.bat"
  Opción 2: Cierra todas las ventanas CMD que se abrieron


📁 ARCHIVOS QUE SE CREAN:

  state/
    └── financial_news.db     (Base de datos SQLite con noticias y alertas)


💡 TIPS PARA TRADING:

  🟢 Verde (BAJO RIESGO)    → No operar, esperar señal clara
  🟡 Amarillo (MEDIO RIESGO) → Precaución, reducir tamaño
  🔴 Rojo (ALTO RIESGO)     → Oportunidad de volatilidad

  📈 CALL (Compra)  → EUR sube contra USD
  📉 PUT (Venta)    → EUR baja contra USD


🌍 HORARIOS:

  ⏰ Todas las horas se muestran en horario de Argentina (UTC-3)
  📊 Mejor momento: Horario NY (9:30-16:00 EST)


❓ SOLUCIÓN DE PROBLEMAS:

  ❌ No se abre el dashboard:
     → Verifica que el puerto 8000 esté libre
     → Revisa si Windows Firewall está bloqueando

  ❌ No aparecen noticias:
     → Espera 10 minutos (tiempo de primer ciclo)
     → Verifica conexión a Internet

  ❌ Error al iniciar:
     → Ejecuta stop_system_portable.bat primero
     → Vuelve a iniciar con start_system_portable.bat


📧 SOPORTE:

  Este sistema es una herramienta de análisis de noticias.
  NO es asesoramiento financiero.
  Opera bajo tu propio riesgo.


════════════════════════════════════════════════════════════════════════════════
  Versión: 1.0 Portable | Fecha: Febrero 2026
════════════════════════════════════════════════════════════════════════════════
