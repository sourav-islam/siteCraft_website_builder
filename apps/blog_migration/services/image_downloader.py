import requests
import base64
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.blog_migration.exceptions import ExportError


class ImageDownloaderService:
    @classmethod
    def download_images(cls, images: list, folder: str) -> list:
        downloaded_images = []
        for idx, image_data in enumerate(images):
            try:
                downloaded_images.append(cls._download_single_image(image_data, folder, idx))
            except Exception:
                continue
        return downloaded_images

    @classmethod
    def _download_single_image(cls, image_data: dict, folder: str, index: int) -> dict:
        src = image_data["src"]
        alt = image_data.get("alt", "")
        
        if src.startswith("data:"):
            # Handle data URL
            # Split the data URL: data:[<mediatype>][;base64],<data>
            header, data = src.split(",", 1)
            # Decode the data
            if ";base64" in header:
                image_content = base64.b64decode(data)
            else:
                image_content = data.encode("utf-8")
            
            # Get content type from header
            content_type = header.split(";")[0].split(":")[1] if ";" in header else "image/jpeg"
        else:
            # Handle HTTP URL
            response = requests.get(src, stream=True, timeout=30)
            if response.status_code != 200:
                raise ExportError(f"Failed to download image: {src}")
            image_content = response.content
            content_type = response.headers.get("content-type", "")

        extension = cls._get_extension(content_type, src)
        storage_path = f"pages/imports/{folder}/img_{index}{extension}"
        saved_path = default_storage.save(storage_path, ContentFile(image_content))

        return {
            "original_src": src,
            "url": default_storage.url(saved_path),
            "alt": alt,
        }

    @staticmethod
    def _get_extension(content_type: str, url: str) -> str:
        if "jpeg" in content_type or "jpg" in url:
            return ".jpg"
        elif "png" in content_type or "png" in url:
            return ".png"
        elif "gif" in content_type or "gif" in url:
            return ".gif"
        elif "webp" in content_type or "webp" in url:
            return ".webp"
        return ".jpg"