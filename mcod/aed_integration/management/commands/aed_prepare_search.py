from django.core.management.base import BaseCommand
from django_elasticsearch_dsl.registries import registry


class Command(BaseCommand):
    help = "Create missing MCOD catalog search indexes without deleting existing indexes."

    def handle(self, *args, **options):
        models = {
            model for model in registry.get_models()
            if model._meta.app_label in ("organizations", "datasets", "resources")
        }
        created = False
        for index in registry.get_indices(models):
            if not index.exists():
                index.create()
                created = True
                self.stdout.write("Created missing MCOD catalog search index.")
        if created:
            for document in registry.get_documents(models):
                document().update(document().get_queryset())
            self.stdout.write("Populated catalog indexes from existing MCOD records.")
