from apps.sites.services import PageService as _PageService


class PageService:
    @staticmethod
    def create_page(**vd):  return _PageService.create_page(**vd)
    @staticmethod
    def update_page(inst, **vd):  return _PageService.update_page(inst, **vd)