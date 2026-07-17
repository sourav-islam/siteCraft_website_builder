from bs4 import BeautifulSoup
from typing import List


class ContentCleanerService:
    @classmethod
    def clean_content(cls, html: str, images: List[dict]) -> str:
        soup = BeautifulSoup(html, "lxml")
        cls._remove_google_doc_styles(soup)
        cls._replace_image_urls(soup, images)
        cls._clean_empty_tags(soup)
        return str(soup)

    @staticmethod
    def _remove_google_doc_styles(soup: BeautifulSoup):
        for style in soup.find_all("style"):
            style.decompose()
        for tag in soup.find_all(True):
            for attr in ("class", "id", "style"):
                if attr in tag.attrs:
                    del tag[attr]
        for span in soup.find_all("span"):
            span.unwrap()

    @staticmethod
    def _replace_image_urls(soup: BeautifulSoup, images: List[dict]):
        img_tags = soup.find_all("img")
        for idx, img in enumerate(img_tags):
            if idx < len(images):
                image = images[idx]
                img["src"] = image["url"]
                if image.get("alt"):
                    img["alt"] = image["alt"]

    @staticmethod
    def _clean_empty_tags(soup: BeautifulSoup):
        for tag_name in ("p", "div", "span"):
            for element in soup.find_all(tag_name):
                if not element.get_text(strip=True) and not element.find_all():
                    element.decompose()