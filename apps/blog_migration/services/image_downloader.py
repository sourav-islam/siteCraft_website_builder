import os
import requests
from pathlib import Path
from django.core.files import File
from django.conf import settings
from tempfile import NamedTemporaryFile

from apps.blog_migration.models import BlogPost, BlogImage
from apps.blog_migration.exceptions import ExportError


class ImageDownloaderService:
    @classmethod
    def download_images(cls, blog_post: BlogPost, images: list) -> list:
        downloaded_images = []
        
        for idx, image_data in enumerate(images):
            try:
                downloaded_image = cls._download_single_image(
                    blog_post,
                    image_data,
                    idx
                )
                downloaded_images.append(downloaded_image)
            except Exception as e:
                continue
        
        return downloaded_images

    @classmethod
    def _download_single_image(cls, blog_post: BlogPost, image_data: dict, index: int) -> BlogImage:
        src = image_data["src"]
        alt = image_data.get("alt", "")
        
        response = requests.get(src, stream=True, timeout=30)
        if response.status_code != 200:
            raise ExportError(f"Failed to download image: {src}")
        
        content_type = response.headers.get("content-type", "")
        extension = cls._get_extension(content_type, src)
        
        with NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        
        try:
            with open(temp_file_path, "rb") as f:
                django_file = File(f)
                blog_image = BlogImage.objects.create(
                    blog_post=blog_post,
                    original_url=src,
                    alt_text=alt
                )
                blog_image.image.save(
                    f"blog_{blog_post.id}_img_{index}{extension}",
                    django_file,
                    save=True
                )
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        
        return blog_image

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
        else:
            return ".jpg"
