from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Dict
import re


class ParserService:
    @classmethod
    def parse_google_doc_html(cls, html: str) -> Dict:
        soup = BeautifulSoup(html, "lxml")
        
        title = cls._extract_title(soup)
        content = cls._extract_content(soup)
        images = cls._extract_images(soup)
        
        return {
            "title": title,
            "content": str(content),
            "images": images
        }

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.text.strip()
        
        first_h1 = soup.find("h1")
        if first_h1:
            return first_h1.text.strip()
        
        return "Untitled Blog Post"

    @staticmethod
    def _extract_content(soup: BeautifulSoup) -> BeautifulSoup:
        body = soup.find("body")
        if not body:
            return BeautifulSoup("", "lxml")
        
        return body

    @staticmethod
    def _extract_images(soup: BeautifulSoup) -> List[Dict]:
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "")
            if src:
                images.append({
                    "src": src,
                    "alt": alt
                })
        return images
