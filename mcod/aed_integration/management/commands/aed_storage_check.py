from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify the configured private Replit App Storage bucket is reachable."

    def handle(self, *args, **options):
        try:
            from replit.object_storage import Client

            Client().exists("__mcod_app_storage_health_check__")
        except Exception as exc:
            raise CommandError(
                "Replit App Storage is enabled but its default bucket is unavailable."
            ) from exc
        self.stdout.write("Replit App Storage is reachable.")
