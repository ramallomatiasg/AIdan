import time
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.common.config import Config
from src.common.logging_setup import setup_logging
from src.common.db import init_db, get_unprocessed_news, mark_news_processed, add_alert
from src.analyzer.news_analyzer import NewsAnalyzer

logger = setup_logging(__name__, Config.LOG_LEVEL)

def run_analyzer():
    """Main analyzer loop"""
    logger.info("Initializing analyzer...")
    init_db()
    
    analyzer = NewsAnalyzer(logger)
    
    logger.info("Starting analyzer")
    
    iteration = 0
    while True:
        try:
            iteration += 1
            logger.info(f"[Iteration {iteration}] Checking for unprocessed news...")
            
            news_items = get_unprocessed_news()
            logger.info(f"Found {len(news_items)} unprocessed news items")
            
            alerts_sent = 0
            for news_id, url, title, summary, entities, tags in news_items:
                # Analyze
                result = analyzer.analyze(news_id, title, summary, entities, tags)
                
                if result and result['should_alert']:
                    logger.info(f"[{result['level']}] Alert for: {title[:50]}")
                    
                    # Record alert with detailed information
                    add_alert(
                        news_id=news_id,
                        impact_score=result['impact_score'],
                        alert_level=result['level'],
                        explanation=result['explanation'],
                        eur_usd_impact=result['eur_usd_impact'],
                        market_implications=result['market_implications']
                    )
                    alerts_sent += 1
                
                # Mark as processed
                mark_news_processed(news_id)
            
            logger.info(f"Sent {alerts_sent} alerts in this iteration")
            
        except Exception as e:
            logger.error(f"Error in analyzer loop: {str(e)}")
        
        logger.info(f"Sleeping for {Config.ANALYZER_INTERVAL} seconds...")
        time.sleep(Config.ANALYZER_INTERVAL)

if __name__ == "__main__":
    run_analyzer()
