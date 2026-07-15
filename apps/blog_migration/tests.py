import os
from unittest.mock import patch

import requests
from django.test import TestCase

from apps.blog_migration.services.exporter import ExporterService


class ExporterServiceTests(TestCase):
    @patch("apps.blog_migration.services.exporter.requests.get")
    def test_export_uses_certifi_bundle_when_environment_bundle_is_invalid(
        self,
        mock_get,
    ):
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = "<html>ok</html>"

        with patch.dict(
            os.environ,
            {"REQUESTS_CA_BUNDLE": "/home/w3e37/certs/company-ca.crt"},
            clear=False,
        ):
            with patch(
                "apps.blog_migration.services.exporter.certifi.where",
                return_value="/tmp/certs.pem",
            ):
                ExporterService.export(
                    "https://docs.google.com/document/d/abc123/edit"
                )

        self.assertEqual(mock_get.call_args.kwargs["verify"], "/tmp/certs.pem")

    @patch("apps.blog_migration.services.exporter.requests.get")
    def test_export_retries_without_verification_when_ssl_check_fails(
        self,
        mock_get,
    ):
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.text = "<html>ok</html>"
        mock_get.side_effect = [
            requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED"),
            mock_response,
        ]

        with patch(
            "apps.blog_migration.services.exporter.certifi.where",
            return_value="/tmp/certs.pem",
        ):
            ExporterService.export(
                "https://docs.google.com/document/d/abc123/edit"
            )

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_get.call_args_list[1].kwargs["verify"], False)
