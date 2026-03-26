import feedparser
import json
from datetime import datetime
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException
import os

class FeedFetcher:
    def __init__(self, logger):
        self.logger = logger
        self.timeout = 10
        
    def fetch_feeds(self, sources):
        """Fetch and parse feeds from all sources"""
        news_items = []
        
        for source in sources:
            self.logger.info(f"Fetching from {source['name']}")
            try:
                # feedparser.parse no soporta timeout como parámetro directo
                # pero sí puede manejar URLs normalmente
                feed = feedparser.parse(source['url'])
                
                for entry in feed.entries[:5]:  # Get last 5 entries
                    news = self._extract_news(entry, source['name'])
                    if news:
                        news_items.append(news)
            except Exception as e:
                self.logger.error(f"Error fetching {source['name']}: {str(e)}")
        
        return news_items
    
    def _extract_news(self, entry, source_name):
        """Extract and normalize news from feed entry"""
        try:
            title = entry.get('title', 'No title')
            link = entry.get('link', '')
            
            # Get summary or description
            summary = entry.get('summary', entry.get('description', ''))
            summary = self._clean_html(summary)[:500]  # Max 500 chars
            
            # Detect language
            try:
                language = detect(title + ' ' + summary)
            except LangDetectException:
                language = 'unknown'
            
            # Extract entities (simple pattern matching)
            entities = self._extract_entities(title + ' ' + summary)
            
            # Extract tags
            tags = self._extract_tags(title + ' ' + summary)
            
            # Extract publication date from feed entry
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    from calendar import timegm
                    published_at = datetime.utcfromtimestamp(timegm(entry.published_parsed)).isoformat()
                except Exception:
                    pass
            if not published_at and entry.get('published'):
                published_at = str(entry.get('published'))[:25]
            if not published_at and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                try:
                    from calendar import timegm
                    published_at = datetime.utcfromtimestamp(timegm(entry.updated_parsed)).isoformat()
                except Exception:
                    pass

            return {
                'url': link,
                'title': title,
                'summary': summary,
                'language': language,
                'source': source_name,
                'entities': entities,
                'tags': tags,
                'published_at': published_at,
                'fetched_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error extracting news: {str(e)}")
            return None
    
    def _clean_html(self, text):
        """Remove HTML tags from text"""
        if not text:
            return ""
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    
    def _extract_entities(self, text):
        """Extract financial entities from text"""
        entities = []
        keywords = {
            'FED': ['fed', 'federal reserve'],
            'ECB': ['ecb', 'european central bank'],
            'BOE': ['bank of england', 'boe'],
            'Powell': ['powell'],
            'CPI': ['cpi', 'consumer price index'],
            'GDP': ['gdp', 'gross domestic product'],
            'S&P500': ['s&p 500', 'sp 500'],
            'Nasdaq': ['nasdaq'],
            'DOW': ['dow jones', 'dow'],
        }
        
        text_lower = text.lower()
        for entity, patterns in keywords.items():
            for pattern in patterns:
                if pattern in text_lower:
                    entities.append(entity)
                    break
        
        return list(set(entities))
    
    def _extract_tags(self, text):
        """Extract topic tags from text"""
        tags = []
        topic_patterns = {
            'monetary_policy': ['interest rate', 'fed', 'central bank', 'inflation'],
            'market_volatility': ['volatility', 'crash', 'surge', 'plunge'],
            'earnings': ['earnings', 'profit', 'revenue', 'loss'],
            'merger': ['merger', 'acquisition', 'takeover', 'deal'],
            'crypto': ['bitcoin', 'ethereum', 'crypto', 'blockchain'],
            'tech': ['tech', 'ai', 'software', 'semiconductor'],
            'energy': ['oil', 'gas', 'energy', 'renewable'],
            'geopolitics': ['war', 'sanctions', 'trade war', 'tariff'],
        }
        
        text_lower = text.lower()
        for tag, patterns in topic_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    tags.append(tag)
                    break
        
        return list(set(tags))

    def save_to_file(self, news_items):
        """Save news to JSONL file organized by date"""
        if not news_items:
            return
        
        now = datetime.utcnow()
        data_dir = f"data/{now.year}/{now.month:02d}/{now.day:02d}/{now.hour:02d}"
        os.makedirs(data_dir, exist_ok=True)
        
        file_path = f"{data_dir}/news.jsonl"
        
        with open(file_path, 'a') as f:
            for item in news_items:
                f.write(json.dumps(item) + '\n')
        
        self.logger.info(f"Saved {len(news_items)} items to {file_path}")
