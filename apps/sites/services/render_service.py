import json
from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils.text import slugify


class PublishedSiteRenderService:
    """Load one published version and render it from its JSON snapshot."""

    def _published_root(self, site):
        site_key = f"{slugify(site.name) or 'site'}-{site.id}"
        return Path(settings.MEDIA_ROOT) / "published" / site_key

    def _read_json(self, path, error_message):
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
            raise Http404(error_message)

    def _read_text(self, path, error_message):
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            raise Http404(error_message)

    def _relative_path(self, version_root, relative_path):
        if not isinstance(relative_path, str) or not relative_path:
            raise Http404("Published site files are invalid.")

        path = (version_root / relative_path).resolve()
        try:
            path.relative_to(version_root.resolve())
        except ValueError:
            raise Http404("Published site files are invalid.")
        return path

    def _load_file_json(self, version_root, relative_path, error_message):
        return self._read_json(
            self._relative_path(version_root, relative_path),
            error_message,
        )

    def get_context(self, site):
        published_root = self._published_root(site)
        current = self._read_json(
            published_root / "current.json",
            "This site has not been published.",
        )
        version = current.get("version") if isinstance(current, dict) else None
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise Http404("The published site version is invalid.")

        version_root = published_root / "versions" / str(version)
        manifest = self._read_json(
            version_root / "manifest.json",
            "The published site manifest is unavailable.",
        )
        if not isinstance(manifest, dict) or manifest.get("version") != version:
            raise Http404("The published site manifest is invalid.")

        files = manifest.get("files")
        if not isinstance(files, dict):
            raise Http404("The published site manifest is invalid.")

        header = self._load_file_json(
            version_root,
            files.get("header"),
            "The published site header is unavailable.",
        )
        footer = self._load_file_json(
            version_root,
            files.get("footer"),
            "The published site footer is unavailable.",
        )

        pages = files.get("pages")
        if not isinstance(pages, dict) or not pages.get("home"):
            raise Http404("The published homepage is unavailable.")
        homepage = self._load_file_json(
            version_root,
            pages["home"],
            "The published homepage is unavailable.",
        )

        global_css = ""
        if files.get("global_css"):
            global_css = self._read_text(
                self._relative_path(version_root, files["global_css"]),
                "The published stylesheet is unavailable.",
            )

        return {
            "site": site,
            "version": version,
            "manifest": manifest,
            "header": header,
            "homepage": homepage,
            "footer": footer,
            "global_css": global_css,
        }

    def render_homepage(self, request, site):
        return render(
            request,
            "published/site.html",
            self.get_context(site),
        )