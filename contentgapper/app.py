#!/usr/bin/env python3
"""
Data-Driven Vector SEO Analyzer (Clean Version)
Uses REAL data instead of guesses:
- Reddit discussions (real user questions)
- Search suggestions (actual searches)
- Content depth analysis (competitor weaknesses)
"""

import os
import sys

# Suppress PyTorch warnings at the system level
os.environ['PYTHONWARNINGS'] = 'ignore::UserWarning'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Redirect stderr to suppress torch warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import requests
from bs4 import BeautifulSoup
import json
import time
import re
import os
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Tuple, Optional
import pandas as pd
from dataclasses import dataclass
import streamlit as st
from urllib.parse import quote_plus
import praw
from collections import Counter
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords

# Download required NLTK data with better error handling
import ssl

# Handle SSL issues
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Download NLTK data with multiple fallbacks
def download_nltk_data():
    """Download NLTK data with fallback options"""
    downloads = [
        ('punkt', 'tokenizers/punkt'),
        ('punkt_tab', 'tokenizers/punkt_tab'), 
        ('stopwords', 'corpora/stopwords')
    ]
    
    for name, path in downloads:
        try:
            nltk.data.find(path)
        except LookupError:
            try:
                nltk.download(name, quiet=True)
            except:
                try:
                    # Fallback download
                    nltk.download(name, quiet=False)
                except:
                    # Continue without this resource if absolutely necessary
                    pass

download_nltk_data()

@dataclass
class TopicData:
    text: str
    embedding: np.ndarray
    source: str  # 'reddit', 'search_suggest', 'competitor', 'depth_gap'
    source_url: str
    competitor_id: int
    confidence: float
    word_count: int = 0
    upvotes: int = 0

