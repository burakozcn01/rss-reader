"""
RSS Reader Client - Comprehensive Usage Guide

This script demonstrates all features of the rssreader-client library,
including working with categories, feeds, entries, system status, and error handling.

Installation:
pip install rssreader-client
"""

from rssreader import RSSClient, APIError, AuthenticationError, ConnectionError
from datetime import datetime, timedelta
import sys

# Configuration
API_URL = "http://localhost:5000"
API_KEY = "apikey"

def print_separator(title):
    """Print a section separator with a title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

def print_section(title):
    """Print a section title."""
    print(f"\n--- {title} ---")

def format_date(date_str):
    """Format an ISO date string to a readable format."""
    if not date_str:
        return "Unknown"
    try:
        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date_obj.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return date_str

# Initialize the client
try:
    client = RSSClient(API_URL, API_KEY)
    print(f"Successfully connected to the RSS Reader API at {API_URL}")
except Exception as e:
    print(f"Failed to initialize the client: {str(e)}")
    sys.exit(1)

# 1. System Status
print_separator("1. System Status")
try:
    status = client.get_status()
    print(f"Total feeds: {status.feed_count}")
    print(f"Total categories: {status.category_count}")
    print(f"Total entries: {status.entry_count}")
    print(f"Feed update interval: {status.update_interval} minutes")
    
    if status.latest_checked:
        print(f"Last feed check: {format_date(status.latest_checked)}")
    
    if status.latest_entry:
        print(f"Latest entry: {format_date(status.latest_entry)}")
except Exception as e:
    print(f"Error getting system status: {str(e)}")

# 2. Background Tasks Status
print_separator("2. Background Tasks Status")
try:
    task_status = client.get_task_status()
    print(f"All feeds update running: {task_status.all_feeds_running}")
    
    if task_status.feed_tasks:
        print(f"Individual feed updates in progress: {len(task_status.feed_tasks)}")
        for feed_id, running in task_status.feed_tasks.items():
            print(f"  - Feed ID {feed_id}: {'Running' if running else 'Not running'}")
    else:
        print("No individual feed updates are currently running")
except Exception as e:
    print(f"Error getting task status: {str(e)}")

# 3. Categories
print_separator("3. Categories")
try:
    categories = client.get_categories()
    print(f"Found {len(categories)} categories:")
    
    for category in categories:
        print(f"ID: {category.id}")
        print(f"Title: {category.title}")
        print(f"Feed count: {category.feed_count}")
        print("-" * 40)
    
    # Store category IDs for later use
    category_ids = [category.id for category in categories] if categories else []
        
except Exception as e:
    print(f"Error getting categories: {str(e)}")
    category_ids = []

# 4. Feeds
print_separator("4. Feeds")
try:
    # 4.1 All feeds
    print_section("4.1 All Feeds")
    feeds = client.get_feeds()
    print(f"Found {len(feeds)} feeds:")
    
    for feed in feeds[:5]:  # Show first 5 feeds
        print(f"ID: {feed.id}")
        print(f"Title: {feed.title}")
        if feed.category:
            print(f"Category: {feed.category.get('title', 'Unknown')}")
        print(f"Feed URL: {feed.feed_url}")
        print(f"Site URL: {feed.site_url}")
        print(f"Last checked: {format_date(feed.checked_at)}")
        print(f"Entry count: {feed.entry_count}")
        print("-" * 40)
    
    if len(feeds) > 5:
        print(f"... and {len(feeds) - 5} more feeds")
    
    # Store feed IDs for later use
    feed_ids = [feed.id for feed in feeds] if feeds else []
    
    # 4.2 Feeds by category
    if category_ids:
        print_section("4.2 Feeds by Category")
        category_id = category_ids[0]  # Use the first category
        category_name = next((cat.title for cat in categories if cat.id == category_id), "Unknown")
        
        category_feeds = client.get_feeds(category_id=category_id)
        print(f"Found {len(category_feeds)} feeds in category '{category_name}':")
        
        for feed in category_feeds[:3]:  # Show first 3 feeds
            print(f"ID: {feed.id}")
            print(f"Title: {feed.title}")
            print(f"Entry count: {feed.entry_count}")
            print("-" * 40)
        
        if len(category_feeds) > 3:
            print(f"... and {len(category_feeds) - 3} more feeds in this category")
    
except Exception as e:
    print(f"Error getting feeds: {str(e)}")
    feed_ids = []

# 5. Entries
print_separator("5. Entries")

# 5.1 All entries (paginated)
print_section("5.1 All Entries (Paginated)")
try:
    page = 1
    per_page = 10
    
    result = client.get_entries(page=page, per_page=per_page)
    entries = result["entries"]
    pagination = result["pagination"]
    
    print(f"Found {pagination.total} entries (showing page {pagination.page} of {pagination.pages}, {per_page} per page):")
    
    for entry in entries[:5]:  # Show first 5 entries
        print(f"ID: {entry.id}")
        print(f"Title: {entry.title}")
        print(f"Feed: {entry.feed.get('title', 'Unknown')}")
        print(f"Published: {format_date(entry.published_at)}")
        print(f"URL: {entry.url}")
        print("-" * 40)
    
    if len(entries) > 5:
        print(f"... and {len(entries) - 5} more entries on this page")
    
    if pagination.pages > 1:
        print(f"\nPagination information:")
        print(f"Current page: {pagination.page}")
        print(f"Total pages: {pagination.pages}")
        print(f"Total entries: {pagination.total}")
        print(f"Entries per page: {pagination.per_page}")
        print(f"Has next page: {pagination.has_next}")
        print(f"Has previous page: {pagination.has_prev}")
except Exception as e:
    print(f"Error getting entries: {str(e)}")

# 5.2 Entries by category
if category_ids:
    print_section("5.2 Entries by Category")
    try:
        category_id = category_ids[0]  # Use the first category
        category_name = next((cat.title for cat in categories if cat.id == category_id), "Unknown")
        
        result = client.get_category_entries(category_id=category_id, page=1, per_page=10)
        entries = result["entries"]
        pagination = result["pagination"]
        category = result["category"]
        
        print(f"Found {pagination.total} entries in category '{category.title if category else category_name}':")
        
        for entry in entries[:3]:  # Show first 3 entries
            print(f"ID: {entry.id}")
            print(f"Title: {entry.title}")
            print(f"Feed: {entry.feed.get('title', 'Unknown')}")
            print(f"Published: {format_date(entry.published_at)}")
            print("-" * 40)
        
        if len(entries) > 3:
            print(f"... and {len(entries) - 3} more entries in this category")
    except Exception as e:
        print(f"Error getting category entries: {str(e)}")

# 5.3 Entries by feed
if feed_ids:
    print_section("5.3 Entries by Feed")
    try:
        feed_id = feed_ids[0]  # Use the first feed
        feed_name = next((feed.title for feed in feeds if feed.id == feed_id), "Unknown")
        
        result = client.get_feed_entries(feed_id=feed_id, page=1, per_page=10)
        entries = result["entries"]
        pagination = result["pagination"]
        feed = result["feed"]
        
        print(f"Found {pagination.total} entries in feed '{feed.title if feed else feed_name}':")
        
        for entry in entries[:3]:  # Show first 3 entries
            print(f"ID: {entry.id}")
            print(f"Title: {entry.title}")
            print(f"Published: {format_date(entry.published_at)}")
            print(f"URL: {entry.url}")
            print("-" * 40)
        
        if len(entries) > 3:
            print(f"... and {len(entries) - 3} more entries in this feed")
    except Exception as e:
        print(f"Error getting feed entries: {str(e)}")

# 6. Single Entry Detail
if feed_ids and len(entries) > 0:
    print_separator("6. Single Entry Detail")
    try:
        entry_id = entries[0].id  # Use the first entry from the previous fetch
        
        entry = client.get_entry(entry_id=entry_id)
        
        print(f"Entry ID: {entry.id}")
        print(f"Title: {entry.title}")
        print(f"Feed: {entry.feed.get('title', 'Unknown')}")
        print(f"Author: {entry.author or 'Unknown'}")
        print(f"Published: {format_date(entry.published_at)}")
        print(f"URL: {entry.url}")
        
        # Content preview
        if entry.content:
            content_length = len(entry.content)
            preview_length = min(200, content_length)
            content_preview = entry.content[:preview_length]
            print(f"\nContent preview ({preview_length} of {content_length} characters):")
            print(f"{content_preview}...")
        
        # Media items
        if entry.media:
            print(f"\nMedia items ({len(entry.media)}):")
            for i, media in enumerate(entry.media[:3], 1):
                print(f"  {i}. Type: {media.get('type', 'Unknown')}")
                print(f"     URL: {media.get('url', 'Unknown')}")
                
                if "width" in media and "height" in media:
                    print(f"     Size: {media.get('width')}x{media.get('height')}")
                    
                if media.get('is_thumbnail'):
                    print(f"     Thumbnail: Yes")
                    
                print()
            
            if len(entry.media) > 3:
                print(f"... and {len(entry.media) - 3} more media items")
    except Exception as e:
        print(f"Error getting entry detail: {str(e)}")

# 7. Advanced Usage Examples
print_separator("7. Advanced Usage Examples")

# 7.1 Recent entries (last 7 days)
print_section("7.1 Recent Entries (Last 7 Days)")
try:
    # Get a larger batch of entries to filter
    result = client.get_entries(per_page=50)
    entries = result["entries"]
    
    # Filter for entries in the last 7 days
    one_week_ago = datetime.now() - timedelta(days=7)
    recent_entries = []
    
    for entry in entries:
        published = entry.published_datetime()
        if published and published > one_week_ago:
            recent_entries.append(entry)
    
    print(f"Found {len(recent_entries)} entries from the last 7 days:")
    for entry in recent_entries[:3]:  # Show first 3 entries
        published = entry.published_datetime()
        date_str = published.strftime("%Y-%m-%d %H:%M:%S") if published else "Unknown"
        
        print(f"- {entry.title}")
        print(f"  Published: {date_str} | Feed: {entry.feed.get('title', 'Unknown')}")
    
    if len(recent_entries) > 3:
        print(f"... and {len(recent_entries) - 3} more recent entries")
except Exception as e:
    print(f"Error in recent entries example: {str(e)}")

# 7.2 Group entries by feeds
print_section("7.2 Group Entries by Feeds")
try:
    result = client.get_entries(per_page=50)
    entries = result["entries"]
    
    feed_groups = {}
    for entry in entries:
        feed_id = entry.feed_id
        feed_title = entry.feed.get('title', 'Unknown')
        
        if feed_id not in feed_groups:
            feed_groups[feed_id] = {
                'title': feed_title,
                'entries': []
            }
        
        feed_groups[feed_id]['entries'].append(entry)
    
    print(f"Grouped {len(entries)} entries by {len(feed_groups)} feeds:")
    for feed_id, group in list(feed_groups.items())[:3]:  # Show first 3 feeds
        print(f"Feed: {group['title']} ({len(group['entries'])} entries)")
        for entry in group['entries'][:2]:  # Show first 2 entries per feed
            print(f"  - {entry.title}")
        
        if len(group['entries']) > 2:
            print(f"    ... and {len(group['entries']) - 2} more entries")
        
        print()
    
    if len(feed_groups) > 3:
        print(f"... and {len(feed_groups) - 3} more feeds")
except Exception as e:
    print(f"Error in grouping example: {str(e)}")

# 8. Error Handling Example
print_separator("8. Error Handling Example")
try:
    print("Attempting to access a non-existent feed (ID: 999999)...")
    result = client.get_feed_entries(feed_id=999999)
    # This should raise an exception
except APIError as e:
    print(f"APIError properly handled:")
    print(f"  Status code: {e.status_code}")
    print(f"  Message: {e.message}")
except AuthenticationError as e:
    print(f"AuthenticationError: {str(e)}")
except ConnectionError as e:
    print(f"ConnectionError: {str(e)}")
except Exception as e:
    print(f"Other error: {str(e)}")

print("\nRSS Reader Client library demonstration complete!")