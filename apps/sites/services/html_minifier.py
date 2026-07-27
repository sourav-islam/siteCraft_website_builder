import re
from bs4 import BeautifulSoup


class HTMLMinifier:
    """Simple HTML minifier for learning purposes."""

    def minify(self, html):
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")
        # Use .body if user uploaded a full <html> doc, else whole soup (fragment case)
        repaired = str(soup.body) if soup.body else str(soup)

        # 1) Collapse whitespace BETWEEN tags:  ">   <"  →  "><"
        collapsed = re.sub(r">\s+<", "><", repaired)
        # 2) Collapse runs of 2+ spaces inside text content to single space
        collapsed = re.sub(r"\s{2,}", " ", collapsed)
        return collapsed.strip()