# RSS Reader

A modern, feature-rich RSS reader application built with Flask and SQLAlchemy. This application allows you to manage RSS feeds, categorize them, and access content through both a web interface and a comprehensive API.

## Features

- **Feed Management**: Add, edit, delete, and refresh RSS feeds
- **Category Organization**: Organize feeds into categories
- **Content Extraction**: Automatically extracts content, authors, and media from feeds
- **Background Processing**: Asynchronous feed updates with threading
- **Scheduled Updates**: Automatic periodic feed refreshing
- **Smart Content Handling**: Cleans HTML content and extracts media items
- **Proxy Support**: Fetch feeds through proxies with automatic rotation
- **User Authentication**: Secure login system with admin privileges
- **API Access**: Comprehensive REST API with key-based authentication
- **OPML Support**: Import and export feeds in OPML format
- **Pagination**: Efficient browsing of large feed collections
- **Error Handling**: Robust error handling for feed parsing issues
- **HTTP Caching**: Utilizes ETag and Last-Modified headers for efficient updates

## Installation

### Prerequisites

- Python 3.7+
- SQLite (default) or another database supported by SQLAlchemy
- pip (Python package manager)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/burakozcn01/rss-reader.git
   cd rss-reader
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create configuration file:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. Initialize the database:
   ```bash
   flask db init
   flask db migrate
   flask db upgrade
   ```

6. Run the application:
   ```bash
   flask run
   ```

7. Access the application at `http://localhost:5000`

## Configuration

Configuration is handled through environment variables or a `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for session security | `gizli-anahtar-buraya` |
| `DATABASE_URL` | Database connection string | `sqlite:///rssreader.db` |
| `FEED_UPDATE_INTERVAL` | Minutes between automatic feed updates | `30` |
| `DEFAULT_API_KEY` | Default API key for API access | `api-key-buraya` |

## Usage

### Initial Login

The application creates a default admin user:
- Username: `admin`
- Password: `password123`

**Important**: Change the default password after first login!

### Adding Feeds

1. Navigate to the "Feeds" section
2. Click "Add Feed"
3. Enter the feed URL and select a category (optional)
4. Submit the form

### Managing Categories

1. Navigate to the "Categories" section
2. Add, edit, or delete categories as needed

### Importing & Exporting Feeds

1. Navigate to the "Feeds" section
2. Use the "Import OPML" or "Export OPML" buttons

### Refreshing Feeds

- To refresh a single feed: Click the refresh button next to the feed
- To refresh all feeds: Click the "Refresh All" button on the feeds page

## API Documentation

The RSS Reader includes a comprehensive REST API. All API endpoints require an API key in the `X-API-Key` header.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/categories` | GET | Get all categories |
| `/api/feeds` | GET | Get all feeds (with optional category filter) |
| `/api/feeds/<id>/entries` | GET | Get entries for a specific feed |
| `/api/categories/<id>/entries` | GET | Get entries for a specific category |
| `/api/entries/<id>` | GET | Get a specific entry with content |
| `/api/entries` | GET | Get entries (with optional filters) |
| `/api/status` | GET | Get system status information |
| `/api/task_status` | GET | Get background task status |

### Example API Usage

```bash
# Get all categories
curl -H "X-API-Key: your-api-key" http://localhost:5000/api/categories

# Get entries from a specific feed
curl -H "X-API-Key: your-api-key" http://localhost:5000/api/feeds/1/entries
```

## Python Client Library

For programmatic access to the RSS Reader, you can use the [rssreader-client](https://pypi.org/project/rssreader-client/) Python library:

```bash
pip install rssreader-client
```

```python
from rssreader import RSSClient

# Initialize client
client = RSSClient("http://localhost:5000", "your-api-key")

# Get all categories
categories = client.get_categories()
for category in categories:
    print(f"{category.id}: {category.title} ({category.feed_count} feeds)")

# Get entries from a specific feed
result = client.get_feed_entries(feed_id=1)
for entry in result["entries"]:
    print(f"- {entry.title}")
```

## Database Schema

The application uses the following main database models:

- **User**: User accounts with authentication
- **Category**: Feed categories
- **Feed**: RSS feeds with metadata
- **Entry**: Feed entries/articles
- **EntryMedia**: Media items associated with entries
- **Proxy**: Proxy servers for feed fetching
- **APIKey**: API keys for API access

## Advanced Features

### Proxy Configuration

The application supports fetching feeds through proxy servers:

1. Navigate to the "Proxies" section
2. Add proxy servers with their connection details
3. Assign specific proxies to feeds or use automatic rotation

### API Key Management

To manage API keys for API access:

1. Navigate to the "API Keys" section
2. Create, activate/deactivate, or delete API keys

## Troubleshooting

### Feed Not Updating

- Check the feed URL is correct and accessible
- Verify the feed has valid RSS/Atom format
- Check proxy settings if using proxies
- View error messages in the feed details

### Database Issues

If you encounter database issues:

```bash
# Reset the database
rm instance/rssreader.db
flask db upgrade
```

### Log Files

The application logs to both console and file:

- Check `rss_reader.log` for detailed error information

## License

This project is licensed under the MIT License - see the LICENSE file for details.