import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.audit.services import AuditService
from apps.common.exceptions import PublishValidationError
from apps.pages.models import Page
from apps.sites.services.html_minifier import HTMLMinifier
from apps.sites.services.html_to_json import HTMLToJSONConverter


class PublishService:
    def __init__(self):
        self.minifier = HTMLMinifier()
        self.converter = HTMLToJSONConverter()

    def _validate_readiness(self, site, pages):
        if not site.header or not site.footer:
            raise PublishValidationError(
                "Both header and footer HTML are required to publish."
            )
        if not pages:
            raise PublishValidationError(
                "Site must have at least one enabled page with HTML to publish."
            )

    def _read(self, file_field):
        with file_field.open("r") as f:
            return f.read()

    def _write_json(self, relative_path, data):
        content = json.dumps(data, indent=2)
        if default_storage.exists(relative_path):
            default_storage.delete(relative_path)
        default_storage.save(relative_path, ContentFile(content.encode("utf-8")))
        return relative_path

    def _write_header(self, site):
        raw_html = self._read(site.header)
        clean_html = self.minifier.minify(raw_html)
        data = self.converter.convert_header(site, clean_html)
        path = f"assets/sites/{site.id}/header.json"
        return self._write_json(path, data)

    def _write_footer(self, site):
        raw_html = self._read(site.footer)
        clean_html = self.minifier.minify(raw_html)
        data = self.converter.convert_footer(site, clean_html)
        path = f"assets/sites/{site.id}/footer.json"
        return self._write_json(path, data)

    def _write_page(self, site, page):
        raw_html = self._read(page.html_file)
        clean_html = self.minifier.minify(raw_html)
        data = self.converter.convert_page(site, page, clean_html)
        path = f"assets/sites/{site.id}/pages/{page.slug}.json"
        return self._write_json(path, data)

    def publish(self, site, actor=None):
        pages = list(
            site.pages.filter(is_enabled=True, html_file__isnull=False).exclude(html_file="")
        )
        self._validate_readiness(site, pages)

        written_files = []
        try:
            written_files.append(self._write_header(site))
            written_files.append(self._write_footer(site))
            for page in pages:
                written_files.append(self._write_page(site, page))
            site.status = site.Status.PUBLISHED
            site.save(update_fields=["status"])
            Page.objects.filter(pk__in=[p.pk for p in pages]).update(
                status=Page.Status.PUBLISHED
            )
        except Exception:
            for file in written_files:
                if default_storage.exists(file):
                    default_storage.delete(file)

            raise

        result = {
            "site_id": site.id,
            "status": "published",
            "assets_path": f"assets/sites/{site.id}/",
            "files": written_files,
        }

        AuditService.log_action(site, actor, "published", metadata=result)

        return result