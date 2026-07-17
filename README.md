# SiteCraft Website Builder

SiteCraft Website Builder is a Django backend for managing websites, pages, and
content imports. The project combines a small REST API for authentication, site
management, and page management with a utility app that migrates public Google
Docs content into site pages.

## Overview

This repository currently provides:
- JWT-based authentication
- user-owned site management
- page management with JSON-based content storage
- a Google Docs migration pipeline that imports one or more document tabs into
  the `pages` app
- local media storage for uploaded logos, favicons, and imported page images

The migration utility is especially useful for editorial workflows where content
is drafted in Google Docs and then imported into the builder as HTML content.

## Tech Stack

- Python
- Django 6
- Django REST Framework
- Simple JWT
- PostgreSQL via Docker Compose scaffold
- SQLite for the current checked-in Django settings
- BeautifulSoup4 + lxml for HTML parsing
- Requests for remote export/download operations
- Pillow for image support

## Project Structure

```text
siteCraft_website_builder/
├── apps/
│   ├── accounts/         # Custom user model and auth endpoints
│   ├── common/           # Shared permissions, validators, exceptions
│   ├── sites/            # Website/site models and API
│   ├── pages/            # Page models and API
│   └── blog_migration/   # Google Docs export/import pipeline
├── config/               # Django settings, root URLs, WSGI/ASGI
├── media/                # Generated during runtime
├── docker-compose.yml    # PostgreSQL service definition
├── requirements.txt
└── manage.py
```

## Application Breakdown

### accounts
- Defines a custom `User` model
- Exposes JWT auth endpoints through `api/auth/`

### sites
- Stores a user-owned site record
- Supports draft, published, and archived statuses
- Stores branding assets such as `logo` and `favicon`

### pages
- Stores site pages
- Uses a `JSONField` for flexible page content
- Supports homepage and publish flags
- Enforces unique slug per site

### blog_migration
- Accepts a public Google Docs URL plus one or more tab IDs
- Exports each tab as HTML
- Parses title, content, and image references
- Downloads or decodes images
- Cleans the exported HTML
- Creates one `Page` record per tab

### common
- Holds reusable utilities such as permissions and validation helpers

## API Summary

### Authentication
- `POST /api/auth/token/`
- `POST /api/auth/token/refresh/`

### Sites
- `GET /api/sites/`
- `POST /api/sites/`
- `GET /api/sites/<id>/`
- `PUT/PATCH /api/sites/<id>/`
- `DELETE /api/sites/<id>/`

### Pages
- `GET /api/pages/`
- `POST /api/pages/`
- `GET /api/pages/<id>/`
- `PUT/PATCH /api/pages/<id>/`
- `DELETE /api/pages/<id>/`

All API routes are protected by authentication by default.

## Data Model Summary

### User
- Custom Django user model
- Uses unique email addresses

### Site
- Belongs to a user
- Contains name, description, status, and branding assets

### Page
- Belongs to a site
- Contains title, slug, JSON content, publish flags, and timestamps
- Stores imported HTML inside `content`, typically as:

```json
{
  "html": "<cleaned html content>"
}
```

## Google Docs Migration Workflow

The migration pipeline lives in the `blog_migration` app and is designed for
public Google Docs documents.

### Input
- Google Docs document URL
- site ID
- comma-separated tab IDs

### Command

```bash
python manage.py migrate_blog "<google-doc-url>" --site-id 1 --tabs "t.0,t.1,t.2"
```

### End-to-End Flow

1. Extract the document ID from the provided Google Docs URL.
2. Build the Google export URL for each tab.
3. Download the exported HTML.
4. Save raw HTML into `media/migration/raw_<tab_id>.html`.
5. Parse the exported HTML to get:
   - page title
   - page body
   - image list
6. Download images from remote URLs or decode base64 data URLs.
7. Save imported images under `media/pages/imports/<slug>/`.
8. Clean Google Docs-specific markup:
   - remove `<style>` tags
   - remove `class`, `id`, and inline `style` attributes
   - unwrap spans
   - remove empty tags
9. Replace image `src` attributes with local media URLs.
10. Create a `Page` record for the selected site.
11. Store the cleaned HTML in `Page.content`.

### Output Artifacts
- Raw exports: `media/migration/`
- Imported images: `media/pages/imports/`
- Database output: rows in `pages_page`

## Local Setup

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd siteCraft_website_builder
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create environment variables

Copy `.env.example` to `.env` and update values as needed.

Example:

```env
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=127.0.0.1,localhost
DB_NAME=database_name
DB_USER=database_user
DB_PASSWORD=database_password
DB_HOST=localhost
DB_PORT=5432
```

## Database Notes

The repository includes PostgreSQL Docker scaffolding in `docker-compose.yml`,
but the current checked-in Django settings are configured to use SQLite:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

That means you currently have two workable development options:

### Option A: Use the current SQLite setup

```bash
python manage.py makemigrations
python manage.py migrate
```

### Option B: Switch settings to PostgreSQL and run Docker

```bash
docker compose up -d
python manage.py makemigrations
python manage.py migrate
```

If you choose PostgreSQL, make sure `config/settings.py` matches the `.env`
database settings.

## Run the Development Server

```bash
python manage.py runserver
```

Admin:
- `http://127.0.0.1:8000/admin/`

## Typical Development Flow

1. Start the database you intend to use.
2. Install dependencies.
3. Apply migrations.
4. Create a superuser if admin access is needed.
5. Obtain a JWT token through the auth endpoints.
6. Create a site through the API.
7. Create pages manually or import them from Google Docs.
8. Verify output in:
   - admin
   - database
   - `media/` artifacts

## Example Migration Run

```bash
python manage.py migrate_blog \
  "https://docs.google.com/document/d/<doc-id>/edit" \
  --site-id 1 \
  --tabs "t.0,t.1,t.2"
```

Expected console flow per tab:
- `Exporting...`
- `Parsing...`
- `Downloading images...`
- `Cleaning content...`
- `Creating page...`
- `Page created with ID: N`

## Current Limitations

- Google Docs tab IDs must currently be collected manually.
- Migration assumes the document is publicly accessible.
- Imported content is stored as raw cleaned HTML inside a JSON wrapper.
- Frontend rendering behavior for `{"html": ...}` depends on the consuming app.
- Production-grade media serving is not yet documented in this repository.
- Automated test coverage is still minimal.

## Recommended Improvements

- Add test coverage for exporters, parsers, and command execution.
- Improve image download error reporting.
- Add stronger HTML normalization/sanitization rules.
- Document deployment with PostgreSQL and production media storage.
- Add a renderer contract for imported HTML content.
- Introduce idempotent import behavior or update mode for re-imports.

## Useful Commands

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py migrate_blog "<doc-url>" --site-id 1 --tabs "t.0"
```

## License

Add a project license if this repository is intended for redistribution or team
use beyond internal development.
