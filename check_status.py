import sqlite3

conn = sqlite3.connect('state/financial_news.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM news')
news_count = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM alerts WHERE alert_level="ALTA"')
alert_count = cursor.fetchone()[0]

print(f'\n📊 Estado del Sistema:')
print(f'   📰 Noticias: {news_count}')
print(f'   🚨 Alertas ALTA: {alert_count}')

if alert_count > 0:
    print(f'\n✅ Alertas con nuevo análisis EUR/USD:')
    cursor.execute('''
        SELECT n.title, a.eur_usd_impact, a.market_implications 
        FROM alerts a
        JOIN news n ON a.news_id = n.id
        WHERE a.alert_level="ALTA"
        LIMIT 2
    ''')
    
    for idx, (title, eur_impact, market_impl) in enumerate(cursor.fetchall(), 1):
        print(f'\n   {idx}. {title[:60]}...')
        print(f'\n   💱 {eur_impact[:100]}...')
        print(f'\n   📊 {market_impl[:100]}...')

conn.close()
