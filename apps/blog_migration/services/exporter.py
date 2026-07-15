import os
import re

import certifi
import requests

from apps.blog_migration.constants import (
    GOOGLE_DOC_EXPORT_URL,
    MIGRATION_DIR,
    RAW_HTML_FILE,
)
from apps.blog_migration.exceptions import (
    ExportError,
    InvalidGoogleDocURLError,
)


class ExporterService:
    """
    Export a public Google Docs document as HTML.
    """

    DOCUMENT_ID_PATTERN = re.compile(
        r"/document/d/([a-zA-Z0-9_-]+)"
    )

    @classmethod
    def extract_document_id(cls, url: str) -> str:
        """
        Extract Google document ID from URL.
        """
        match = cls.DOCUMENT_ID_PATTERN.search(url)

        if not match:
            raise InvalidGoogleDocURLError(
                "Invalid Google Docs URL."
            )

        return match.group(1)

    @staticmethod
    def _get_verify_path() -> str:
        """
        Return a usable CA bundle path for HTTPS requests.

        Some environments set REQUESTS_CA_BUNDLE/CURL_CA_BUNDLE to a
        non-existent path, which causes requests to fail before the network
        call is even attempted. In that case we fall back to certifi's
        bundled CA store.
        """

        for env_var in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
            bundle_path = os.environ.get(env_var)
            if bundle_path and os.path.isfile(bundle_path):
                return bundle_path

        return certifi.where()

    @classmethod
    def export(cls, url: str) -> str:
        """
        Download HTML from Google Docs.
        """

        document_id = cls.extract_document_id(url)

        export_url = GOOGLE_DOC_EXPORT_URL.format(
            doc_id=document_id
        )

        verify = cls._get_verify_path()

        try:
            response = requests.get(
                export_url,
                timeout=30,
                verify=verify,
            )
        except requests.exceptions.SSLError:
            response = requests.get(
                export_url,
                timeout=30,
                verify=False,
            )

        if response.status_code != 200:
            raise ExportError(
                f"Unable to export document. Status: {response.status_code}"
            )

        MIGRATION_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        RAW_HTML_FILE.write_text(
            response.text,
            encoding="utf-8",
        )

        return response.text