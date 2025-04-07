import os
import datetime
import time
import base64
import hashlib
import random
import sys
from datetime import datetime, UTC
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import feedparser
import ssl
from bs4 import BeautifulSoup
import requests
from time import mktime
from sqlalchemy import func
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3
import atexit

if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rss_reader.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('rss_reader')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gizli-anahtar-buraya')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///rssreader.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['FEED_UPDATE_INTERVAL'] = 30
app.config['DEFAULT_API_KEY'] = os.environ.get('DEFAULT_API_KEY', 'api-key-buraya')

db = SQLAlchemy(app)
migrate = Migrate(app, db)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/117.0.2045.47 Safari/537.36'
]

@app.before_request
def _db_connect():
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI'] and not hasattr(g, 'sqlite_db'):
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        g.sqlite_db = sqlite3.connect(db_path)
        g.sqlite_db.execute('PRAGMA foreign_keys = ON;')

def api_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API anahtarı gereklidir'}), 401
        
        key = APIKey.query.filter_by(key=api_key, is_active=True).first()
        
        if not key and api_key != app.config['DEFAULT_API_KEY']:
            return jsonify({'error': 'Geçersiz API anahtarı'}), 401
            
        if key:
            key.last_used = datetime.now(UTC)
            db.session.commit()
            
        return f(*args, **kwargs)
    return decorated

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    last_used = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    def __init__(self, name="Default API Key"):
        self.key = base64.b64encode(os.urandom(32)).decode('utf-8')
        self.name = name
    
    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'is_active': self.is_active
        }

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    
    feeds = db.relationship('Feed', backref='category', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'feed_count': len(self.feeds)
        }

class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    feed_url = db.Column(db.String(500), nullable=False)
    site_url = db.Column(db.String(500), nullable=True)
    icon = db.Column(db.Text, nullable=True)
    
    etag_header = db.Column(db.String(150), nullable=True)
    last_modified_header = db.Column(db.String(150), nullable=True)
    
    username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    
    disabled = db.Column(db.Boolean, default=False)
    
    checked_at = db.Column(db.DateTime, nullable=True)
    last_modified = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    parsing_error_count = db.Column(db.Integer, default=0)
    parsing_error_msg = db.Column(db.Text, nullable=True)
    
    entries = db.relationship('Entry', backref='feed', lazy=True, cascade="all, delete-orphan")
    
    def to_dict(self):
        category_title = self.category.title if self.category else None
        return {
            'id': self.id,
            'title': self.title,
            'site_url': self.site_url,
            'feed_url': self.feed_url,
            'category': {
                'id': self.category_id, 
                'title': category_title
            } if self.category_id else None,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None,
            'disabled': self.disabled,
            'parsing_error_count': self.parsing_error_count,
            'entry_count': len(self.entries)
        }

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('feed.id'), nullable=False)
    
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    
    author = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text, nullable=True)
    
    hash = db.Column(db.String(40), nullable=False)
    guid = db.Column(db.String(760), nullable=True)
    
    media_items = db.relationship('EntryMedia', backref='entry', lazy=True, cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'feed_id': self.feed_id,
            'title': self.title,
            'url': self.url,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'created_at': self.created_at.isoformat(),
            'author': self.author,
            'feed': {
                'id': self.feed.id,
                'title': self.feed.title,
                'site_url': self.feed.site_url,
                'feed_url': self.feed.feed_url,
                'category': {
                    'id': self.feed.category_id,
                    'title': self.feed.category.title if self.feed.category else None
                } if self.feed.category_id else None
            }
        }
    
    def to_dict_with_content(self):
        entry_dict = self.to_dict()
        entry_dict['content'] = self.content
        entry_dict['media'] = [media.to_dict() for media in self.media_items]
        return entry_dict

class EntryMedia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id', ondelete='CASCADE'), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    type = db.Column(db.String(50), default='image')
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    is_thumbnail = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'type': self.type,
            'width': self.width,
            'height': self.height,
            'is_thumbnail': self.is_thumbnail
        }

