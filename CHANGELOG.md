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