from .models import Site


class SiteService:

    @staticmethod
    def create_site(owner, **validated_data):
        return Site.objects.create(
            owner=owner,
            **validated_data,
        )