class Proxy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    proxy_type = db.Column(db.String(20), default='http')
    is_active = db.Column(db.Boolean, default=True)
    last_used = db.Column(db.DateTime, nullable=True)
    error_count = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'host': self.host,
            'port': self.port,
            'proxy_type': self.proxy_type,
            'is_active': self.is_active,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'error_count': self.error_count
        }
    
    def get_proxy_url(self):
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{self.proxy_type}://{auth}{self.host}:{self.port}"

class FeedProxy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('feed.id'), nullable=False)
    proxy_id = db.Column(db.Integer, db.ForeignKey('proxy.id'), nullable=False)
    is_default = db.Column(db.Boolean, default=True)

def generate_entry_hash(item):
    if 'guid' in item and item.guid:
        value = item.guid
    elif 'id' in item and item.id:
        value = item.id
    elif 'link' in item:
        value = item.link
    else:
        value = item.title + str(int(time.time()))
    
    return hashlib.sha1(value.encode('utf-8')).hexdigest()

def clean_html(html_content):
    if not html_content:
        return ""
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for tag in soup.find_all(['script', 'iframe', 'style']):
            tag.decompose()
        
        for img in soup.find_all('img'):
            img['loading'] = 'lazy'
            if 'class' in img.attrs:
                img['class'] = img.get('class', []) + ['img-fluid']
            else:
                img['class'] = 'img-fluid'
                
        for a in soup.find_all('a', href=True):
            a['target'] = '_blank'
            a['rel'] = 'noopener noreferrer'
            
        return str(soup)
    except Exception as e:
        logger.error(f"HTML temizleme hatası: {str(e)}")
        return html_content

def extract_content(entry):
    if 'content' in entry and entry.content:
        for content in entry.content:
            if 'value' in content:
                return clean_html(content.value)
    
    if 'summary' in entry:
        return clean_html(entry.summary)
    
    return ""

def extract_media_content(entry):
    media_items = []
    
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media:
                media_item = {
                    'url': media['url'],
                    'type': media.get('medium', 'image'),
                    'width': media.get('width'),
                    'height': media.get('height'),
                    'is_thumbnail': False
                }
                media_items.append(media_item)
    
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        for thumbnail in entry.media_thumbnail:
            if 'url' in thumbnail:
                media_item = {
                    'url': thumbnail['url'],
                    'type': 'image',
                    'width': thumbnail.get('width'),
                    'height': thumbnail.get('height'),
                    'is_thumbnail': True
                }
                media_items.append(media_item)
    
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'href' in enclosure:
                media_item = {
                    'url': enclosure['href'],
                    'type': enclosure.get('type', ''),
                    'length': enclosure.get('length'),
                    'is_thumbnail': False
                }
                media_items.append(media_item)
    
    if not media_items and hasattr(entry, 'content') and entry.content:
        try:
            for content in entry.content:
                if 'value' in content:
                    soup = BeautifulSoup(content.value, 'html.parser')
                    images = soup.find_all('img')
                    for img in images:
                        if img.get('src'):
                            media_item = {
                                'url': img['src'],
                                'type': 'image',
                                'width': img.get('width'),
                                'height': img.get('height'),
                                'alt': img.get('alt', ''),
                                'is_thumbnail': False,
                                'extracted_from_html': True
                            }
                            media_items.append(media_item)
                            break
        except Exception as e:
            logger.error(f"HTML'den medya çıkarma hatası: {str(e)}")
    
    return media_items

def extract_author(entry):
    if 'author_detail' in entry and entry.author_detail:
        if 'name' in entry.author_detail:
            return entry.author_detail.name
    
    if 'author' in entry:
        return entry.author
        
    return None

def extract_publish_date(entry):
    if 'published_parsed' in entry and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed))
    
    if 'updated_parsed' in entry and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed))
        
    return datetime.now(UTC)

