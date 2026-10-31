from django.core.management.base import BaseCommand
from django.utils import timezone
from subscriptions.services import close_expired_subscriptions


class Command(BaseCommand):
    help = "Close active subscriptions whose plan has auto_close=True and expiry_date has passed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help="Simulate a specific reference date (YYYY-MM-DD)",
        )

    def handle(self, *args, **options):
        ref_date = None
        if options['date']:
            ref_date = timezone.datetime.strptime(options['date'], "%Y-%m-%d").date()

        count = close_expired_subscriptions(ref_date)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully closed {count} expired subscriptions.")
        )