class DataDrivenSEOAnalyzer:
    def __init__(self, serper_api_key: str, reddit_client_id: str = None, 
                 reddit_client_secret: str = None):
        """Initialize with API keys"""
        self.serper_key = serper_api_key
        
        # Reddit setup (optional)
        self.reddit = None
        if reddit_client_id and reddit_client_secret:
            try:
                self.reddit = praw.Reddit(
                    client_id=reddit_client_id,
                    client_secret=reddit_client_secret,
                    user_agent="SEO_Analyzer_v2.0"
                )
            except Exception as e:
                st.warning(f"Reddit API setup failed: {e}. Continuing without Reddit data.")
        
        # Load embedding model with better error suppression
        if 'embedding_model' not in st.session_state:
            with st.spinner("Loading AI embedding model..."):
                try:
                    # Comprehensive warning suppression
                    import warnings
                    import logging
                    
                    # Suppress all warnings temporarily
                    warnings.filterwarnings("ignore")
                    logging.getLogger().setLevel(logging.ERROR)
                    
                    # Temporarily redirect stderr
                    import sys
                    from io import StringIO
                    old_stderr = sys.stderr
                    sys.stderr = StringIO()
                    
                    try:
                        st.session_state.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                    finally:
                        # Restore stderr
                        sys.stderr = old_stderr
                    
                except Exception as e:
                    st.error(f"Failed to load embedding model: {e}")
                    st.session_state.embedding_model = None
        
        self.embedding_model = st.session_state.embedding_model
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Stop words for content analysis
        # Initialize stop words with fallback
        try:
            self.stop_words = set(stopwords.words('english'))
        except:
            # Fallback stopwords if NLTK fails
            self.stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once'}
    
    def search_competitors(self, keyword: str, num_results: int = 10) -> List[str]:
        """Search for competitor URLs using Serper"""
        url = "https://google.serper.dev/search"
        
        payload = {'q': keyword, 'num': num_results}
        headers = {'X-API-KEY': self.serper_key, 'Content-Type': 'application/json'}
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        results = response.json()
        return [result['link'] for result in results.get('organic', [])]
    
    def get_search_suggestions(self, keyword: str) -> List[TopicData]:
        """Get real search suggestions from Google Autocomplete - NO FALLBACKS"""
        suggestions = []
        
        # Google Autocomplete API - only real data
        base_suggestions = [
            f"{keyword} how to",
            f"{keyword} best",
            f"{keyword} vs",
            f"{keyword} for",
            f"{keyword} guide",
            f"{keyword} problems",
            f"{keyword} reviews",
            f"{keyword} comparison"
        ]
        
        for base in base_suggestions:
            try:
                autocomplete_url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={quote_plus(base)}"
                response = requests.get(autocomplete_url, timeout=5, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if len(data) > 1 and isinstance(data[1], list):
                        for suggestion in data[1][:3]:  # Top 3 per base
                            if (len(suggestion) > 10 and 
                                suggestion.lower() != base.lower() and
                                suggestion not in suggestions):
                                suggestions.append(suggestion)
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                continue  # Just skip if API fails - NO FALLBACKS
        
        # Convert to TopicData objects - ONLY REAL DATA
        topic_data = []
        if suggestions:
            embeddings = self.embedding_model.encode(suggestions)
            
            for suggestion, embedding in zip(suggestions, embeddings):
                topic_data.append(TopicData(
                    text=suggestion,
                    embedding=embedding,
                    source='search_suggest',
                    source_url='google_autocomplete',
                    competitor_id=-1,
                    confidence=0.8
                ))
        
        return topic_data
    
    def mine_reddit_discussions(self, keyword: str, max_posts: int = 30) -> List[TopicData]:
        """Mine Reddit for real user questions - NO FALLBACKS"""
        reddit_topics = []
        
        if not self.reddit:
            st.info("Reddit API not configured. Skipping Reddit mining.")
            return reddit_topics  # Return empty list - NO FALLBACKS
        
        try:
            subreddit = self.reddit.subreddit('all')
            
            # Search for posts containing the keyword
            for submission in subreddit.search(keyword, limit=max_posts, sort='hot'):
                
                # Process the main post title
                title = submission.title.strip()
                if self._is_meaningful_question(title, keyword):
                    reddit_topics.append({
                        'text': title,
                        'upvotes': submission.score,
                        'url': f"https://reddit.com{submission.permalink}"
                    })
                
                # Process selftext if it contains questions
                if submission.selftext and len(submission.selftext) > 50:
                    questions = self._extract_questions(submission.selftext, keyword)
                    for question in questions:
                        reddit_topics.append({
                            'text': question,
                            'upvotes': submission.score,
                            'url': f"https://reddit.com{submission.permalink}"
                        })
            
            # Filter and convert to embeddings - ONLY REAL DATA
            if reddit_topics:
                filtered_topics = self._filter_reddit_topics(reddit_topics, keyword)
                
                if filtered_topics:
                    texts = [topic['text'] for topic in filtered_topics]
                    embeddings = self.embedding_model.encode(texts)
                    
                    topic_data = []
                    for topic, embedding in zip(filtered_topics, embeddings):
                        topic_data.append(TopicData(
                            text=topic['text'],
                            embedding=embedding,
                            source='reddit',
                            source_url=topic['url'],
                            competitor_id=-1,
                            confidence=0.9,
                            upvotes=topic['upvotes']
                        ))
                    
                    return topic_data
        
        except Exception as e:
            st.warning(f"Reddit mining failed: {e}")
        
        return []  # Return empty if no real data found
    
    def _is_meaningful_question(self, text: str, keyword: str) -> bool:
        """Check if text is a meaningful question"""
        text_lower = text.lower()
        keyword_lower = keyword.lower()
        
        # Must contain the keyword (strict requirement)
        if keyword_lower not in text_lower:
            return False
        
        # Filter out garbage patterns
        garbage_patterns = [
            'carrying on here', 'character limit', 'reddit mod',
            r'^(so|and|but|the|a|an)\s', r'^\w{1,2}\s'
        ]
        
        for pattern in garbage_patterns:
            if re.search(pattern, text_lower):
                return False
        
        # Must be long enough
        if len(text.split()) < 4:
            return False
        
        # Should contain question indicators
        indicators = ['how', 'what', 'why', 'where', 'when', 'which', 'best', 'recommend', '?', 'help', 'advice']
        return any(indicator in text_lower for indicator in indicators)
    
    def _extract_questions(self, text: str, keyword: str) -> List[str]:
        """Extract questions from text"""
        questions = []
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences[:5]:  # Check first 5 sentences
            sentence = sentence.strip()
            if (self._is_meaningful_question(sentence, keyword) and 
                20 <= len(sentence) <= 200):
                questions.append(sentence)
        
        return questions[:2]  # Max 2 questions per text
    
    def _filter_reddit_topics(self, topics: List[Dict], keyword: str) -> List[Dict]:
        """Filter and deduplicate Reddit topics"""
        filtered = []
        seen_texts = set()
        
        for topic in topics:
            text = topic['text'].strip()
            text_lower = text.lower()
            
            # Skip duplicates
            if text_lower in seen_texts:
                continue
            
            # Skip non-English (basic check)
            if not any(c.isascii() for c in text):
                continue
            
            seen_texts.add(text_lower)
            filtered.append(topic)
        
        # Sort by upvotes and take top ones
        filtered.sort(key=lambda x: x['upvotes'], reverse=True)
        return filtered[:10]  # Top 10 quality topics
    
    def scrape_competitor_content(self, urls: List[str], progress_bar=None) -> List[TopicData]:
        """Scrape competitor content with proper depth analysis"""
        all_topics = []
        
        for i, url in enumerate(urls):
            if progress_bar:
                progress_bar.progress((i + 1) / len(urls), f"Analyzing competitor {i+1}/{len(urls)}")
            
            try:
                response = requests.get(url, headers=self.headers, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove noise
                for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    element.decompose()
                
                # Get main content
                content = ""
                content_selectors = ['article', 'main', '.content', '#content', '.post-content', '.entry-content']
                
                for selector in content_selectors:
                    elements = soup.select(selector)
                    if elements:
                        content = ' '.join([elem.get_text() for elem in elements])
                        break
                
                if not content:
                    body = soup.find('body')
                    content = body.get_text() if body else ""
                
                content = re.sub(r'\s+', ' ', content).strip()
                
                # Calculate total article word count
                total_words = len([w for w in word_tokenize(content.lower()) 
                                 if w.isalpha() and w not in self.stop_words])
                
                if total_words > 100:
                    # Extract headings for topic analysis
                    headings = []
                    for tag in ['h1', 'h2', 'h3']:
                        for heading in soup.find_all(tag):
                            heading_text = heading.get_text().strip()
                            if 10 <= len(heading_text) <= 100:
                                headings.append(heading_text)
                    
                    # Process headings as topics
                    if headings:
                        embeddings = self.embedding_model.encode(headings[:5])  # Top 5 headings
                        
                        for heading, embedding in zip(headings[:5], embeddings):
                            all_topics.append(TopicData(
                                text=heading,
                                embedding=embedding,
                                source='competitor',
                                source_url=url,
                                competitor_id=i,
                                confidence=0.6,
                                word_count=total_words  # Total article word count
                            ))
                
                time.sleep(1)
                
            except Exception as e:
                st.warning(f"Error analyzing {url}: {str(e)}")
                continue
        
        return all_topics
    
    def analyze_content_depth(self, competitor_topics: List[TopicData]) -> List[TopicData]:
        """Find thin content opportunities with clear, actionable topics"""
        depth_gaps = []
        
        if not competitor_topics:
            return depth_gaps
        
        # Group by URL to get article depths
        url_depths = {}
        url_topics = {}
        
        for topic in competitor_topics:
            url = topic.source_url
            if url not in url_depths:
                url_depths[url] = topic.word_count
                url_topics[url] = topic.text
        
        # Find thin content (less than 1500 words)
        thin_content = {url: words for url, words in url_depths.items() if words < 1500}
        
        if thin_content:
            # Create meaningful depth gap opportunities
            for url, word_count in list(thin_content.items())[:3]:  # Top 3 opportunities
                original_topic = url_topics.get(url, "")
                
                # Extract meaningful topic from the heading
                meaningful_topic = self._extract_meaningful_topic(original_topic, url)
                
                # Create actionable gap description
                gap_text = f"Complete {meaningful_topic} Guide (current best: {word_count} words)"
                gap_embedding = self.embedding_model.encode([gap_text])[0]
                
                depth_gaps.append(TopicData(
                    text=gap_text,
                    embedding=gap_embedding,
                    source='depth_gap',
                    source_url=url,
                    competitor_id=-1,
                    confidence=0.8,
                    word_count=word_count
                ))
        
        return depth_gaps
    
    def _extract_meaningful_topic(self, heading: str, url: str) -> str:
        """Extract a clear, actionable topic from heading or URL"""
        
        # Clean the heading first
        cleaned_heading = heading.strip()
        
        # Remove common prefixes
        prefixes_to_remove = ['r/', 'complete guide:', 'ultimate guide:', 'best', 'top', 'how to']
        for prefix in prefixes_to_remove:
            if cleaned_heading.lower().startswith(prefix.lower()):
                cleaned_heading = cleaned_heading[len(prefix):].strip()
        
        # If heading is still unclear, extract from URL
        if (len(cleaned_heading.split()) < 2 or 
            cleaned_heading.lower() in ['seedboxes', 'home', 'main', 'index']):
            
            # Extract meaningful part from URL
            domain = url.split('/')[2].replace('www.', '')
            
            # Common URL patterns to extract topics
            url_lower = url.lower()
            
            if 'seedbox' in url_lower:
                if 'setup' in url_lower or 'guide' in url_lower:
                    return "Seedbox Setup"
                elif 'review' in url_lower or 'comparison' in url_lower:
                    return "Seedbox Reviews and Comparisons"
                elif 'plex' in url_lower:
                    return "Seedbox for Plex Setup"
                elif 'vpn' in url_lower:
                    return "Seedbox VPN Configuration"
                else:
                    return "Seedbox Guide"
            
            elif 'plex' in url_lower:
                if 'server' in url_lower:
                    return "Plex Media Server Setup"
                elif 'seedbox' in url_lower:
                    return "Plex with Seedbox Integration"
                else:
                    return "Plex Configuration"
            
            elif 'vpn' in url_lower:
                return "VPN Setup and Configuration"
            
            # Fallback to domain-based topic
            if 'seedbox' in domain:
                return "Seedbox Solutions"
            elif 'plex' in domain:
                return "Plex Media Solutions"
            else:
                return f"{domain.split('.')[0].title()} Guide"
        
        # Clean up the heading further
        # Capitalize properly
        words = cleaned_heading.split()
        if len(words) > 0:
            # Make it title case but keep important words capitalized
            important_words = ['seedbox', 'plex', 'vpn', 'api', 'ssl', 'ssh', 'ftp']
            result_words = []
            
            for word in words:
                if word.lower() in important_words:
                    result_words.append(word.upper())
                else:
                    result_words.append(word.capitalize())
            
            return ' '.join(result_words)
        
        return cleaned_heading.title() if cleaned_heading else "Content Topic"
    
    def find_content_gaps(self, competitor_topics: List[TopicData], 
                         reddit_topics: List[TopicData],
                         search_topics: List[TopicData],
                         depth_gaps: List[TopicData]) -> List[TopicData]:
        """Find real content gaps with more aggressive detection"""
        all_user_topics = reddit_topics + search_topics + depth_gaps
        gaps = []
        
        if not all_user_topics:
            return gaps
        
        if not competitor_topics:
            # If no competitor data, everything is a gap
            return all_user_topics
        
        competitor_embeddings = np.array([t.embedding for t in competitor_topics])
        
        # More aggressive gap detection
        for user_topic in all_user_topics:
            # Check if competitors cover this topic
            similarities = cosine_similarity([user_topic.embedding], competitor_embeddings)[0]
            max_similarity = np.max(similarities) if len(similarities) > 0 else 0
            
            # Lower threshold for gap detection (was 0.7, now 0.6)
            # This means if similarity < 60%, it's considered a gap
            if max_similarity < 0.6:
                gaps.append(user_topic)
            
            # Also check for partial coverage gaps
            # If similarity is 0.6-0.75, it might still be worth targeting
            elif 0.6 <= max_similarity < 0.75:
                # Check if it's a high-value topic (search suggestion or highly upvoted)
                if (user_topic.source == 'search_suggest' or 
                    (user_topic.source == 'reddit' and user_topic.upvotes > 20) or
                    user_topic.source == 'depth_gap'):
                    
                    # Mark as partial gap - still worth targeting
                    user_topic.confidence = user_topic.confidence * 0.8  # Reduce confidence slightly
                    gaps.append(user_topic)
        
        # Add some semantic gap detection
        # Look for topics that are semantically different from all competitor content
        if competitor_topics and all_user_topics:
            semantic_gaps = self._find_semantic_gaps(competitor_topics, all_user_topics)
            gaps.extend(semantic_gaps)
        
        # Sort by confidence and engagement
        gaps.sort(key=lambda x: (x.confidence, x.upvotes), reverse=True)
        return gaps

    def _find_semantic_gaps(
        self,
        competitor_topics: List[TopicData],
        user_topics: List[TopicData]
    ) -> List[TopicData]:
        """Find semantic gaps using clustering"""
        semantic_gaps = []

        # Find topics that are semantically isolated from competitor content
        for user_topic in user_topics:
            competitor_distances = []

            for comp_topic in competitor_topics:
                similarity = cosine_similarity(
                    [user_topic.embedding],
                    [comp_topic.embedding]
                )[0][0]
                distance = 1 - similarity
                competitor_distances.append(distance)

            # If this topic is semantically distant from ALL competitor topics
            if competitor_distances:          # avoid min() on empty list
                min_distance = min(competitor_distances)
                if min_distance > 0.4:
                    semantic_gaps.append(
                        TopicData(
                            text=f"Semantic gap: {user_topic.text}",
                            embedding=user_topic.embedding,
                            source=f"semantic_{user_topic.source}",
                            source_url=user_topic.source_url,
                            competitor_id=-1,
                            confidence=0.7,
                            upvotes=user_topic.upvotes,
                            word_count=user_topic.word_count,
                        )
                    )

        return semantic_gaps    

    def analyze_website_relevance(self, website_url: str, target_topic: str, max_pages: int = None) -> Dict:
        """Analyze entire website to find irrelevant content using vector embeddings"""
        st.info(f"🔍 Analyzing {website_url} for topic relevance...")
        
        try:
            # Get all pages from the website
            pages_data = self._crawl_entire_website(website_url, max_pages)
            
            if not pages_data:
                return {"error": "Could not crawl website pages"}
            
            # Batch process embeddings for efficiency
            st.info(f"🧠 Processing {len(pages_data)} pages with AI...")
            target_embedding = self.embedding_model.encode([target_topic])[0]
            
            # Process pages in batches to avoid memory issues
            batch_size = 50
            relevance_results = []
            
            progress_bar = st.progress(0)
            
            for i in range(0, len(pages_data), batch_size):
                batch = pages_data[i:i + batch_size]
                batch_texts = [page['content'] for page in batch]
                
                # Process batch embeddings
                batch_embeddings = self.embedding_model.encode(batch_texts, show_progress_bar=False)
                
                for j, page in enumerate(batch):
                    # Calculate similarity to target topic
                    similarity = cosine_similarity([target_embedding], [batch_embeddings[j]])[0][0]
                    
                    relevance_results.append({
                        'url': page['url'],
                        'title': page['title'],
                        'word_count': page['word_count'],
                        'similarity_score': similarity,
                        'relevance_status': self._categorize_relevance(similarity),
                        'content_preview': page['content'][:200] + "...",
                        'main_topics': self._extract_main_topics(page['content'])
                    })
                
                # Update progress
                progress = min((i + batch_size) / len(pages_data), 1.0)
                progress_bar.progress(progress)
            
            # Sort by least relevant first (lowest similarity)
            relevance_results.sort(key=lambda x: x['similarity_score'])
            
            return {
                'target_topic': target_topic,
                'total_pages': len(relevance_results),
                'irrelevant_pages': len([r for r in relevance_results if r['relevance_status'] == 'Irrelevant']),
                'somewhat_relevant': len([r for r in relevance_results if r['relevance_status'] == 'Somewhat Relevant']),
                'highly_relevant': len([r for r in relevance_results if r['relevance_status'] == 'Highly Relevant']),
                'pages': relevance_results
            }
            
        except Exception as e:
            return {"error": f"Error analyzing website: {str(e)}"}
    
    def _crawl_entire_website(self, base_url: str, max_pages: int = None) -> List[Dict]:
        """Advanced website crawler with safety limits and better handling"""
        pages_data = []
        visited_urls = set()
        urls_to_visit = [base_url]
        
        # Get base domain for staying on same site
        from urllib.parse import urljoin, urlparse, parse_qs
        base_domain = urlparse(base_url).netloc
        
        # Try to find sitemap first for faster discovery
        sitemap_urls = self._discover_sitemap_urls(base_url)
        if sitemap_urls:
            st.info(f"📋 Found sitemap with {len(sitemap_urls)} URLs")
            urls_to_visit.extend(sitemap_urls)
        
        # Remove duplicates
        urls_to_visit = list(dict.fromkeys(urls_to_visit))
        
        # Apply safety limits
        if max_pages:
            urls_to_visit = urls_to_visit[:max_pages]
            st.info(f"🔍 Analyzing up to {max_pages} pages (user limit)")
        else:
            # Safety limit for unlimited crawling
            if len(urls_to_visit) > 500:
                st.warning(f"⚠️ Large website detected ({len(urls_to_visit)} URLs). Limiting to 500 pages for performance.")
                urls_to_visit = urls_to_visit[:500]
            st.info(f"🔍 Analyzing website ({len(urls_to_visit)} URLs discovered)")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_to_process = len(urls_to_visit)
        successful_crawls = 0
        errors = 0
        
        for i, current_url in enumerate(urls_to_visit):
            if current_url in visited_urls:
                continue
                
            visited_urls.add(current_url)
            status_text.text(f"Crawling {i+1}/{total_to_process}: {current_url.split('/')[-1][:50]}...")
            
            # Fix progress calculation
            progress_value = min((i + 1) / max(total_to_process, 1), 1.0)
            progress_bar.progress(progress_value)
            
            try:
                # Skip certain file types
                if any(current_url.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.xml', '.txt']):
                    continue
                
                response = requests.get(current_url, headers=self.headers, timeout=20)
                response.raise_for_status()
                
                # Skip non-HTML content
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' not in content_type:
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove noise elements
                for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                    element.decompose()
                
                # Get page title
                title = soup.find('title')
                title_text = title.get_text().strip() if title else current_url.split('/')[-1]
                
                # Get main content with multiple strategies
                content = self._extract_main_content(soup)
                content = re.sub(r'\s+', ' ', content).strip()
                
                # Calculate word count
                word_count = len([w for w in content.split() if w.isalpha()])
                
                if word_count > 50:  # Include pages with substantial content
                    pages_data.append({
                        'url': current_url,
                        'title': title_text,
                        'content': content,
                        'word_count': word_count
                    })
                    successful_crawls += 1
                
                # For sites without sitemaps, discover more URLs (limited)
                if not sitemap_urls and len(urls_to_visit) < 100:  # Only for small sites
                    new_urls = self._discover_internal_links(soup, current_url, base_domain, visited_urls)
                    remaining_slots = min(20, 100 - len(urls_to_visit))  # Add max 20 more URLs
                    urls_to_visit.extend(new_urls[:remaining_slots])
                    total_to_process = len(urls_to_visit)
                
                # Rate limiting - be respectful
                time.sleep(0.8)  # Slightly slower for large sites
                
            except Exception as e:
                errors += 1
                if errors > 10:  # Too many errors, stop
                    st.error(f"❌ Too many errors ({errors}). Stopping crawl.")
                    break
                continue
            
            # Safety break for very large sites
            if len(pages_data) > 200:
                st.warning(f"⚠️ Reached 200 pages limit for performance. Stopping crawl.")
                break
        
        status_text.text(f"✅ Crawl complete: {successful_crawls} pages analyzed, {errors} errors")
        
        if len(pages_data) == 0:
            st.error("❌ No pages could be crawled. The website might be blocking requests or have technical issues.")
        
        return pages_data
    
    def _discover_sitemap_urls(self, base_url: str) -> List[str]:
        """Try to find and parse XML sitemaps for faster URL discovery"""
        sitemap_urls = []
        
        # Clean base URL
        base_url = base_url.rstrip('/')
        
        # Common sitemap locations
        sitemap_locations = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap/sitemap.xml",
            f"{base_url}/sitemaps/sitemap.xml",
            f"{base_url}/wp-sitemap.xml",  # WordPress
            f"{base_url}/sitemap-index.xml",
            f"{base_url}/robots.txt"
        ]
        
        for sitemap_url in sitemap_locations:
            try:
                st.write(f"🔍 Checking: {sitemap_url}")
                response = requests.get(sitemap_url, headers=self.headers, timeout=15)
                
                if response.status_code == 200:
                    if sitemap_url.endswith('robots.txt'):
                        # Parse robots.txt for sitemap references
                        st.write("📋 Parsing robots.txt for sitemaps...")
                        for line in response.text.split('\n'):
                            line = line.strip()
                            if line.lower().startswith('sitemap:'):
                                actual_sitemap = line.split(':', 1)[1].strip()
                                st.write(f"📋 Found sitemap in robots.txt: {actual_sitemap}")
                                try:
                                    sitemap_response = requests.get(actual_sitemap, headers=self.headers, timeout=15)
                                    if sitemap_response.status_code == 200:
                                        new_urls = self._parse_sitemap_xml(sitemap_response.text, base_url)
                                        sitemap_urls.extend(new_urls)
                                        st.write(f"✅ Extracted {len(new_urls)} URLs from {actual_sitemap}")
                                except Exception as e:
                                    st.write(f"❌ Error parsing sitemap from robots.txt: {str(e)}")
                                    continue
                    else:
                        # Parse XML sitemap
                        st.write(f"✅ Found XML sitemap: {sitemap_url}")
                        new_urls = self._parse_sitemap_xml(response.text, base_url)
                        sitemap_urls.extend(new_urls)
                        st.write(f"✅ Extracted {len(new_urls)} URLs from sitemap")
                        
                    if sitemap_urls:
                        st.success(f"🎉 Total discovered: {len(sitemap_urls)} URLs from sitemaps!")
                        break  # Found working sitemap
                else:
                    st.write(f"❌ HTTP {response.status_code} for {sitemap_url}")
                        
            except Exception as e:
                st.write(f"❌ Could not access {sitemap_url}: {str(e)}")
                continue
        
        if not sitemap_urls:
            st.warning("⚠️ No sitemaps found. Will use aggressive link discovery instead.")
            # Try a more aggressive approach for sites without sitemaps
            return self._fallback_url_discovery(base_url)
        
        return sitemap_urls[:1000]  # Reasonable limit to prevent crashes
    
    def _fallback_url_discovery(self, base_url: str) -> List[str]:
        """Fallback URL discovery for sites without sitemaps"""
        discovered_urls = [base_url]
        
        try:
            st.info("🕷️ Using aggressive link discovery (no sitemap found)...")
            response = requests.get(base_url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove noise
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()
                
                # Find all internal links
                from urllib.parse import urljoin, urlparse
                base_domain = urlparse(base_url).netloc
                
                links = soup.find_all('a', href=True)
                st.write(f"🔗 Found {len(links)} links on homepage")
                
                for link in links:
                    href = link['href'].strip()
                    if not href or href.startswith('#'):
                        continue
                    
                    full_url = urljoin(base_url, href)
                    parsed = urlparse(full_url)
                    
                    if (parsed.netloc == base_domain and 
                        full_url not in discovered_urls and
                        not any(full_url.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.gif', '.zip'])):
                        discovered_urls.append(full_url)
                        
                        if len(discovered_urls) >= 50:  # Limit for fallback
                            break
                
                st.info(f"🔗 Discovered {len(discovered_urls)} URLs through link crawling")
        
        except Exception as e:
            st.error(f"❌ Fallback discovery failed: {str(e)}")
        
        return discovered_urls
    
    def _parse_sitemap_xml(self, xml_content: str, base_url: str) -> List[str]:
        """Parse XML sitemap to extract URLs with better error handling"""
        urls = []
        try:
            # Handle different XML parsers
            try:
                soup = BeautifulSoup(xml_content, 'xml')
            except:
                soup = BeautifulSoup(xml_content, 'html.parser')
            
            # Handle sitemap index files
            sitemap_tags = soup.find_all('sitemap')
            if sitemap_tags:
                st.write(f"📑 Processing sitemap index with {len(sitemap_tags)} nested sitemaps...")
                for sitemap in sitemap_tags[:10]:  # Limit nested sitemaps
                    loc = sitemap.find('loc')
                    if loc:
                        # Recursively parse nested sitemaps
                        try:
                            nested_url = loc.text.strip()
                            response = requests.get(nested_url, timeout=10)
                            if response.status_code == 200:
                                nested_urls = self._parse_sitemap_xml(response.text, base_url)
                                urls.extend(nested_urls)
                                st.write(f"  ✅ Parsed {len(nested_urls)} URLs from {nested_url}")
                        except Exception:
                            continue
            
            # Handle regular URL entries
            url_tags = soup.find_all('url')
            if url_tags:
                st.write(f"📄 Processing {len(url_tags)} individual URLs...")
                for url_tag in url_tags:
                    loc = url_tag.find('loc')
                    if loc:
                        url = loc.text.strip()
                        # Ensure URL is from the same domain
                        from urllib.parse import urlparse
                        if urlparse(url).netloc == urlparse(base_url).netloc:
                            urls.append(url)
                    
        except Exception as e:
            st.write(f"❌ Error parsing sitemap XML: {str(e)}")
        
        return urls
    
    def _extract_main_content(self, soup) -> str:
        """Extract main content using multiple strategies"""
        content = ""
        
        # Strategy 1: Look for main content selectors
        content_selectors = [
            'article', 'main', '[role="main"]', '.content', '#content', 
            '.post-content', '.entry-content', '.page-content', '.article-content',
            '.post', '.entry', '.article', '.blog-post'
        ]
        
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                content = ' '.join([elem.get_text() for elem in elements])
                break
        
        # Strategy 2: If no main content found, use body but filter out common noise
        if not content or len(content) < 100:
            body = soup.find('body')
            if body:
                # Remove common navigation and sidebar elements
                for noise in body.select('nav, .navigation, .sidebar, .menu, .footer, .header, .breadcrumb, .social, .share'):
                    noise.decompose()
                content = body.get_text()
        
        # Strategy 3: Fallback to all text
        if not content:
            content = soup.get_text()
        
        return content
    
    def _discover_internal_links(self, soup, current_url: str, base_domain: str, visited_urls: set) -> List[str]:
        """Discover internal links from current page with better filtering"""
        from urllib.parse import urljoin, urlparse, urlunparse
        
        new_urls = []
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link['href'].strip()
            
            # Skip empty or invalid hrefs
            if not href or href in ['#', 'javascript:void(0)', 'javascript:;']:
                continue
            
            # Convert to absolute URL
            full_url = urljoin(current_url, href)
            
            # Parse URL
            parsed = urlparse(full_url)
            
            # Clean the URL (remove fragments and some parameters)
            clean_url = urlunparse((
                parsed.scheme,
                parsed.netloc, 
                parsed.path.rstrip('/'),  # Remove trailing slash for consistency
                parsed.params,
                parsed.query,
                ''  # Remove fragment
            ))
            
            # Only add internal links from same domain
            if (parsed.netloc == base_domain and 
                clean_url not in visited_urls and 
                clean_url != current_url and  # Don't add self-references
                not any(clean_url.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc', '.docx', '.xls', '.xlsx']) and
                not any(skip in clean_url.lower() for skip in ['/wp-admin/', '/admin/', '/login', '/register', '/cart', '/checkout', '/search?', '?page=']) and
                len(parsed.path.split('/')) <= 6):  # Avoid very deep URLs
                
                new_urls.append(clean_url)
                
                if len(new_urls) >= 30:  # Increased limit per page
                    break
        
        return new_urls
    
    def _categorize_relevance(self, similarity_score: float) -> str:
        """Categorize relevance based on similarity score with more lenient thresholds"""
        if similarity_score >= 0.5:  # Lowered from 0.7
            return "Highly Relevant"
        elif similarity_score >= 0.25:  # Lowered from 0.4
            return "Somewhat Relevant"
        else:
            return "Irrelevant"
    
    def _extract_main_topics(self, content: str) -> List[str]:
        """Extract main topics from content using simple keyword extraction with fallback"""
        try:
            # Try NLTK tokenization first
            words = word_tokenize(content.lower())
        except:
            # Fallback to simple split if NLTK fails
            words = content.lower().split()
        
        # Remove stop words and get word frequency
        try:
            # Try using NLTK stopwords
            clean_words = [w for w in words if w.isalpha() and len(w) > 3 and w not in self.stop_words]
        except:
            # Fallback stopwords if NLTK fails
            basic_stopwords = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once'}
            clean_words = [w for w in words if w.isalpha() and len(w) > 3 and w not in basic_stopwords]
        
        from collections import Counter
        word_freq = Counter(clean_words)
        
        # Get top 5 most frequent meaningful words
        top_words = [word for word, freq in word_freq.most_common(5)]
        return top_words
    
    def create_relevance_visualization(self, relevance_data: Dict) -> go.Figure:
        """Create visualization for website relevance analysis"""
        if 'error' in relevance_data:
            return None
            
        pages = relevance_data['pages']
        
        # Create scatter plot
        fig = go.Figure()
        
        # Color mapping for relevance
        color_map = {
            'Irrelevant': 'red',
            'Somewhat Relevant': 'orange', 
            'Highly Relevant': 'green'
        }
        
        for status in ['Irrelevant', 'Somewhat Relevant', 'Highly Relevant']:
            filtered_pages = [p for p in pages if p['relevance_status'] == status]
            
            if filtered_pages:
                similarities = [p['similarity_score'] for p in filtered_pages]
                word_counts = [p['word_count'] for p in filtered_pages]
                titles = [p['title'][:50] + "..." if len(p['title']) > 50 else p['title'] for p in filtered_pages]
                urls = [p['url'] for p in filtered_pages]
                
                hover_text = [f"<b>{title}</b><br>Similarity: {sim:.2%}<br>Words: {wc}<br>URL: {url}" 
                             for title, sim, wc, url in zip(titles, similarities, word_counts, urls)]
                
                fig.add_trace(go.Scatter(
                    x=similarities,
                    y=word_counts,
                    mode='markers',
                    name=f'{status} ({len(filtered_pages)})',
                    marker=dict(
                        size=12,
                        color=color_map[status],
                        opacity=0.7,
                        line=dict(width=1, color='white')
                    ),
                    hovertemplate='%{hovertext}<extra></extra>',
                    hovertext=hover_text
                ))
        
        fig.update_layout(
            title=f'Website Content Relevance Analysis<br><sup>Target Topic: "{relevance_data["target_topic"]}"</sup>',
            xaxis_title='Similarity Score (Higher = More Relevant)',
            yaxis_title='Word Count',
            width=800,
            height=600,
            showlegend=True,
            legend=dict(x=0.02, y=0.98)
        )
        
        # Add relevance threshold lines with updated values
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig.add_vline(x=0.25, line_dash="dash", line_color="orange", opacity=0.5, 
                     annotation_text="Relevance Threshold")
        fig.add_vline(x=0.5, line_dash="dash", line_color="green", opacity=0.5,
                     annotation_text="High Relevance")
        
        return fig
    
    def generate_actionable_topics(self, gaps: List[TopicData]) -> List[Dict]:
        """Convert gaps to actionable topics"""
        actionable_topics = []
        
        for gap in gaps:
            # Generate better topic titles
            if gap.source == 'reddit':
                topic_title = self._reddit_to_topic(gap.text)
            elif gap.source == 'search_suggest':
                topic_title = f"Ultimate Guide: {gap.text.title()}"
            elif gap.source == 'depth_gap':
                topic_title = gap.text  # Already formatted
            else:
                topic_title = f"Complete Guide: {gap.text}"
            
            # Calculate scores
            difficulty = self._estimate_difficulty(gap.text)
            opportunity_score = self._calculate_opportunity_score(gap)
            
            actionable_topics.append({
                'title': topic_title,
                'difficulty': difficulty,
                'opportunity_score': opportunity_score,
                'source': gap.source,
                'upvotes': gap.upvotes,
                'confidence': gap.confidence,
                'why_gap': self._explain_gap(gap),
                'content_angle': self._suggest_angle(gap)
            })
        
        # Sort by opportunity score
        actionable_topics.sort(key=lambda x: x['opportunity_score'], reverse=True)
        return actionable_topics
    
    def _reddit_to_topic(self, reddit_text: str) -> str:
        """Convert Reddit question to blog post title"""
        text = reddit_text.strip()
        text_lower = text.lower()
        
        # Specific patterns for common topics
        if 'seedbox' in text_lower:
            if any(word in text_lower for word in ['slow', 'speed']):
                return "How to Fix Slow Seedbox Performance: Complete Troubleshooting Guide"
            elif any(word in text_lower for word in ['best', 'recommend']):
                return "Best Seedbox Providers: Complete Comparison Guide 2025"
            elif 'plex' in text_lower:
                return "Seedbox + Plex Setup: Complete Media Server Guide"
            else:
                return "Ultimate Seedbox Guide: Everything You Need to Know"
        
        elif any(word in text_lower for word in ['plex', 'media server']):
            if 'mini pc' in text_lower:
                return "Best Mini PC for Plex Server: Complete Hardware Guide 2025"
            elif 'power' in text_lower:
                return "Most Power-Efficient Plex Server Setup Guide"
            else:
                return "Complete Plex Media Server Setup Guide"
        
        elif 'vpn' in text_lower:
            if 'best' in text_lower:
                return "Best VPN for Torrenting: Complete Privacy Guide 2025"
            else:
                return "Complete VPN Guide for Privacy and Security"
        
        # Generic patterns
        if text_lower.startswith('how to'):
            return f"Complete Guide: {text}"
        elif text_lower.startswith('what is'):
            topic = text[7:].strip()  # Remove "what is"
            return f"Complete Guide to {topic}"
        elif text_lower.startswith('best'):
            return f"{text} - Complete Guide 2025"
        elif '?' in text:
            clean_text = text.replace('?', '').strip()
            return f"Complete Guide: {clean_text}"
        else:
            return f"Ultimate Guide: {text[:60]}..."
    
    def _estimate_difficulty(self, text: str) -> str:
        """Estimate content difficulty"""
        text_lower = text.lower()
        if any(word in text_lower for word in ['api', 'technical', 'advanced']):
            return 'Hard'
        elif any(word in text_lower for word in ['setup', 'install', 'configure']):
            return 'Medium'
        else:
            return 'Easy'
    
    def _calculate_opportunity_score(self, gap: TopicData) -> float:
        """Calculate opportunity score 0-100"""
        score = gap.confidence * 50
        
        if gap.source == 'reddit' and gap.upvotes > 0:
            score += min(gap.upvotes * 2, 30)
        
        if gap.source == 'search_suggest':
            score += 20
        
        if gap.source == 'depth_gap':
            score += 15
        
        return min(score, 100)
    
    def _explain_gap(self, gap: TopicData) -> str:
        """Explain why this is a gap with clear actionable insight"""
        if gap.source == 'reddit':
            return f"Real users asking about this (upvotes: {gap.upvotes}), but competitors don't address it well"
        elif gap.source == 'search_suggest':
            return "People actively search for this, but current results are weak"
        elif gap.source == 'depth_gap':
            return f"Current best content is only {gap.word_count} words - opportunity for comprehensive coverage"
        elif gap.source.startswith('semantic_'):
            return "Topic is semantically different from existing competitor content"
        else:
            return "User demand exists but competition is low"
    
    def _suggest_angle(self, gap: TopicData) -> str:
        """Suggest content approach with specific recommendations"""
        if gap.source == 'reddit':
            return "FAQ/Problem-solving format - address specific user pain points from Reddit discussions"
        elif gap.source == 'search_suggest':
            return "SEO-optimized comprehensive guide targeting the exact search query people use"
        elif gap.source == 'depth_gap':
            return f"Create 2000+ word definitive guide (currently only {gap.word_count} words available)"
        elif gap.source.startswith('semantic_'):
            return "Unique angle not covered by competitors - first-mover advantage"
        else:
            return "Complete guide covering all aspects of the topic"
    
    def create_visualization(self, competitor_topics: List[TopicData],
                           all_user_topics: List[TopicData], 
                           gaps: List[TopicData], 
                           keyword: str,
                           competitor_urls: List[str]):
        """Create 3D visualization"""
        all_topics = competitor_topics + all_user_topics
        if not all_topics:
            return None
            
        embeddings = np.array([topic.embedding for topic in all_topics])
        
        # Reduce to 3D
        pca = PCA(n_components=3)
        embeddings_3d = pca.fit_transform(embeddings)
        
        fig = go.Figure()
        
        # Always add all legend entries for clarity (even if empty)
        # This ensures first-time users understand what each color means
        
        # Plot competitor topics
        comp_indices = [i for i, topic in enumerate(all_topics) if topic.source == 'competitor']
        if comp_indices:
            comp_data = embeddings_3d[comp_indices]
            comp_colors = [all_topics[i].competitor_id for i in comp_indices]
            
            # Get competitor names from URLs
            competitor_names = []
            for url in competitor_urls:
                domain = url.split('/')[2].replace('www.', '')
                competitor_names.append(domain[:20])
            
            comp_hovers = []
            for i in comp_indices:
                topic = all_topics[i]
                comp_id = topic.competitor_id
                comp_name = competitor_names[comp_id] if comp_id < len(competitor_names) else f'Competitor {comp_id+1}'
                hover_text = f"🏢 {comp_name}<br>Topic: {topic.text[:60]}...<br>Words: {topic.word_count}<br>URL: {topic.source_url}<br><br>💡 Click to select and view URL"
                comp_hovers.append(hover_text)
            
            fig.add_trace(go.Scatter3d(
                x=comp_data[:, 0], y=comp_data[:, 1], z=comp_data[:, 2],
                mode='markers',
                marker=dict(size=6, opacity=0.6, color=comp_colors, colorscale='Viridis'),
                hovertemplate='%{hovertext}<extra></extra>',
                hovertext=comp_hovers,
                name='🏢 Competitor Content',
                customdata=[all_topics[i].source_url for i in comp_indices],
                showlegend=True
            ))
        else:
            # Add invisible trace for legend
            fig.add_trace(go.Scatter3d(
                x=[None], y=[None], z=[None],
                mode='markers',
                marker=dict(size=6, color='gray', opacity=0.6),
                name='🏢 Competitor Content',
                showlegend=True,
                hoverinfo='skip'
            ))
        
        # Plot Reddit topics
        reddit_indices = [i for i, topic in enumerate(all_topics) if topic.source == 'reddit']
        if reddit_indices:
            reddit_data = embeddings_3d[reddit_indices]
            reddit_hovers = [f"💬 Reddit Question<br>{all_topics[i].text[:60]}...<br>Upvotes: {all_topics[i].upvotes}<br>Source: Real user question<br>URL: {all_topics[i].source_url}<br><br>💡 Click to select and view URL" for i in reddit_indices]
            
            fig.add_trace(go.Scatter3d(
                x=reddit_data[:, 0], y=reddit_data[:, 1], z=reddit_data[:, 2],
                mode='markers',
                marker=dict(size=8, opacity=0.8, color='orange', symbol='square'),
                hovertemplate='%{hovertext}<extra></extra>',
                hovertext=reddit_hovers,
                name='💬 Reddit Questions',
                customdata=[all_topics[i].source_url for i in reddit_indices],
                showlegend=True
            ))
        else:
            # Add invisible trace for legend
            fig.add_trace(go.Scatter3d(
                x=[None], y=[None], z=[None],
                mode='markers',
                marker=dict(size=8, color='orange', symbol='square', opacity=0.8),
                name='💬 Reddit Questions',
                showlegend=True,
                hoverinfo='skip'
            ))
        
        # Plot search suggestions
        search_indices = [i for i, topic in enumerate(all_topics) if topic.source == 'search_suggest']
        if search_indices:
            search_data = embeddings_3d[search_indices]
            search_hovers = [f"🔍 Search Suggestion<br>Query: {all_topics[i].text}<br>Source: Google Autocomplete<br>People actually search this<br><br>💡 Click to select and view details" for i in search_indices]
            
            fig.add_trace(go.Scatter3d(
                x=search_data[:, 0], y=search_data[:, 1], z=search_data[:, 2],
                mode='markers',
                marker=dict(size=8, opacity=0.8, color='blue', symbol='cross'),
                hovertemplate='%{hovertext}<extra></extra>',
                hovertext=search_hovers,
                name='🔍 Search Suggestions',
                customdata=[all_topics[i].source_url for i in search_indices],
                showlegend=True
            ))
        else:
            # Add invisible trace for legend
            fig.add_trace(go.Scatter3d(
                x=[None], y=[None], z=[None],
                mode='markers',
                marker=dict(size=8, color='blue', symbol='cross', opacity=0.8),
                name='🔍 Search Suggestions',
                showlegend=True,
                hoverinfo='skip'
            ))
        
        # Plot depth gaps
        depth_indices = [i for i, topic in enumerate(all_topics) if topic.source == 'depth_gap']
        if depth_indices:
            depth_data = embeddings_3d[depth_indices]
            depth_hovers = [f"📊 Thin Content Gap<br>Topic: {all_topics[i].text}<br>Avg competitor depth: {all_topics[i].word_count} words<br>Opportunity: Create comprehensive guide<br>URL: {all_topics[i].source_url}<br><br>💡 Click to select and view URL" for i in depth_indices]
            
            fig.add_trace(go.Scatter3d(
                x=depth_data[:, 0], y=depth_data[:, 1], z=depth_data[:, 2],
                mode='markers',
                marker=dict(size=10, opacity=0.9, color='purple', symbol='circle'),
                hovertemplate='%{hovertext}<extra></extra>',
                hovertext=depth_hovers,
                name='📊 Thin Content Gaps',
                customdata=[all_topics[i].source_url for i in depth_indices],
                showlegend=True
            ))
        else:
            # Add invisible trace for legend
            fig.add_trace(go.Scatter3d(
                x=[None], y=[None], z=[None],
                mode='markers',
                marker=dict(size=10, color='purple', symbol='circle', opacity=0.9),
                name='📊 Thin Content Gaps',
                showlegend=True,
                hoverinfo='skip'
            ))
        
        # Highlight content gaps in red
        gap_texts = [gap.text for gap in gaps]
        gap_indices = [i for i, topic in enumerate(all_topics) if topic.text in gap_texts]
        
        if gap_indices:
            gap_data = embeddings_3d[gap_indices]
            gap_hovers = []
            
            for i in gap_indices:
                topic = all_topics[i]
                source_emoji = {'reddit': '💬', 'search_suggest': '🔍', 'depth_gap': '📊'}.get(topic.source, '🎯')
                hover_text = f"{source_emoji} CONTENT GAP<br>Topic: {topic.text[:60]}...<br>Source: {topic.source.replace('_', ' ').title()}<br>Why gap: No competitors cover this well<br>Confidence: {topic.confidence:.1%}"
                gap_hovers.append(hover_text)
            
            fig.add_trace(go.Scatter3d(
                x=gap_data[:, 0], y=gap_data[:, 1], z=gap_data[:, 2],
                mode='markers',
                marker=dict(size=15, symbol='diamond', color='red', opacity=1.0, 
                           line=dict(color='black', width=2)),
                hovertemplate='%{hovertext}<extra></extra>',
                hovertext=gap_hovers,
                name=f'🎯 CONTENT GAPS ({len(gaps)})',
                customdata=[all_topics[i].source_url for i in gap_indices]
            ))
        
        fig.update_layout(
            title=f'Data-Driven Analysis: "{keyword}"<br><sup>Real user data from Reddit + Search + Competitor analysis</sup>',
            scene=dict(
                xaxis_title='Semantic Dimension 1',
                yaxis_title='Semantic Dimension 2', 
                zaxis_title='Semantic Dimension 3'
            ),
            width=1000,
            height=700,
            legend=dict(
                x=0.02,
                y=0.98,
                bgcolor="rgba(0,0,0,0)",  # Transparent background
                bordercolor="rgba(255,255,255,0.3)",
                borderwidth=1,
                font=dict(color="white", size=12)  # White text for better visibility
            )
        )
        
        return fig
    
    def run_analysis(self, keyword: str, num_competitors: int = 8):
        """Run complete analysis"""
        st.header(f"🎯 Data-Driven Analysis: '{keyword}'")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Find competitors
        status_text.text("🔍 Finding competitors...")
        progress_bar.progress(0.1)
        competitor_urls = self.search_competitors(keyword, num_competitors)
        
        # Step 2: Get search suggestions
        status_text.text("🔍 Getting search suggestions...")
        progress_bar.progress(0.2)
        search_topics = self.get_search_suggestions(keyword)
        
        # Step 3: Mine Reddit
        status_text.text("💬 Mining Reddit...")
        progress_bar.progress(0.4)
        reddit_topics = self.mine_reddit_discussions(keyword)
        
        # Step 4: Analyze competitors
        status_text.text("📄 Analyzing competitors...")
        competitor_topics = self.scrape_competitor_content(competitor_urls, progress_bar)
        progress_bar.progress(0.7)
        
        # Step 5: Find thin content
        status_text.text("📊 Finding thin content...")
        depth_gaps = self.analyze_content_depth(competitor_topics)
        progress_bar.progress(0.8)
        
        # Step 6: Find gaps
        status_text.text("🎯 Identifying gaps...")
        all_user_topics = reddit_topics + search_topics + depth_gaps
        gaps = self.find_content_gaps(competitor_topics, reddit_topics, search_topics, depth_gaps)
        progress_bar.progress(0.9)
        
        # Step 7: Generate actionable topics
        status_text.text("📝 Creating actionable topics...")
        actionable_topics = self.generate_actionable_topics(gaps)
        
        # Step 8: Create visualization
        status_text.text("📊 Creating visualization...")
        fig = self.create_visualization(competitor_topics, all_user_topics, gaps, keyword, competitor_urls)
        progress_bar.progress(1.0)
        status_text.text("✅ Analysis complete!")
        
        return fig, gaps, competitor_topics, competitor_urls, reddit_topics, search_topics, depth_gaps, actionable_topics

# Streamlit App
def main():
    st.set_page_config(
        page_title="Data-Driven SEO Analyzer", 
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Header with logo and branding
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        # Add your logo here - you'll need to upload logo.png to your repo
        try:
            st.image("logo.png", width=120)
        except:
            st.write("")  # Fallback emoji if no logo
    
    with col2:
        st.title("Content Gap Analyzer")
        st.markdown("**Find content gaps using REAL user data!**")
    
    with col3:
        # Your website link
        st.markdown("""
        <div style='text-align: right; padding-top: 20px;'>

        </div>
        """, unsafe_allow_html=True)
    
    # Add custom CSS for better styling
    st.markdown("""
    <style>
    .main > div {
        padding-top: 1rem;
    }
    
    .stApp > header {
        background-color: transparent;
    }
    
    .css-1d391kg {
        padding-top: 1rem;
    }
    
    /* Custom button styling */
    div.stButton > button {
        background: linear-gradient(45deg, #ff4b4b, #ff6b6b);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        transition: all 0.3s;
    }
    
    div.stButton > button:hover {
        background: linear-gradient(45deg, #ff3b3b, #ff5b5b);
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(255, 75, 75, 0.3);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background-color: #f8f9fa;
    }
    
    /* Footer */
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #0e1117;
        color: white;
        text-align: center;
        padding: 10px;
        font-size: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Buy Me a Coffee Widget
    st.markdown("""
    <script data-name="BMC-Widget" data-cfasync="false" src="https://cdnjs.buymeacoffee.com/1.0.0/widget.prod.min.js" data-id="deyangeorgiev" data-description="Support me on Buy me a coffee!" data-message="If this tool has helped you, consider getting me a coffee :) Thanks!" data-color="#5F7FFF" data-position="Right" data-x_margin="18" data-y_margin="18"></script>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Tool selection
        analysis_mode = st.radio(
            "Choose Analysis Type:",
            ["🔍 Find Content Gaps", "🎯 Check Website Relevance"],
            help="Find gaps in competitor content OR analyze your website for off-topic content"
        )
        
        serper_key = st.text_input(
            "Serper API Key", 
            type="password",
            help="Get free key from serper.dev"
        )
        
        if analysis_mode == "🔍 Find Content Gaps":
            st.markdown("**Optional: Reddit API**")
            reddit_id = st.text_input("Reddit Client ID", type="password")
            reddit_secret = st.text_input("Reddit Client Secret", type="password")
            
            keyword = st.text_input("Target Keyword", placeholder="e.g., best seedbox")
            num_competitors = st.slider("Competitors", 3, 12, 8)
            
            analyze_btn = st.button("🎯 Find Content Gaps", type="primary")
            
        else:  # Website Relevance Analysis
            website_url = st.text_input(
                "Website URL", 
                placeholder="/",
                help="Enter the website URL to analyze for content relevance"
            )
            target_topic = st.text_input(
                "Main Topic/Niche", 
                placeholder="e.g., digital marketing, web development, fitness",
                help="What should your website be about? We'll find content that doesn't match."
            )
            
            # Advanced options
            with st.expander("⚙️ Advanced Crawl Settings"):
                crawl_mode = st.radio(
                    "Crawling Mode:",
                    ["🌐 Entire Website (Recommended)", "📊 Limited Crawl"],
                    help="Entire website uses sitemaps and intelligent crawling. Limited crawl stops at a specific number."
                )
                
                if crawl_mode == "📊 Limited Crawl":
                    max_pages = st.slider("Max Pages to Analyze", 10, 500, 100)
                else:
                    max_pages = None
                    st.info("✅ Will analyze up to 500 pages (performance limit) using sitemaps and intelligent crawling")
                
                # Performance warning
                st.warning("⚠️ **Performance Notice**: Large websites (500+ pages) may take 15-30 minutes to analyze. Consider using Limited Crawl for faster results.")
                
                st.markdown("""
                **Crawling Strategy:**
                - 🗺️ **Sitemap Discovery**: Automatically finds and parses XML sitemaps
                - 🔗 **Link Following**: Discovers pages through internal links (if no sitemap)
                - 🚫 **Smart Filtering**: Skips images, PDFs, and duplicate content
                - ⚡ **Batch Processing**: Efficiently handles large websites
                - 🛡️ **Safety Limits**: Auto-stops at 500 pages for performance
                """)
            
            analyze_btn = st.button("🎯 Analyze Website Relevance", type="primary")
        
        # Sidebar footer with your branding
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; color: #666; font-size: 12px;'>

        </div>
        """, unsafe_allow_html=True)
    
    # Info
    with st.expander("ℹ️ What makes this different?"):
        if analysis_mode == "🔍 Find Content Gaps":
            st.markdown("""
            **Real data sources:**
            - 🔍 **Search Suggestions**: Google Autocomplete data
            - 💬 **Reddit Mining**: Real user questions  
            - 📊 **Content Depth**: Competitor weaknesses
            - 🎯 **Vector Analysis**: AI finds missed topics
            
            **Why it works:**
            - Uses actual user behavior data, not guesses
            - AI-powered semantic analysis finds hidden gaps
            - Actionable recommendations with difficulty scores
            """)
        else:
            st.markdown("""
            **Website Relevance Analysis:**
            - 🕷️ **Website Crawling**: Analyzes your ENTIRE website intelligently
            - 🎯 **Vector Similarity**: AI compares content to your main topic
            - 📊 **Relevance Scoring**: Identifies off-topic content
            - 🔍 **Topic Extraction**: Shows what each page is actually about
            
            **Advanced Crawling:**
            - 🗺️ **Sitemap Discovery**: Finds and parses XML sitemaps automatically
            - 🔗 **Intelligent Link Following**: Discovers all internal pages
            - 📈 **Scales to Any Size**: Handles websites with 1000+ pages
            - ⚡ **Batch Processing**: Efficient AI analysis
            
            **Why it's useful:**
            - Find content that hurts your SEO focus
            - Identify pages to remove or redirect
            - Maintain topical authority
            - Clean up content strategy
            """)
    
    # Handle different analysis modes
    if analysis_mode == "🔍 Find Content Gaps":
        if not serper_key:
            st.info("👈 Enter Serper API key to start")
            return
        
        if not keyword:
            st.info("👈 Enter a keyword to analyze")
            return
        
        if analyze_btn:
            try:
                analyzer = DataDrivenSEOAnalyzer(serper_key, reddit_id, reddit_secret)
                results = analyzer.run_analysis(keyword, num_competitors)
                fig, gaps, competitor_topics, competitor_urls, reddit_topics, search_topics, depth_gaps, actionable_topics = results
                
                # Display results
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    if fig:
                        # Display the chart with selection capability
                        event = st.plotly_chart(fig, use_container_width=True, key="main_chart")
                        
                        # Check for clicked points
                        if st.session_state.get('clicked_point'):
                            st.subheader("🎯 Selected Point Details")
                            point_data = st.session_state.clicked_point
                            
                            st.write(f"**Type:** {point_data.get('trace_name', 'Unknown')}")
                            st.write(f"**Topic:** {point_data.get('text', 'N/A')}")
                            
                            if point_data.get('url'):
                                st.write(f"**URL:** [{point_data['url']}]({point_data['url']})")
                                st.code(point_data['url'], language=None)
                            
                            if st.button("Clear Selection"):
                                del st.session_state.clicked_point
                                st.rerun()
                        
                        # Instructions for users
                        st.info("💡 **Tip:** Click on legend items to show/hide data types. Use the legend toggle functionality to focus on specific data sources!")
                        
                    else:
                        st.error("No data found for visualization")
                
                with col2:
                    st.subheader("🎯 Actionable Content Ideas")
                    
                    for i, topic in enumerate(actionable_topics[:8], 1):
                        with st.expander(f"#{i} {topic['title'][:50]}... (Score: {topic['opportunity_score']:.0f})"):
                            st.write(f"**📝 Topic:** {topic['title']}")
                            st.write(f"**🎯 Difficulty:** {topic['difficulty']}")
                            st.write(f"**💡 Why gap:** {topic['why_gap']}")
                            st.write(f"**📋 Angle:** {topic['content_angle']}")
                            
                            if topic['source'] == 'reddit' and topic['upvotes'] > 0:
                                st.write(f"**👍 Engagement:** {topic['upvotes']} upvotes")
                            
                            st.caption(f"Source: {topic['source'].replace('_', ' ').title()}")
                    
                    st.subheader("📊 Data Sources")
                    st.metric("Reddit Questions", len(reddit_topics))
                    st.metric("Search Suggestions", len(search_topics))
                    st.metric("Thin Content Gaps", len(depth_gaps))
                    st.metric("Total Opportunities", len(actionable_topics))
                    
                    st.subheader("🏢 Competitors Analyzed")
                    for i, url in enumerate(competitor_urls, 1):
                        domain = url.split('/')[2].replace('www.', '')
                        st.write(f"**{i}.** [{domain}]({url})")
            
            except Exception as e:
                st.error(f"Error during analysis: {str(e)}")
                st.exception(e)
    
    else:  # Website Relevance Analysis
        if not website_url:
            st.info("👈 Enter a website URL to analyze")
            return
        
        if not target_topic:
            st.info("👈 Enter your main topic/niche")
            return
        
        if analyze_btn:
            try:
                analyzer = DataDrivenSEOAnalyzer(serper_key or "dummy", "", "")  # Dummy key for website analysis
                relevance_data = analyzer.analyze_website_relevance(website_url, target_topic, max_pages)
                
                if 'error' in relevance_data:
                    st.error(relevance_data['error'])
                    return
                
                # Display results
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader(f"🎯 Website Relevance Analysis")
                    
                    # Create and display visualization
                    fig = analyzer.create_relevance_visualization(relevance_data)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Show detailed results
                    st.subheader("📄 Page-by-Page Analysis")
                    
                    # Filter options
                    show_filter = st.selectbox(
                        "Show pages:",
                        ["All Pages", "Irrelevant Only", "Somewhat Relevant", "Highly Relevant"]
                    )
                    
                    filtered_pages = relevance_data['pages']
                    if show_filter != "All Pages":
                        filtered_pages = [p for p in relevance_data['pages'] 
                                        if p['relevance_status'] == show_filter.replace(" Only", "")]
                    
                    for i, page in enumerate(filtered_pages, 1):
                        status_emoji = {"Irrelevant": "🔴", "Somewhat Relevant": "🟡", "Highly Relevant": "🟢"}
                        emoji = status_emoji.get(page['relevance_status'], "⚪")
                        
                        with st.expander(f"{emoji} {page['title'][:60]}... (Similarity: {page['similarity_score']:.1%})"):
                            st.write(f"**📊 Relevance:** {page['relevance_status']} ({page['similarity_score']:.1%} similar)")
                            
                            # Show boost if applied
                            if 'original_similarity' in page and page['original_similarity'] != page['similarity_score']:
                                st.write(f"**🚀 AI Boost:** Original: {page['original_similarity']:.1%} → Boosted: {page['similarity_score']:.1%}")
                            
                            st.write(f"**🌍 Language:** {page.get('language', 'Unknown')}")
                            st.write(f"**📄 Word Count:** {page['word_count']} words")
                            st.write(f"**🔗 URL:** [{page['url']}]({page['url']})")
                            st.write(f"**🏷️ Main Topics:** {', '.join(page['main_topics'])}")
                            st.write(f"**📝 Preview:** {page['content_preview']}")
                            
                            if page['relevance_status'] == 'Irrelevant':
                                st.warning("💡 **Recommendation:** Consider removing, redirecting, or rewriting this page to match your main topic.")
                            elif page['relevance_status'] == 'Somewhat Relevant':
                                st.info("💡 **Recommendation:** Consider optimizing this page to better align with your main topic.")
                
                with col2:
                    st.subheader("📊 Summary")
                    
                    total_pages = relevance_data['total_pages']
                    irrelevant = relevance_data['irrelevant_pages']
                    somewhat = relevance_data['somewhat_relevant']
                    relevant = relevance_data['highly_relevant']
                    
                    st.metric("Total Pages Analyzed", total_pages)
                    st.metric("🔴 Irrelevant Pages", f"{irrelevant} ({irrelevant/total_pages:.1%})")
                    st.metric("🟡 Somewhat Relevant", f"{somewhat} ({somewhat/total_pages:.1%})")
                    st.metric("🟢 Highly Relevant", f"{relevant} ({relevant/total_pages:.1%})")
                    
                    # Language breakdown
                    if 'languages_detected' in relevance_data:
                        st.subheader("🌍 Languages Detected")
                        languages = relevance_data['languages_detected']
                        for lang in languages:
                            lang_pages = len([p for p in relevance_data['pages'] if p.get('language') == lang])
                            st.write(f"**{lang}:** {lang_pages} pages")
                    
                    # Recommendations
                    st.subheader("💡 Recommendations")
                    
                    if irrelevant > 0:
                        st.warning(f"**{irrelevant} pages** are off-topic and may hurt your SEO focus.")
                    
                    if irrelevant > total_pages * 0.3:
                        st.error("⚠️ **High Alert:** Over 30% of your content is irrelevant to your main topic!")
                    elif irrelevant > total_pages * 0.1:
                        st.warning("⚠️ **Warning:** Over 10% of your content is off-topic.")
                    else:
                        st.success("✅ **Good:** Most of your content stays on-topic!")
                    
                    st.markdown("**Action Items:**")
                    if irrelevant > 0:
                        st.write(f"- Remove or redirect {irrelevant} irrelevant pages")
                    if somewhat > 0:
                        st.write(f"- Optimize {somewhat} somewhat relevant pages")
                    st.write(f"- Keep creating content like your {relevant} highly relevant pages")
                    
                    # Multilingual notice
                    if len(relevance_data.get('languages_detected', [])) > 1:
                        st.info("🌍 **Multilingual Site Detected**: The tool now handles multiple languages better. Non-English content is evaluated fairly.")
            
            except Exception as e:
                st.error(f"Error during website analysis: {str(e)}")
                st.exception(e)
    
    # Footer
    st.markdown("""
    <div class='footer'>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

