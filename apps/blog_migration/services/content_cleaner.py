from bs4 import BeautifulSoup
from typing import Dict, List
from django.conf import settings


class ContentCleanerService:
    @classmethod
    def clean_content(cls, html: str, blog_images: List) -> str:
        soup = BeautifulSoup(html, "lxml")
        
        cls._remove_google_doc_styles(soup)
        cls._replace_image_urls(soup, blog_images)
        cls._clean_empty_tags(soup)
        
        return str(soup)

    @staticmethod
    def _remove_google_doc_styles(soup: BeautifulSoup):
        for style in soup.find_all("style"):
            style.decompose()
        
        for tag in soup.find_all(True):
            if "class" in tag.attrs:
                del tag["class"]
            if "id" in tag.attrs:
                del tag["id"]
            if "style" in tag.attrs:
                del tag["style"]
        
        for span in soup.find_all("span"):
            span.unwrap()

    @staticmethod
    def _replace_image_urls(soup: BeautifulSoup, blog_images: List):
        img_tags = soup.find_all("img")
        
        for idx, img in enumerate(img_tags):
            if idx < len(blog_images):
                blog_image = blog_images[idx]
                img["src"] = blog_image.image.url
                if blog_image.alt_text:
                    img["alt"] = blog_image.alt_text

    @staticmethod
    def _clean_empty_tags(soup: BeautifulSoup):
        empty_tags = ["p", "div", "span"]
        for tag in empty_tags:
            for element in soup.find_all(tag):
                if not element.get_text(strip=True) and not element.find_all():
                    element.decompose()
