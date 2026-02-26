#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('state/financial_news.db')
cursor = conn.cursor()

cursor.execute('SELECT count(*) FROM alerts')
alert_count = cursor.fetchone()[0]
print(f'Total alerts in DB: {alert_count}')

cursor.execute("""
    SELECT id, impact_score, alert_level, 
           CAST(LENGTH(explanation) AS INTEGER) as exp_len,
           CAST(LENGTH(eur_usd_impact) AS INTEGER) as eur_len,
           CAST(LENGTH(market_implications) AS INTEGER) as mkt_len
    FROM alerts 
    LIMIT 3
""")

for row in cursor.fetchall():
    print(f'Alert {row[0]}: Score={row[1]}, Level={row[2]}, Explanation_chars={row[3]}, EUR_chars={row[4]}, Market_chars={row[5]}')

# Show one full alert
print("\n--- First Alert Details ---")
cursor.execute("""
    SELECT title, explanation, eur_usd_impact, market_implications
    FROM alerts a
    JOIN news n ON a.news_id = n.id
    LIMIT 1
""")
row = cursor.fetchone()
if row:
    print(f"Title: {row[0]}")
    print(f"\nExplanation:\n{row[1]}")
    print(f"\nEUR/USD Impact:\n{row[2]}")
    print(f"\nMarket Implications:\n{row[3]}")

conn.close()