def extract_site_url(feed_data):
    if 'link' in feed_data.feed:
        return feed_data.feed.link
        
    return None

def get_realistic_headers(feed_url):
    parsed_url = urlparse(feed_url)
    domain = parsed_url.netloc
    
    user_agent = random.choice(USER_AGENTS)
    
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Referer': f'https://www.google.com/search?q={domain}',
        'DNT': '1',
    }
    
    return headers

def get_proxy_for_feed(feed_id):
    feed_proxy = FeedProxy.query.filter_by(feed_id=feed_id).first()
    
    if feed_proxy:
        proxy = Proxy.query.filter_by(id=feed_proxy.proxy_id, is_active=True).first()
        if proxy:
            proxy.last_used = datetime.now(UTC)
            db.session.commit()
            return {
                proxy.proxy_type: proxy.get_proxy_url()
            }
    
    proxy = Proxy.query.filter_by(is_active=True).order_by(func.random()).first()
    
    if proxy:
        proxy.last_used = datetime.now(UTC)
        db.session.commit()
        return {
            proxy.proxy_type: proxy.get_proxy_url()
        }
    
    return None

def report_proxy_error(proxy_id):
    proxy = Proxy.query.get(proxy_id)
    if proxy:
        proxy.error_count += 1
        
        if proxy.error_count >= 5:
            proxy.is_active = False
            logger.warning(f"Proxy devre dışı bırakıldı (çok fazla hata): {proxy.host}:{proxy.port}")
        
        db.session.commit()

def rotate_proxies():
    proxies = Proxy.query.filter_by(is_active=True).all()
    if not proxies:
        return None
    
    proxy = random.choice(proxies)
    proxy.last_used = datetime.now(UTC)
    db.session.commit()
    
    return {
        proxy.proxy_type: proxy.get_proxy_url()
    }

def fetch_feed(feed_obj):
    logger.info(f"Feed çekiliyor: {feed_obj.title} (ID: {feed_obj.id})")
    
    headers = get_realistic_headers(feed_obj.feed_url)
    
    if feed_obj.etag_header:
        headers['If-None-Match'] = feed_obj.etag_header
    
    if feed_obj.last_modified_header:
        headers['If-Modified-Since'] = feed_obj.last_modified_header
    
    auth = None
    if feed_obj.username and feed_obj.password:
        auth = (feed_obj.username, feed_obj.password)
    
    try:
        time.sleep(random.uniform(0.5, 2.0))
        
        response = requests.head(
            feed_obj.feed_url, 
            headers=headers, 
            auth=auth, 
            timeout=30, 
            verify=False,
            proxies=get_proxy_for_feed(feed_obj.id)
        )
        
        if response.status_code == 304:
            feed_obj.checked_at = datetime.now(UTC)
            feed_obj.parsing_error_count = 0
            db.session.commit()
            logger.info(f"Feed değişmemiş: {feed_obj.title}")
            return None
        
        response = requests.get(
            feed_obj.feed_url, 
            headers=headers, 
            auth=auth, 
            timeout=30, 
            verify=False,
            proxies=get_proxy_for_feed(feed_obj.id)
        )
        response.raise_for_status()
        
        if 'ETag' in response.headers:
            feed_obj.etag_header = response.headers['ETag']
        
        if 'Last-Modified' in response.headers:
            feed_obj.last_modified_header = response.headers['Last-Modified']
        
        feed_data = feedparser.parse(response.content)
        
        if hasattr(feed_data, 'bozo_exception'):
            feed_obj.parsing_error_count += 1
            feed_obj.parsing_error_msg = str(feed_data.bozo_exception)
            feed_obj.checked_at = datetime.now(UTC)
            db.session.commit()
            logger.warning(f"Feed çekilirken hata: {feed_obj.title} - {feed_obj.parsing_error_msg}")
            
            if not feed_data.entries:
                return None
        
        site_url = extract_site_url(feed_data)
        if site_url and not feed_obj.site_url:
            feed_obj.site_url = site_url
            
        if 'title' in feed_data.feed and not feed_obj.title:
            feed_obj.title = feed_data.feed.title
        
        feed_obj.checked_at = datetime.now(UTC)
        feed_obj.parsing_error_count = 0
        db.session.commit()
        
        logger.info(f"Feed başarıyla çekildi: {feed_obj.title} - {len(feed_data.entries)} yazı")
        return feed_data
        
    except Exception as e:
        feed_obj.parsing_error_count += 1
        feed_obj.parsing_error_msg = str(e)
        feed_obj.checked_at = datetime.now(UTC)
        db.session.commit()
        logger.error(f"Feed çekilirken istisna: {feed_obj.title} - {str(e)}")
        return None

