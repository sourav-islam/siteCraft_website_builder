# SiteCraft Website Builder

SiteCraft is a Django and Django REST Framework backend for building and
publishing user-owned websites. It provides JWT authentication, site and page
management, editor locks backed by Redis, versioned publishing, audit logging,
and a Google Docs import pipeline.

## Status

This repository is an API backend. It does not include a frontend application
or a complete production deployment stack. PostgreSQL is required; SQLite is
not configured as a fallback.

## Features

- Custom user accounts with JWT access and refresh tokens
- Owner-scoped site and page CRUD APIs
- HTML page files with SEO metadata, page types, homepage flags, and enablement
- Redis-backed site and page edit locks with TTL heartbeat endpoints
- Published site manifests with immutable, numbered versions
- Rollback to an earlier published version
- Read-only audit log for site activity
- Public HTML rendering for published sites
- Import of public Google Docs tabs, including image download and HTML cleanup
- Local media storage separated by `APP_ENV` (`canary`, `beta`, or `production`)

## Technology

- Python `>=3.10`
- Django `6.0.7`
- Django REST Framework `3.17.1`
- Simple JWT
- PostgreSQL `16` (Docker Compose)
- Redis `7` (Docker Compose)
- BeautifulSoup4, lxml, Requests, and Pillow

## Repository Layout

```text
apps/
+-- accounts/           # Users, registration, login, and profiles
+-- audit/              # Site audit log
+-- blog_migration/     # Google Docs export/import services and command
+-- common/             # Shared models, permissions, validators, and health
+-- pages/              # Nested page API and HTML file model
+-- sites/              # Site API, publishing, rendering, and versioning
config/                 # Django settings and root URL configuration
media/                  # Runtime media; generated environment output
docker-compose.yml      # Local PostgreSQL and Redis services
manage.py               # Django administration entry point
requirements.txt        # Pinned runtime and development dependencies
pyproject.toml          # Package metadata and Ruff configuration
```

## Quick Start

### Prerequisites

- Python 3.10 or newer
- Docker Engine and Docker Compose
- Git

### Installation

```bash
git clone https://github.com/sourav-islam/siteCraft_website_builder.git
cd siteCraft_website_builder
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create `.env` in the repository root. The values below match the supplied
Compose services:

```env
APP_ENV=canary
DEBUG=True
SECRET_KEY=replace-me-for-local-development
ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=sitecraft_db
DB_USER=sitecraft_user
DB_PASSWORD=sitecraft_password
DB_HOST=localhost
DB_PORT=5432

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
LOCK_TTL=120
```

`APP_ENV` controls the media directory: files are written under
`media/<APP_ENV>/`. Only `canary`, `beta`, and `production` are accepted.

Start infrastructure, migrate the database, and run Django:

```bash
docker compose up -d
python manage.py check
python manage.py migrate
python manage.py createsuperuser  # optional
python manage.py runserver
```

The local endpoints are:

- API: `http://127.0.0.1:8000/api/v1/`
- Admin: `http://127.0.0.1:8000/admin/`
- Published site: `http://127.0.0.1:8000/sites/<site-id>/published/`

API paths intentionally do not use trailing slashes. `APPEND_SLASH` is
disabled, so clients should use the paths exactly as shown below.

## API

Authentication is required by default. Registration, login, token refresh,
health, and published rendering are public. Site and page resources are scoped
to the authenticated owner.

### Authentication and health

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Create an account |
| `POST` | `/api/v1/auth/login` | Obtain access and refresh tokens |
| `POST` | `/api/v1/auth/login/refresh` | Rotate the access token |
| `GET` | `/api/v1/auth/profile` | Read the current profile |
| `PUT`, `PATCH` | `/api/v1/auth/profile` | Update the current profile |
| `GET` | `/api/v1/health` | Health check |

Registration requires `username`, `email`, `password`, and
`password_confirm`; `first_name` and `last_name` are optional. Send the access
token as `Authorization: Bearer <access-token>`.

