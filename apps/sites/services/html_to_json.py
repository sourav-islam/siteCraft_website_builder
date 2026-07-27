class HTMLToJSONConverter:
    """Simple HTML → JSON wrapper for published assets (learning-mode)."""

    def convert_header(self, site, html):
        return {
            "site_id": site.id,
            "site_name": site.name,
            "type": "header",
            "html": html,
        }

    def convert_footer(self, site, html):
        return {
            "site_id": site.id,
            "site_name": site.name,
            "type": "footer",
            "html": html,
        }

    def convert_page(self, site, page, html):
        return {
            "site_id": site.id,
            "page_id": page.id,
            "slug": page.slug,
            "title": page.title,
            "meta_description": page.meta_description or "",
            "page_type": page.page_type or "standard",
            "html": html,
        }