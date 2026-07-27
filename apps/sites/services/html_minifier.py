import re

from bs4 import BeautifulSoup


class HTMLMinifier:
    def minify(self, html):
        soup = BeautifulSoup(html, "html.parser")
        repaired = str(soup.body or soup)

        collapsed = re.sub(r">\s+<", "><", repaired)
        collapsed = re.sub(r"\s{2,}", " ", collapsed)
        return collapsed.strip()
