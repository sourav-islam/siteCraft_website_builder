# Changelog

## [Unreleased]

### Tasks
- Initial changelog file created for tracking future updates.

### Details
- Changelog will be updated with completed work items and implementation notes as the project progresses.

## [Unreleased] Date : 

## problem 1 : trailing-slash & top-level pages

### Fixed
- **API routing**: Nested pages under sites (`/api/v1/sites/<site_id>/pages`)
  instead of a top-level `/api/v1/pages/` resource. Site is now resolved
  from the URL, not the request body.
- **URL consistency**: Removed trailing slashes from all API endpoints and
  disabled `APPEND_SLASH` to prevent silent redirects on writes.

### Changed
- `PageSerializer.site` is now read-only.