### Sites and pages

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/sites` | List or create sites |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/sites/<site-id>` | Manage one site |
| `GET`, `POST`, `DELETE` | `/api/v1/sites/<site-id>/lock` | Read, acquire, or release a site lock |
| `POST` | `/api/v1/sites/<site-id>/heartbeat` | Refresh a site lock TTL |
| `POST` | `/api/v1/sites/<site-id>/publish` | Create a published version |
| `POST` | `/api/v1/sites/<site-id>/rollback` | Point `current.json` to a prior version |
| `GET`, `POST` | `/api/v1/sites/<site-id>/pages` | List or create pages |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/v1/sites/<site-id>/pages/<page-id>` | Manage one page |
| `GET`, `POST`, `DELETE` | `/api/v1/sites/<site-id>/pages/<page-id>/lock` | Read, acquire, or release a page lock |
| `POST` | `/api/v1/sites/<site-id>/pages/<page-id>/heartbeat` | Refresh a page lock TTL |
| `GET` | `/api/v1/sites/<site-id>/audit-log` | Read site audit entries |

Pages are nested under a site. Their `site`, `status`, `is_published`, audit
timestamps, and creator/updater fields are server-managed. A page's HTML is
uploaded through `html_file`; there is no JSON `content` field.

Rollback expects a JSON body containing a positive version number:

```json
{"version": 2}
```

## Publishing and Rendering

Before publishing, a site must have a header, footer, and at least one enabled
page with an HTML file. Publishing creates an immutable version directory and a
`current.json` pointer under:

```text
media/<APP_ENV>/published/<site-name>-<site-id>/
+-- current.json
+-- versions/<version-number>/
  |-- manifest.json
  |-- header.html
  |-- footer.html
  |-- global.css             # when configured
  `-- pages/<page-slug>.html
```

Public rendering uses the current pointer and does not require JWT:

- `GET /sites/<site-id>/published/` renders the `home` page.
- `GET /sites/<site-id>/published/<page-slug>` renders a named page.

The renderer currently reads published files from local storage. Put a reverse
proxy or object storage in front of media for production deployments, and make
sure published-site access is protected at the hosting layer if public access
is not desired.

## Google Docs Import

`migrate_blog` imports tabs from a publicly accessible Google Docs document. It
exports each tab, extracts the title, content, and images, downloads or decodes
image assets, removes Google-specific markup, and creates one draft `Page` per
tab. The cleaned HTML is stored in the page's `html_file`.

```bash
python manage.py migrate_blog \
  "https://docs.google.com/document/d/<document-id>/edit" \
  --site-id 1 \
  --tabs "t.0,t.1,t.2"
```

Imported images and other runtime files are stored below the active environment
media root. Tab IDs must currently be supplied manually, and the source
document must be publicly exportable.

## Development Commands

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test
ruff check .
ruff format --check .
```

The benchmark commands are available when investigating publish performance:

```bash
python manage.py benchmark_sync --site-id 1
python manage.py benchmark_async --site-id 1
python manage.py benchmark_multiprocessing --site-id 1
python manage.py benchmark_sync_io --site-id 1
```

## Production Checklist

- Set `DEBUG=False`, use a strong unique `SECRET_KEY`, and configure every
  hostname in `ALLOWED_HOSTS`.
- Use managed PostgreSQL and Redis or hardened private instances; do not keep
  the Compose credentials in production.
- Run `python manage.py check --deploy` as part of deployment validation.
- Serve media and static files through a web server or object storage.
- Back up PostgreSQL and the media root, including published versions.
- Terminate TLS at the load balancer or reverse proxy.
- Restrict admin access and monitor failed authentication, publishing, and
  migration operations.
- Review HTML upload and rendering policy before accepting untrusted content.

The repository does not currently ship a production web-server configuration,
static/media hosting configuration, CI pipeline, or secret-management setup.
