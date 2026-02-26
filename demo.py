"""
Demo script to test the Financial News Monitor locally
"""
import sys
import os
import json
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.common.logging_setup import setup_logging
from src.common.db import init_db, add_news, get_unprocessed_news, add_alert
from src.collector.feed_fetcher import FeedFetcher
from src.analyzer.news_analyzer import NewsAnalyzer

logger = setup_logging(__name__, "INFO")

def demo():
    """Run a quick demo of the system"""
    logger.info("=" * 60)
    logger.info("FINANCIAL NEWS MONITOR - DEMO")
    logger.info("=" * 60)
    
    # Initialize database
    logger.info("\n[1] Initializing database...")
    init_db()
    logger.info("✓ Database initialized")
    
    # Create sample data
    logger.info("\n[2] Creating sample news data...")
    sample_news = [
        {
            "url": "https://example.com/fed-raises-rates",
            "title": "Federal Reserve Raises Interest Rates Unexpectedly",
            "summary": "In a surprise move, the Federal Reserve announced a 0.75% interest rate increase.",
            "language": "en",
            "entities": "['FED', 'Powell']",
            "tags": "['monetary_policy', 'inflation']"
        },
        {
            "url": "https://example.com/tesla-earnings",
            "title": "Tesla Q4 Earnings Beat Expectations",
            "summary": "Tesla reported record quarterly earnings with strong guidance for 2026.",
            "language": "en",
            "entities": "['Tesla']",
            "tags": "['earnings', 'tech']"
        },
        {
            "url": "https://example.com/crypto-surge",
            "title": "Bitcoin Surges to New All-Time High",
            "summary": "Cryptocurrency market experiences explosive growth as institutional investors join.",
            "language": "en",
            "entities": "['Bitcoin']",
            "tags": "['crypto', 'market_volatility']"
        }
    ]
    
    news_ids = []
    for news in sample_news:
        news_id = add_news(**news)
        if news_id:
            news_ids.append(news_id)
            logger.info(f"✓ Added: {news['title'][:50]}")
    
    # Analyze news
    logger.info("\n[3] Analyzing news for impact...")
    analyzer = NewsAnalyzer(logger)
    
    unprocessed = get_unprocessed_news()
    for news_id, url, title, summary, entities, tags in unprocessed:
        result = analyzer.analyze(news_id, title, summary, entities, tags)
        
        if result:
            logger.info(f"\nNews: {title[:60]}")
            logger.info(f"  Impact Score: {result['impact_score']}/100")
            logger.info(f"  Level: {result['level']}")
            logger.info(f"  Should Alert: {result['should_alert']}")
            
            if result['should_alert']:
                add_alert(news_id, result['impact_score'])
                logger.info(f"  ⚠️  ALERT SENT")
    
    # Show dashboard stats
    logger.info("\n[4] Dashboard Statistics")
    logger.info("=" * 60)
    
    from src.common.db import get_stats, get_recent_alerts
    
    stats = get_stats()
    logger.info(f"Total News Items: {stats['total_news']}")
    logger.info(f"Total Alerts Sent: {stats['total_alerts']}")
    logger.info(f"News in Last Hour: {stats['news_last_hour']}")
    
    recent_alerts = get_recent_alerts(5)
    if recent_alerts:
        logger.info(f"\nRecent Alerts ({len(recent_alerts)}):")
        for alert_id, score, sent_at, title, url in recent_alerts:
            level = "ALTA" if score >= 80 else ("MEDIA" if score >= 50 else "BAJA")
            logger.info(f"  [{level}] {title[:50]} (Score: {score})")
    
    logger.info("\n" + "=" * 60)
    logger.info("Demo completed!")
    logger.info("=" * 60)
    
    print("\n📊 To view the API dashboard, run:")
    print("   python src\\admin\\main.py")
    print("\n   Then visit: http://localhost:8000/docs")

if __name__ == "__main__":
    demo()
