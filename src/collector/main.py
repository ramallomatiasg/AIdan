import time
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.common.config import Config
from src.common.logging_setup import setup_logging
from src.common.db import init_db, add_news
from src.collector.feed_fetcher import FeedFetcher

logger = setup_logging(__name__, Config.LOG_LEVEL)

def run_collector():
    """Main collector loop"""
    logger.info("Initializing collector...")
    init_db()
    
    fetcher = FeedFetcher(logger)
    
    # Default sources if config file doesn't exist.
    # v3.61.0: FT y Reuters devuelven 0 entries desde hace meses (medido 26-ago),
    # asi que el fallback ya no las incluye: un default con fuentes muertas hacia
    # que "5 fuentes configuradas" fuera 1 fuente real.
    default_sources = [
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss"},
    ]
    
    sources = Config.get_sources() or default_sources
    
    logger.info(f"Starting collector with {len(sources)} sources")
    
    iteration = 0
    while True:
        try:
            iteration += 1
            logger.info(f"[Iteration {iteration}] Fetching news...")
            
            news_items = fetcher.fetch_feeds(sources)
            logger.info(f"Fetched {len(news_items)} news items")
            
            # Save to files
            fetcher.save_to_file(news_items)
            
            # Save to database
            added = 0
            for item in news_items:
                result = add_news(
                    url=item['url'],
                    title=item['title'],
                    summary=item['summary'],
                    language=item['language'],
                    entities=str(item['entities']),
                    tags=str(item['tags'])
                )
                if result:
                    added += 1
            
            logger.info(f"Added {added} new items to database")
            
        except Exception as e:
            logger.error(f"Error in collector loop: {str(e)}")
        
        logger.info(f"Sleeping for {Config.COLLECTOR_INTERVAL} seconds...")
        time.sleep(Config.COLLECTOR_INTERVAL)

if __name__ == "__main__":
    run_collector()
