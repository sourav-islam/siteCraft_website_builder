import re

from bs4 import BeautifulSoup


def minify_html(html):
    """Minify HTML without importing Django models or services."""
    soup = BeautifulSoup(html, "html.parser")
    repaired = str(soup.body or soup)

    collapsed = re.sub(r">\s+<", "><", repaired)
    collapsed = re.sub(r"\s{2,}", " ", collapsed)
    return collapsed.strip()