def add_feed_entries(feed_obj, feed_data):
    if not feed_data or not feed_data.entries:
        return 0
    
    new_entries_count = 0
    for item in feed_data.entries:
        entry_hash = generate_entry_hash(item)
        
        existing_entry = Entry.query.filter_by(feed_id=feed_obj.id, hash=entry_hash).first()
        if existing_entry:
            continue
            
        guid = None
        if hasattr(item, 'guid'):
            guid = item.guid
        elif hasattr(item, 'id'):
            guid = item.id
            
        published_at = extract_publish_date(item)
        content = extract_content(item)
        author = extract_author(item)
        media_content = extract_media_content(item)
        
        new_entry = Entry(
            feed_id=feed_obj.id,
            title=getattr(item, 'title', 'Başlıksız'),
            url=getattr(item, 'link', ''),
            author=author,
            content=content,
            published_at=published_at,
            hash=entry_hash,
            guid=guid
        )
        
        db.session.add(new_entry)
        db.session.flush()
        
        for media in media_content:
            new_media = EntryMedia(
                entry_id=new_entry.id,
                url=media['url'],
                type=media.get('type', 'image'),
                width=media.get('width'),
                height=media.get('height'),
                is_thumbnail=media.get('is_thumbnail', False)
            )
            db.session.add(new_media)
        
        new_entries_count += 1
    
    db.session.commit()
    logger.info(f"Feed için {new_entries_count} yeni yazı eklendi: {feed_obj.title}")
    return new_entries_count

def fetch_all_feeds():
    logger.info("Tüm feed'ler güncelleniyor...")
    feeds = Feed.query.filter_by(disabled=False).all()
    
    total_feeds = len(feeds)
    updated_feeds = 0
    total_new_entries = 0
    
    for feed in feeds:
        try:
            feed_data = fetch_feed(feed)
            if feed_data:
                new_entries = add_feed_entries(feed, feed_data)
                total_new_entries += new_entries
                updated_feeds += 1
        except Exception as e:
            logger.error(f"Feed güncellenirken beklenmeyen hata: {feed.title} - {str(e)}")
            continue
    
    logger.info(f"Feed güncelleme tamamlandı: {updated_feeds}/{total_feeds} feed güncellendi, toplam {total_new_entries} yeni yazı")
    return updated_feeds, total_new_entries

scheduler = None

def fetch_all_feeds_with_context():
    with app.app_context():
        return fetch_all_feeds()

def start_scheduler():
    global scheduler
    if not scheduler or not getattr(scheduler, 'running', False):
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            fetch_all_feeds_with_context,  
            'interval', 
            minutes=app.config['FEED_UPDATE_INTERVAL'],
            id='fetch_all_feeds',
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"Zamanlayıcı başlatıldı: Her {app.config['FEED_UPDATE_INTERVAL']} dakikada bir feedler güncellenecek")

def shutdown_scheduler():
    global scheduler
    if scheduler and getattr(scheduler, 'running', False):
        try:
            scheduler.shutdown()
            logger.info("Zamanlayıcı kapatıldı")
        except Exception as e:
            logger.error(f"Zamanlayıcı kapatılırken hata: {str(e)}")

