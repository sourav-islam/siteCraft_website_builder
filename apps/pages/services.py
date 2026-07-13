from .models import Page


class PageService:
    """
    Business logic for Page operations.
    """

    @staticmethod
    def create_page(**validated_data):
        return Page.objects.create(**validated_data)

    @staticmethod
    def update_page(instance, **validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        return instance