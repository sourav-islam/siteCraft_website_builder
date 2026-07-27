from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import transaction
from django.conf import settings
import json

from apps.pages.models import Page

from .html_minifier import HTMLMinifier
from .html_to_json import HTMLToJSONConverter


def _abs_url(request, relative_path):
    """Build absolute URL from a media-relative path like 'assets/sites/1/...'."""
    if not request or not relative_path:
        return relative_path  # caller may not have request, that's OK
    return request.build_absolute_uri(settings.MEDIA_URL + relative_path)


class PublishService:
    """
    Simple publish orchestrator for learning purposes.

    Usage (from a view):
        svc = PublishService(request=request)
        result = svc.publish(site)
        # result includes URLs to each published JSON file.
    """

    def __init__(self, request=None):
        self.minifier = HTMLMinifier()
        self.converter = HTMLToJSONConverter()
        self.request = request  # used for building absolute URLs in return

    # ------------------------------------------------------------------
    # Validation (fail-early)
    # ------------------------------------------------------------------
    def _validate_readiness(self, site, pages):
        if not site.header:
            raise ValidationError("Header HTML file is required to publish.")
        if not site.footer:
            raise ValidationError("Footer HTML file is required to publish.")
        if not pages:
            raise ValidationError(
                "Site must have at least 1 ENABLED page with an html_file uploaded."
            )

    # ------------------------------------------------------------------
    # File IO helpers
    # ------------------------------------------------------------------
    def _read(self, file_field):
        """Read a Django FileField as utf-8 text."""
        with file_field.open("rb") as f:
            return f.read().decode("utf-8")

    def _write_json(self, relative_path, data):
        """Write dict as JSON to media storage. Delete old copy first."""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        if default_storage.exists(relative_path):
            default_storage.delete(relative_path)
        saved_name = default_storage.save(
            relative_path,
            ContentFile(content.encode("utf-8")),
        )
        return saved_name  # usually == relative_path but use storage's return

    # ------------------------------------------------------------------
    # Individual asset writers
    # ------------------------------------------------------------------
    def _write_header(self, site):
        raw = self._read(site.header)
        clean = self.minifier.minify(raw)
        payload = self.converter.convert_header(site, clean)
        path = f"assets/sites/{site.id}/header.json"
        return self._write_json(path, payload)

    def _write_footer(self, site):
        raw = self._read(site.footer)
        clean = self.minifier.minify(raw)
        payload = self.converter.convert_footer(site, clean)
        path = f"assets/sites/{site.id}/footer.json"
        return self._write_json(path, payload)

    def _write_page(self, site, page):
        raw = self._read(page.html_file)
        clean = self.minifier.minify(raw)
        payload = self.converter.convert_page(site, page, clean)
        path = f"assets/sites/{site.id}/pages/{page.slug}.json"
        return self._write_json(path, payload)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def publish(self, site):
        """
        Publish a site:
          1. validate
          2. write all JSON files  (rollback delete if any fail)
          3. update DB statuses     (atomic txn)
          4. return medium envelope + URLs to header/footer/page JSON files.
        """

        # ---- pages filter: enabled + has html_file ----------------------
        # NOTE: model names used in this codebase:
        #   Page.is_enabled       (not .enable)
        #   Page.html_file       (not .html)
        pages = list(
            site.pages
            .filter(is_enabled=True, html_file__isnull=False)
            .exclude(html_file="")
        )

        self._validate_readiness(site, pages)

        written_files = []

        try:
            # ---- write assets ---------------------------------------
            header_path = self._write_header(site)
            written_files.append(header_path)

            footer_path = self._write_footer(site)
            written_files.append(footer_path)

            page_paths = []    # [(page, stored_path)] so we can build per-page URLs
            for page in pages:
                p_path = self._write_page(site, page)
                written_files.append(p_path)
                page_paths.append((page, p_path))

            # ---- DB statuses (atomic, never half-published) ---------
            with transaction.atomic():
                site.status = site.Status.PUBLISHED
                site.save(update_fields=["status", "updated_at"])

                page_ids = [p.pk for p in pages]
                Page.objects.filter(pk__in=page_ids).update(
                    status=Page.Status.PUBLISHED,
                    is_published=True,
                )

        except Exception:
            # Rollback: delete any files we wrote so user can retry cleanly
            for fp in written_files:
                if default_storage.exists(fp):
                    default_storage.delete(fp)
            raise  # re-raise so the view layer returns an error response

        # ---- Build medium success envelope + URLs -----------------------
        req = self.request

        # Per-page result list: page info + its JSON URL
        pages_result = []
        for page, p_path in page_paths:
            pages_result.append({
                "page_id": page.id,
                "title": page.title,
                "slug": page.slug,
                "is_homepage": page.is_homepage,
                "page_type": page.page_type or "standard",
                "asset_path": p_path,
                "asset_url": _abs_url(req, p_path),
            })

        return {
            # Core (matches original spec §5)
            "site_id": site.id,
            "site_name": site.name,
            "status": "published",
            "assets_path": f"assets/sites/{site.id}/",
            "files": written_files,

            # Important URLs you asked for
            "urls": {
                "site_detail": _abs_url(req, None) and
                    req.build_absolute_uri(
                        __import__("django.urls").urls.reverse(
                            "site-detail", args=[site.id]
                        )
                    ) if req else None,
                "header": _abs_url(req, header_path),
                "footer": _abs_url(req, footer_path),
                "pages": [pr["asset_url"] for pr in pages_result],
            },

            # Per-page summary
            "pages_published": len(pages_result),
            "pages": pages_result,
        }