import json
import os
import posixpath
import tempfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.text import slugify

from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.common.exceptions import PublishValidationError
from apps.pages.models import Page
from apps.sites.models import Site, SiteVersion
from apps.sites.services.html_minifier import HTMLMinifier
from apps.sites.services.html_to_json import HTMLToJSONConverter


class PublishService:
    def __init__(self):
        self.minifier = HTMLMinifier()
        self.converter = HTMLToJSONConverter()

    def _validate_readiness(self, site, pages):
        if not site.header or not site.footer:
            raise PublishValidationError(
                "Both header and footer HTML are required to publish.",
            )
        if not pages:
            raise PublishValidationError(
                "Site must have at least one enabled page with HTML to publish.",
            )

    def _read(self, file_field):
        with file_field.open("r") as f:
            return f.read()

    def _write_bytes(self, relative_path, content):
        if default_storage.exists(relative_path):
            raise FileExistsError(f"Published file already exists: {relative_path}")
        default_storage.save(relative_path, ContentFile(content))
        return relative_path

    def _write_json(self, relative_path, data):
        content = json.dumps(data, indent=2)
        return self._write_bytes(relative_path, content.encode("utf-8"))

    def _published_root(self, site):
        site_key = f"{slugify(site.name) or 'site'}-{site.id}"
        return f"published/{site_key}"

    def _version_root(self, site, version_number):
        return posixpath.join(
            self._published_root(site),
            "versions",
            str(version_number),
        )

    def _write_header(self, site, version_root):
        raw_html = self._read(site.header)
        clean_html = self.minifier.minify(raw_html)
        data = self.converter.convert_header(site, clean_html)
        path = posixpath.join(version_root, "header.json")
        return self._write_json(path, data)

    def _write_footer(self, site, version_root):
        raw_html = self._read(site.footer)
        clean_html = self.minifier.minify(raw_html)
        data = self.converter.convert_footer(site, clean_html)
        path = posixpath.join(version_root, "footer.json")
        return self._write_json(path, data)

    def _write_global_css(self, site, version_root):
        return self._write_bytes(
            posixpath.join(version_root, "global.css"),
            self._read_bytes(site.global_css),
        )

    def _write_page(self, site, page, version_root):
        raw_html = self._read(page.html_file)
        clean_html = self.minifier.minify(raw_html)
        data = self.converter.convert_page(site, page, clean_html)
        path = posixpath.join(version_root, "pages", f"{page.slug}.json")
        return self._write_json(path, data)

    def _read_bytes(self, file_field):
        with file_field.open("rb") as file:
            return file.read()

    def _write_manifest(self, version_root, version_number, files):
        manifest = {
            "version": version_number,
            "files": files,
        }
        return self._write_json(
            posixpath.join(version_root, "manifest.json"),
            manifest,
        )

    def _write_current(self, site, version_number):
        path = posixpath.join(self._published_root(site), "current.json")
        content = json.dumps({"version": version_number}, indent=2).encode("utf-8")
        absolute_path = default_storage.path(path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(
            dir=os.path.dirname(absolute_path),
            prefix=".current-",
            suffix=".json",
        )
        try:
            with os.fdopen(file_descriptor, "wb") as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, absolute_path)
        except Exception:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise
        return path

    def _required_files_exist(self, files):
        return all(default_storage.exists(path) for path in files)

    def _manifest_file_paths(self, version_root, manifest):
        file_paths = [posixpath.join(version_root, "manifest.json")]

        def collect_files(value):
            if isinstance(value, str):
                if value.startswith("/") or ".." in value.split("/"):
                    raise PublishValidationError(
                        "Published manifest contains an unsafe file path.",
                    )
                file_paths.append(posixpath.normpath(posixpath.join(version_root, value)))
            elif isinstance(value, dict):
                for nested_value in value.values():
                    collect_files(nested_value)

        collect_files(manifest.get("files", {}))
        return file_paths

    def rollback(self, site, version_number, actor=None):
        with transaction.atomic():
            locked_site = Site.objects.select_for_update().get(pk=site.pk)
            version = SiteVersion.objects.filter(
                site=locked_site,
                version_number=version_number,
                status=SiteVersion.Status.PUBLISHED,
            ).first()
            if version is None:
                raise PublishValidationError(
                    "The requested published version does not exist.",
                )

            version_root = self._version_root(locked_site, version_number)
            manifest_path = posixpath.join(version_root, "manifest.json")
            if not default_storage.exists(manifest_path):
                raise PublishValidationError(
                    "The requested published version is incomplete.",
                )

            try:
                with default_storage.open(manifest_path, "r") as manifest_file:
                    manifest = json.load(manifest_file)
                if manifest.get("version") != version_number:
                    raise PublishValidationError(
                        "The requested published version has an invalid manifest.",
                    )
                required_files = self._manifest_file_paths(version_root, manifest)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise PublishValidationError(
                    "The requested published version has an invalid manifest.",
                ) from exc

            if not self._required_files_exist(required_files):
                raise PublishValidationError(
                    "The requested published version is incomplete.",
                )

            self._write_current(locked_site, version_number)

        result = {
            "message": "Site rolled back successfully.",
            "site": site.id,
            "version": version_number,
        }
        AuditService.log_action(
            site,
            actor,
            AuditLog.Action.ROLLED_BACK,
            metadata=result,
        )
        return result

    def publish(self, site, actor=None):
        written_files = []
        try:
            with transaction.atomic():
                locked_site = Site.objects.select_for_update().get(pk=site.pk)
                pages = list(
                    locked_site.pages.filter(
                        is_enabled=True,
                        html_file__isnull=False,
                    ).exclude(html_file=""),
                )
                self._validate_readiness(locked_site, pages)

                last_version = SiteVersion.objects.filter(site=locked_site).order_by("-version_number").first()
                version_number = last_version.version_number + 1 if last_version else 1
                version = SiteVersion.objects.create(
                    site=locked_site,
                    version_number=version_number,
                    created_by=actor,
                )
                version_root = self._version_root(locked_site, version_number)

                header_path = self._write_header(locked_site, version_root)
                footer_path = self._write_footer(locked_site, version_root)
                written_files.extend([header_path, footer_path])

                manifest_files = {
                    "header": "header.json",
                    "footer": "footer.json",
                    "pages": {},
                }
                if locked_site.global_css:
                    css_path = self._write_global_css(locked_site, version_root)
                    written_files.append(css_path)
                    manifest_files["global_css"] = "global.css"

                for page in pages:
                    page_path = self._write_page(
                        locked_site,
                        page,
                        version_root,
                    )
                    written_files.append(page_path)
                    manifest_files["pages"][page.slug] = posixpath.relpath(
                        page_path,
                        version_root,
                    )

                manifest_path = self._write_manifest(
                    version_root,
                    version_number,
                    manifest_files,
                )
                written_files.append(manifest_path)

                if not self._required_files_exist(written_files):
                    raise OSError("Published version is missing required files.")

                version.status = SiteVersion.Status.PUBLISHED
                version.save(update_fields=["status"])
                locked_site.status = locked_site.Status.PUBLISHED
                locked_site.save(update_fields=["status"])
                Page.objects.filter(pk__in=[p.pk for p in pages]).update(
                    status=Page.Status.PUBLISHED,
                )
                self._write_current(locked_site, version_number)
        except Exception:
            for file in written_files:
                if default_storage.exists(file):
                    default_storage.delete(file)

            raise

        result = {
            "message": "Site published successfully.",
            "site": site.id,
            "version": version_number,
            "status": SiteVersion.Status.PUBLISHED,
        }

        AuditService.log_action(site, actor, "published", metadata=result)

        return result