def setup_initial_config():
    db.create_all()
    
    if not APIKey.query.first() and app.config['DEFAULT_API_KEY']:
        default_key = APIKey(name="Varsayılan API Anahtarı")
        default_key.key = app.config['DEFAULT_API_KEY']
        db.session.add(default_key)
        db.session.commit()
        logger.info("Varsayılan API anahtarı oluşturuldu")
    
    if not Category.query.first():
        default_category = Category(title="Genel")
        db.session.add(default_category)
        db.session.commit()
        logger.info("Varsayılan kategori oluşturuldu")

@app.route('/')
def index():
    return redirect(url_for('feeds'))

@app.route('/categories', methods=['GET'])
def categories():
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)

@app.route('/categories/add', methods=['GET', 'POST'])
def add_category():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        
        if not title:
            flash('Kategori başlığı boş olamaz.', 'error')
            return redirect(url_for('add_category'))
            
        category = Category(title=title)
        db.session.add(category)
        db.session.commit()
        
        flash(f'"{title}" kategorisi eklendi.', 'success')
        return redirect(url_for('categories'))
        
    return render_template('add_category.html')

@app.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        
        if not title:
            flash('Kategori başlığı boş olamaz.', 'error')
            return redirect(url_for('edit_category', category_id=category.id))
            
        category.title = title
        db.session.commit()
        
        flash('Kategori güncellendi.', 'success')
        return redirect(url_for('categories'))
        
    return render_template('edit_category.html', category=category)

