"""
Management command: run_loop
Starts the autonomous workflow loop. Blocks until Ctrl-C.

Usage:
    python manage.py run_loop                  # all active products
    python manage.py run_loop --product-id=1   # single product
    python manage.py run_loop --once           # single iteration then exit
"""
import signal
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the autonomous workflow loop (blocks until Ctrl-C)."

    def add_arguments(self, parser):
        parser.add_argument("--product-id", type=int, default=None,
                            help="Limit loop to a single product.")
        parser.add_argument("--schema", type=str, default=None,
                            help="Limit loop to a single tenant schema (default: all tenants).")
        parser.add_argument("--once", action="store_true",
                            help="Run a single iteration then exit.")

    def handle(self, *args, **options):
        from apps.workflow.autonomous.loop import AutonomousLoop

        loop = AutonomousLoop()
        product_id = options.get("product_id")
        schema = options.get("schema")
        run_once = options.get("once", False)

        if run_once:
            self.stdout.write("Running one loop iteration…")
            if schema:
                from django_tenants.utils import schema_context
                with schema_context(schema):
                    summary = loop.run_once(product_id=product_id)
            else:
                summary = loop.iterate_all_tenants(product_id=product_id)
            self.stdout.write(self.style.SUCCESS(f"Done: {summary}"))
            return

        def _shutdown(sig, frame):
            self.stdout.write("\nStopping autonomous loop…")
            loop.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        self.stdout.write(self.style.SUCCESS(
            "Autonomous loop starting. Press Ctrl-C to stop."
        ))
        loop.start()

        # Keep main thread alive
        loop._thread.join()
