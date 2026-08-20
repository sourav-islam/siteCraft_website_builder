# Changelog

## [Unreleased]

### Tasks
- Initial changelog file created for tracking future updates.

### Details
- Changelog will be updated with completed work items and implementation notes as the project progresses.

## [Unreleased] Date : 31-07-26

## problem 1 : trailing-slash & top-level pages

### Fixed
- **API routing**: Nested pages under sites (`/api/v1/sites/<site_id>/pages`)
  instead of a top-level `/api/v1/pages/` resource. Site is now resolved
  from the URL, not the request body.
- **URL consistency**: Removed trailing slashes from all API endpoints and
  disabled `APPEND_SLASH` to prevent silent redirects on writes.

### Changed
- `PageSerializer.site` is now read-only.

## problem 2 : Remove the content sotrage

### Fixed
- **Page content storage**: Removed the unused `content` JSONField from
  `Page`; `html_file` is now the single source of HTML for the builder,
  publish flow, and blog migration. Blog-migrated pages were previously
  unpublishable since their HTML lived in the wrong field.

### Changed
- `migrate_blog` command now writes HTML into `html_file` instead of
  `content`.

## [Unreleased] Date : 20-08-26

## problem 3 : Site global CSS and published versioning

### Fixed
- **Global CSS upload**: Added the optional `Site.global_css` file field with
  file-size and `.css` extension validation. CSS files are stored under
  `media/sites/global_css/`.
- **Versioned publishing**: Added `SiteVersion` with sequential version
  numbers per site and a database uniqueness constraint for
  `(site, version_number)`.
- **Immutable media output**: Publishing now writes each site version into
  `media/published/<site-name>-<site-id>/versions/<version>/` without
  overwriting previous versions.
- **Current version pointer**: Added atomic `current.json` updates after the
  published files and manifest have been generated and validated.
- **Rollback**: Added `POST /api/v1/sites/<site_id>/rollback` with ownership,
  published-version, manifest, and file-existence validation.
- **Rollback safety**: Rollback updates only `current.json`; newer published
  versions remain available and unchanged.
- **Concurrency protection**: Site-row locking with PostgreSQL
  `select_for_update()` prevents duplicate version allocation for concurrent
  publishes of the same site.

### Changed
- `POST /api/v1/sites/<site_id>/publish` now returns the published site,
  version number, and status instead of reusable asset paths.
- Added dynamic `manifest.json` generation for header, footer, global CSS, and
  page files.
- Added the `rolled_back` audit action and rollback migration.
- Corrected site URL patterns to use Django-compatible paths without leading
  slashes.
- Added publishing and rollback tests for version creation, rollback,
  ownership, failed publishing, file preservation, and per-site numbering.

### Validation
- Python compilation, editor diagnostics, and `git diff --check` passed.
- Django tests could not run in the active interpreter because
  `python-dotenv` is not installed.