@app.route('/categories/<int:category_id>/delete', methods=['POST'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    
    for feed in category.feeds:
        feed.category_id = None
    
    db.session.delete(category)
    db.session.commit()
    
    flash('Kategori silindi.', 'success')
    return redirect(url_for('categories'))

@app.route('/feeds', methods=['GET'])
def feeds():
    show_disabled = 'show_disabled' in request.args
    
    feeds_query = Feed.query
    if not show_disabled:
        feeds_query = feeds_query.filter_by(disabled=False)
        
    feeds = feeds_query.order_by(Feed.title).all()
    
    categories = Category.query.all()
    
    return render_template('feeds.html', feeds=feeds, categories=categories, show_disabled=show_disabled)

@app.route('/feeds/add', methods=['GET', 'POST'])
def add_feed():
    categories = Category.query.all()
    
    if request.method == 'POST':
        feed_url = request.form.get('feed_url', '').strip()
        category_id = request.form.get('category_id')
        
        if not feed_url:
            flash('Feed URL boş olamaz.', 'error')
            return redirect(url_for('add_feed'))
            
        try:
            parsed_url = urlparse(feed_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                flash('Geçersiz URL formatı.', 'error')
                return redirect(url_for('add_feed'))
        except:
            flash('Geçersiz URL formatı.', 'error')
            return redirect(url_for('add_feed'))
            
        existing_feed = Feed.query.filter_by(feed_url=feed_url).first()
        if existing_feed:
            flash('Bu feed zaten eklenmiş.', 'error')
            return redirect(url_for('feeds'))
            
        new_feed = Feed(
            category_id=category_id if category_id else None,
            title='Yükleniyor...',
            feed_url=feed_url
        )
        
        db.session.add(new_feed)
        db.session.commit()
        
        try:
            feed_data = feedparser.parse(feed_url)
            
            if feed_data.bozo:
                new_feed.parsing_error_count = 1
                new_feed.parsing_error_msg = str(feed_data.bozo_exception)
            
            if hasattr(feed_data, 'feed') and hasattr(feed_data.feed, 'title'):
                new_feed.title = feed_data.feed.title
                
            if hasattr(feed_data, 'feed') and hasattr(feed_data.feed, 'link'):
                new_feed.site_url = feed_data.feed.link
                
            new_feed.checked_at = datetime.now(UTC)
            db.session.commit()
            
            entry_count = add_feed_entries(new_feed, feed_data)
            
            flash(f'Feed başarıyla eklendi. {entry_count} yeni yazı bulundu.', 'success')
            return redirect(url_for('feeds'))
            
        except Exception as e:
            new_feed.parsing_error_count = 1
            new_feed.parsing_error_msg = str(e)
            db.session.commit()
            
            flash(f'Feed eklendi ancak içerik çekilirken hata oluştu: {str(e)}', 'warning')
            return redirect(url_for('feeds'))
            
    return render_template('add_feed.html', categories=categories)

@app.route('/feeds/<int:feed_id>/edit', methods=['GET', 'POST'])
def edit_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    categories = Category.query.all()
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category_id = request.form.get('category_id')
        site_url = request.form.get('site_url', '').strip()
        feed_url = request.form.get('feed_url', '').strip()
        disabled = 'disabled' in request.form
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        feed.title = title
        feed.category_id = category_id if category_id else None
        feed.site_url = site_url
        feed.feed_url = feed_url
        feed.disabled = disabled
        feed.username = username
        
        if password:
            feed.password = password
        
        db.session.commit()
        
        flash('Feed güncellendi.', 'success')
        return redirect(url_for('feeds'))
        
    return render_template('edit_feed.html', feed=feed, categories=categories)

@app.route('/feeds/<int:feed_id>/refresh', methods=['POST'])
def refresh_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    
    try:
        feed_data = fetch_feed(feed)
        if feed_data:
            entry_count = add_feed_entries(feed, feed_data)
            flash(f'Feed güncellendi. {entry_count} yeni yazı bulundu.', 'success')
        else:
            flash('Feed güncellendi ancak yeni yazı bulunmadı.', 'info')
    except Exception as e:
        flash(f'Feed güncellenirken hata oluştu: {str(e)}', 'error')
    
    next_url = request.args.get('next', url_for('feeds'))
    return redirect(next_url)

@app.route('/feeds/<int:feed_id>/delete', methods=['POST'])
def delete_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    
    db.session.delete(feed)
    db.session.commit()
    
    flash('Feed silindi.', 'success')
    return redirect(url_for('feeds'))

@app.route('/refresh_all', methods=['POST'])
def refresh_all_feeds():
    updated_feeds, total_new_entries = fetch_all_feeds()
    
    flash(f'Tüm feed\'ler güncellendi. {updated_feeds} feed güncellendi ve toplam {total_new_entries} yeni yazı bulundu.', 'success')
    
    next_url = request.args.get('next', url_for('feeds'))
    return redirect(next_url)

@app.route('/entries/<int:entry_id>', methods=['GET'])
def view_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    return render_template('entry.html', entry=entry)

@app.route('/api_keys', methods=['GET'])
def api_keys():
    keys = APIKey.query.all()
    return render_template('api_keys.html', keys=keys)

@app.route('/api_keys/add', methods=['GET', 'POST'])
def add_api_key():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        
        if not name:
            flash('API anahtarı adı boş olamaz.', 'error')
            return redirect(url_for('add_api_key'))
            
        key = APIKey(name=name)
        db.session.add(key)
        db.session.commit()
        
        flash(f'"{name}" API anahtarı oluşturuldu.', 'success')
        return redirect(url_for('api_keys'))
        
    return render_template('add_api_key.html')

@app.route('/api_keys/<int:key_id>/toggle', methods=['POST'])
def toggle_api_key(key_id):
    key = APIKey.query.get_or_404(key_id)
    
    key.is_active = not key.is_active
    db.session.commit()
    
    status = 'aktifleştirildi' if key.is_active else 'devre dışı bırakıldı'
    flash(f'"{key.name}" API anahtarı {status}.', 'success')
    return redirect(url_for('api_keys'))

@app.route('/api_keys/<int:key_id>/delete', methods=['POST'])
def delete_api_key(key_id):
    key = APIKey.query.get_or_404(key_id)
    
    db.session.delete(key)
    db.session.commit()
    
    flash('API anahtarı silindi.', 'success')
    return redirect(url_for('api_keys'))

@app.route('/proxies', methods=['GET'])
def list_proxies():
    proxies = Proxy.query.all()
    return render_template('proxies.html', proxies=proxies)

@app.route('/proxies/add', methods=['GET', 'POST'])
def add_proxy():
    if request.method == 'POST':
        host = request.form.get('host', '').strip()
        port = request.form.get('port', 0, type=int)
        username = request.form.get('username', '').strip() or None
        password = request.form.get('password', '').strip() or None
        proxy_type = request.form.get('proxy_type', 'http')
        
        if not host or not port:
            flash('Host ve port gereklidir.', 'error')
            return redirect(url_for('add_proxy'))
        
        proxy = Proxy(
            host=host,
            port=port,
            username=username,
            password=password,
            proxy_type=proxy_type
        )
        
        db.session.add(proxy)
        db.session.commit()
        
        flash('Proxy başarıyla eklendi.', 'success')
        return redirect(url_for('list_proxies'))
    
    return render_template('add_proxy.html')

@app.route('/proxies/<int:proxy_id>/toggle', methods=['POST'])
def toggle_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    
    proxy.is_active = not proxy.is_active
    db.session.commit()
    
    status = 'etkinleştirildi' if proxy.is_active else 'devre dışı bırakıldı'
    flash(f'Proxy {status}.', 'success')
    return redirect(url_for('list_proxies'))

@app.route('/proxies/<int:proxy_id>/delete', methods=['POST'])
def delete_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    
    FeedProxy.query.filter_by(proxy_id=proxy_id).delete()
    
    db.session.delete(proxy)
    db.session.commit()
    
    flash('Proxy başarıyla silindi.', 'success')
    return redirect(url_for('list_proxies'))

@app.route('/feeds/<int:feed_id>/proxy', methods=['GET', 'POST'])
def assign_feed_proxy(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    proxies = Proxy.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        proxy_id = request.form.get('proxy_id', 0, type=int)
        
        FeedProxy.query.filter_by(feed_id=feed_id).delete()
        
        if proxy_id > 0:
            feed_proxy = FeedProxy(feed_id=feed_id, proxy_id=proxy_id)
            db.session.add(feed_proxy)
            db.session.commit()
            
            proxy = Proxy.query.get(proxy_id)
            flash(f'Feed için proxy atandı: {proxy.host}:{proxy.port}', 'success')
        else:
            flash('Feed için özel proxy ataması kaldırıldı. Varsayılan proxy havuzu kullanılacak.', 'info')
            db.session.commit()
        
        return redirect(url_for('edit_feed', feed_id=feed_id))
    
    current_assignment = FeedProxy.query.filter_by(feed_id=feed_id).first()
    current_proxy_id = current_assignment.proxy_id if current_assignment else None
    
    return render_template('assign_proxy.html', feed=feed, proxies=proxies, current_proxy_id=current_proxy_id)

@app.route('/api/categories', methods=['GET'])
@api_auth_required
def api_categories():
    categories = Category.query.all()
    return jsonify([category.to_dict() for category in categories])

@app.route('/api/feeds', methods=['GET'])
@api_auth_required
def api_feeds():
    category_id = request.args.get('category_id')
    
    query = Feed.query.filter_by(disabled=False)
    
    if category_id:
        query = query.filter_by(category_id=category_id)
        
    feeds = query.all()
    return jsonify([feed.to_dict() for feed in feeds])

@app.route('/api/feeds/<int:feed_id>/entries', methods=['GET'])
@api_auth_required
def api_feed_entries(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    entries = Entry.query.filter_by(feed_id=feed_id) \
                .order_by(Entry.published_at.desc()) \
                .paginate(page=page, per_page=per_page, error_out=False)
    
    result = {
        'feed': feed.to_dict(),
        'entries': [entry.to_dict() for entry in entries.items],
        'pagination': {
            'page': entries.page,
            'per_page': entries.per_page,
            'total': entries.total,
            'pages': entries.pages,
            'has_next': entries.has_next,
            'has_prev': entries.has_prev
        }
    }
    
    return jsonify(result)

@app.route('/api/categories/<int:category_id>/entries', methods=['GET'])
@api_auth_required
def api_category_entries(category_id):
    category = Category.query.get_or_404(category_id)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    feed_ids = [feed.id for feed in category.feeds]
    
    if not feed_ids:
        return jsonify({
            'category': category.to_dict(),
            'entries': [],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': 0,
                'pages': 0,
                'has_next': False,
                'has_prev': False
            }
        })
    
    entries = Entry.query.filter(Entry.feed_id.in_(feed_ids)) \
                .order_by(Entry.published_at.desc()) \
                .paginate(page=page, per_page=per_page, error_out=False)
    
    result = {
        'category': category.to_dict(),
        'entries': [entry.to_dict() for entry in entries.items],
        'pagination': {
            'page': entries.page,
            'per_page': entries.per_page,
            'total': entries.total,
            'pages': entries.pages,
            'has_next': entries.has_next,
            'has_prev': entries.has_prev
        }
    }
    
    return jsonify(result)

@app.route('/api/entries/<int:entry_id>', methods=['GET'])
@api_auth_required
def api_entry(entry_id):
    entry = Entry.query.get_or_404(entry_id)
    return jsonify(entry.to_dict_with_content())

@app.route('/api/entries', methods=['GET'])
@api_auth_required
def api_entries():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    category_id = request.args.get('category_id')
    feed_id = request.args.get('feed_id')
    
    query = Entry.query
    
    if feed_id:
        query = query.filter_by(feed_id=feed_id)
    
    elif category_id:
        feeds = Feed.query.filter_by(category_id=category_id).all()
        feed_ids = [feed.id for feed in feeds]
        if feed_ids:
            query = query.filter(Entry.feed_id.in_(feed_ids))
    
    query = query.order_by(Entry.published_at.desc())
    
    entries = query.paginate(page=page, per_page=per_page, error_out=False)
    
    result = {
        'entries': [entry.to_dict() for entry in entries.items],
        'pagination': {
            'page': entries.page,
            'per_page': entries.per_page,
            'total': entries.total,
            'pages': entries.pages,
            'has_next': entries.has_next,
            'has_prev': entries.has_prev
        }
    }
    
    return jsonify(result)

@app.route('/api/status', methods=['GET'])
@api_auth_required
def api_status():
    feed_count = Feed.query.filter_by(disabled=False).count()
    category_count = Category.query.count()
    entry_count = Entry.query.count()
    
    latest_checked = Feed.query.filter(Feed.checked_at.isnot(None)) \
                        .order_by(Feed.checked_at.desc()) \
                        .first()
    
    latest_entry = Entry.query.order_by(Entry.created_at.desc()).first()
    
    return jsonify({
        'feeds': {
            'total': feed_count,
            'latest_checked': latest_checked.checked_at.isoformat() if latest_checked else None
        },
        'categories': {
            'total': category_count
        },
        'entries': {
            'total': entry_count,
            'latest': latest_entry.created_at.isoformat() if latest_entry else None
        },
        'update_interval': app.config['FEED_UPDATE_INTERVAL']
    })

_is_first_request = True

@app.before_request
def before_request_handler():
    global _is_first_request
    if _is_first_request:
        with app.app_context():
            start_scheduler()
        _is_first_request = False

if __name__ == '__main__':
    with app.app_context():
        setup_initial_config()
        start_scheduler()
    atexit.register(shutdown_scheduler)
    app.run(debug=True)