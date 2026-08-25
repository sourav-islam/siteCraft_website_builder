from apps.audit.services import AuditService, diff_fields

from ..models import Site


class SiteService:
    @staticmethod
    def create_site(owner, actor=None, **validated_data):
        site = Site.objects.create(
            owner=owner,
            **validated_data,
        )
        AuditService.log_create(site, actor or owner)
        return site

    @staticmethod
    def update_site(instance, actor=None, **validated_data):
        changes = diff_fields(instance, validated_data)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        AuditService.log_update(instance, actor, changes)

        return instance
