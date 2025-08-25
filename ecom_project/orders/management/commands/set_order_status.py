# orders/management/commands/set_order_statuses.py
import random
from django.core.management.base import BaseCommand
from orders.models import Order, OrderStatus

class Command(BaseCommand):
    help = (
        "Map old statuses to new enum and randomly set 60% of confirmed orders "
        "to DELIVERED, 30% CANCELED_STORE, 10% CANCELED_CLIENT (direct update for testing)."
    )

    def handle(self, *args, **kwargs):
        # Map old statuses to new enum
        pending_orders = Order.objects.filter(order_status="Pending")
        rejected_orders = Order.objects.filter(order_status="Rejected")
        accepted_orders = Order.objects.filter(order_status="Accepted")

        if pending_orders.exists():
            pending_orders.update(order_status=OrderStatus.PENDING)
            self.stdout.write(self.style.SUCCESS(f"Mapped {pending_orders.count()} old 'Pending' orders to PENDING"))

        if rejected_orders.exists():
            rejected_orders.update(order_status=OrderStatus.CANCELED_STORE)
            self.stdout.write(self.style.SUCCESS(f"Mapped {rejected_orders.count()} old 'Rejected' orders to CANCELED_STORE"))

        if accepted_orders.exists():
            accepted_orders.update(order_status=OrderStatus.CONFIRMED)
            self.stdout.write(self.style.SUCCESS(f"Mapped {accepted_orders.count()} old 'Accepted' orders to CONFIRMED"))

        # Fetch all confirmed orders
        confirmed_orders = list(Order.objects.filter(order_status=OrderStatus.CONFIRMED))
        total = len(confirmed_orders)

        if total == 0:
            self.stdout.write(self.style.WARNING("No confirmed orders found for testing."))
            return

        # Shuffle for randomness
        random.shuffle(confirmed_orders)

        # Calculate distribution
        delivered_count = int(total * 0.6)
        canceled_store_count = int(total * 0.3)
        canceled_client_count = total - delivered_count - canceled_store_count

        delivered_orders = confirmed_orders[:delivered_count]
        canceled_store_orders = confirmed_orders[delivered_count:delivered_count + canceled_store_count]
        canceled_client_orders = confirmed_orders[delivered_count + canceled_store_count:]

        # Directly update order_status for testing (bypassing transition_to)
        Order.objects.filter(id__in=[o.id for o in delivered_orders]).update(order_status=OrderStatus.DELIVERED)
        Order.objects.filter(id__in=[o.id for o in canceled_store_orders]).update(order_status=OrderStatus.CANCELED_STORE)
        Order.objects.filter(id__in=[o.id for o in canceled_client_orders]).update(order_status=OrderStatus.CANCELED_CLIENT)

        self.stdout.write(self.style.SUCCESS(
            f"Updated {delivered_count} orders to DELIVERED, "
            f"{canceled_store_count} to CANCELED_STORE, "
            f"{canceled_client_count} to CANCELED_CLIENT."
        ))
