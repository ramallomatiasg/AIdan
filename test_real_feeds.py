"""
Script de prueba para verificar que los feeds RSS funcionan
Ejecutar: python test_real_feeds.py
"""

def test_feeds_simple():
    """Test simplificado sin dependencias complejas"""
    import urllib.request
    import json
    from datetime import datetime
    
    print("=" * 70)
    print("🔥 PROBANDO FEEDS RSS REALES DE NOTICIAS FINANCIERAS")
    print("=" * 70)
    
    # Fuentes de feeds RSS reales
    feeds = [
        {
            "name": "Reuters Business",
            "url": "https://feeds.reuters.com/reuters/businessNews",
            "format": "rss"
        },
        {
            "name": "MarketWatch",
            "url": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
            "format": "rss"
        },
        {
            "name": "Financial Times",
            "url": "https://www.ft.com/markets?format=rss",
            "format": "rss"
        }
    ]
    
    print(f"\n📡 Intentando conectar a {len(feeds)} fuentes RSS...\n")
    
    successful = 0
    failed = 0
    
    for feed in feeds:
        try:
            print(f"Conectando a: {feed['name']}")
            print(f"URL: {feed['url']}")
            
            # Hacer request HTTP simple
            req = urllib.request.Request(
                feed['url'],
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                
                # Verificar que es XML/RSS
                if b'<rss' in data[:500] or b'<feed' in data[:500]:
                    print(f"✅ ÉXITO - Feed RSS válido ({len(data)} bytes)")
                    successful += 1
                    
                    # Mostrar primeros caracteres
                    preview = data[:200].decode('utf-8', errors='ignore')
                    print(f"   Preview: {preview[:100]}...")
                else:
                    print(f"⚠️  Respuesta recibida pero no parece RSS")
                    failed += 1
                    
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            failed += 1
        
        print("-" * 70)
    
    print(f"\n📊 RESUMEN:")
    print(f"   ✅ Exitosos: {successful}/{len(feeds)}")
    print(f"   ❌ Fallidos:  {failed}/{len(feeds)}")
    print(f"\n💡 Para procesar y analizar estas noticias, ejecuta:")
    print(f"   python src/collector/main.py")
    print("=" * 70)

def test_feeds_with_feedparser():
    """Test completo con feedparser si está disponible"""
    try:
        import feedparser
        from datetime import datetime
        
        print("\n" + "=" * 70)
        print("🚀 TEST COMPLETO CON FEEDPARSER")
        print("=" * 70)
        
        feeds = [
            "https://feeds.reuters.com/reuters/businessNews",
            "https://feeds.marketwatch.com/marketwatch/marketpulse/"
        ]
        
        for feed_url in feeds:
            print(f"\n📰 Parseando: {feed_url}")
            feed = feedparser.parse(feed_url)
            
            if feed.entries:
                print(f"✅ {len(feed.entries)} noticias encontradas\n")
                
                # Mostrar las 3 más recientes
                for i, entry in enumerate(feed.entries[:3], 1):
                    title = entry.get('title', 'Sin título')
                    link = entry.get('link', '')
                    published = entry.get('published', 'Fecha desconocida')
                    
                    print(f"  [{i}] {title}")
                    print(f"      📅 {published}")
                    print(f"      🔗 {link[:60]}...")
                    print()
            else:
                print(f"❌ No se pudieron obtener noticias")
            
            print("-" * 70)
            
    except ImportError:
        print("\n⚠️  feedparser no está instalado")
        print("   Instalar con: pip install feedparser")

if __name__ == "__main__":
    print("\n🔍 TEST DE FEEDS RSS - Financial News Monitor\n")
    
    # Test básico (funciona sin dependencias extra)
    test_feeds_simple()
    
    # Test avanzado (requiere feedparser)
    print("\n")
    test_feeds_with_feedparser()
