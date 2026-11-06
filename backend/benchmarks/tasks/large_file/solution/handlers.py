"""Event handlers. One function per event type."""


HANDLERS = {}


def handler(name):
    def register(fn):
        HANDLERS[name] = fn
        return fn
    return register


@handler("order.created")
def handle_order_created(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.updated")
def handle_order_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.cancelled")
def handle_order_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.archived")
def handle_order_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.restored")
def handle_order_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.approved")
def handle_order_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.rejected")
def handle_order_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.paused")
def handle_order_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.resumed")
def handle_order_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.flagged")
def handle_order_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.verified")
def handle_order_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.assigned")
def handle_order_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.merged")
def handle_order_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.exported")
def handle_order_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.imported")
def handle_order_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("order.expired")
def handle_order_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "order"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.created")
def handle_invoice_created(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.updated")
def handle_invoice_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.cancelled")
def handle_invoice_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.archived")
def handle_invoice_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.restored")
def handle_invoice_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.approved")
def handle_invoice_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.rejected")
def handle_invoice_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.paused")
def handle_invoice_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.resumed")
def handle_invoice_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.flagged")
def handle_invoice_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.verified")
def handle_invoice_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.assigned")
def handle_invoice_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.merged")
def handle_invoice_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.exported")
def handle_invoice_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.imported")
def handle_invoice_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("invoice.expired")
def handle_invoice_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "invoice"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.created")
def handle_shipment_created(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.updated")
def handle_shipment_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.cancelled")
def handle_shipment_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.archived")
def handle_shipment_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.restored")
def handle_shipment_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.approved")
def handle_shipment_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.rejected")
def handle_shipment_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.paused")
def handle_shipment_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.resumed")
def handle_shipment_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.flagged")
def handle_shipment_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.verified")
def handle_shipment_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.assigned")
def handle_shipment_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.merged")
def handle_shipment_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.exported")
def handle_shipment_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.imported")
def handle_shipment_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("shipment.expired")
def handle_shipment_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "shipment"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.created")
def handle_customer_created(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.updated")
def handle_customer_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.cancelled")
def handle_customer_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.archived")
def handle_customer_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.restored")
def handle_customer_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.approved")
def handle_customer_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.rejected")
def handle_customer_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.paused")
def handle_customer_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.resumed")
def handle_customer_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.flagged")
def handle_customer_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.verified")
def handle_customer_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.assigned")
def handle_customer_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.merged")
def handle_customer_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.exported")
def handle_customer_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.imported")
def handle_customer_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("customer.expired")
def handle_customer_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "customer"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.created")
def handle_payment_created(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.updated")
def handle_payment_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.cancelled")
def handle_payment_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.archived")
def handle_payment_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.restored")
def handle_payment_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.approved")
def handle_payment_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.rejected")
def handle_payment_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.paused")
def handle_payment_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.resumed")
def handle_payment_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.flagged")
def handle_payment_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.verified")
def handle_payment_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.assigned")
def handle_payment_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.merged")
def handle_payment_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.exported")
def handle_payment_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.imported")
def handle_payment_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("payment.expired")
def handle_payment_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "payment"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.created")
def handle_subscription_created(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.updated")
def handle_subscription_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.cancelled")
def handle_subscription_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.archived")
def handle_subscription_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.restored")
def handle_subscription_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.approved")
def handle_subscription_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.rejected")
def handle_subscription_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.paused")
def handle_subscription_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.resumed")
def handle_subscription_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.flagged")
def handle_subscription_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.verified")
def handle_subscription_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.assigned")
def handle_subscription_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.merged")
def handle_subscription_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.exported")
def handle_subscription_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.imported")
def handle_subscription_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("subscription.expired")
def handle_subscription_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "subscription"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.created")
def handle_coupon_created(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.updated")
def handle_coupon_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.cancelled")
def handle_coupon_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.archived")
def handle_coupon_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.restored")
def handle_coupon_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.approved")
def handle_coupon_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.rejected")
def handle_coupon_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.paused")
def handle_coupon_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.resumed")
def handle_coupon_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.flagged")
def handle_coupon_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.verified")
def handle_coupon_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.assigned")
def handle_coupon_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.merged")
def handle_coupon_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.exported")
def handle_coupon_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.imported")
def handle_coupon_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("coupon.expired")
def handle_coupon_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "coupon"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.created")
def handle_warehouse_created(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.updated")
def handle_warehouse_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.cancelled")
def handle_warehouse_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.archived")
def handle_warehouse_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.restored")
def handle_warehouse_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.approved")
def handle_warehouse_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.rejected")
def handle_warehouse_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.paused")
def handle_warehouse_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.resumed")
def handle_warehouse_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.flagged")
def handle_warehouse_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.verified")
def handle_warehouse_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.assigned")
def handle_warehouse_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.merged")
def handle_warehouse_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.exported")
def handle_warehouse_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.imported")
def handle_warehouse_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("warehouse.expired")
def handle_warehouse_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "warehouse"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.created")
def handle_supplier_created(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.updated")
def handle_supplier_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.cancelled")
def handle_supplier_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.archived")
def handle_supplier_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.restored")
def handle_supplier_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.approved")
def handle_supplier_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.rejected")
def handle_supplier_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.paused")
def handle_supplier_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.resumed")
def handle_supplier_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.flagged")
def handle_supplier_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.verified")
def handle_supplier_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.assigned")
def handle_supplier_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.merged")
def handle_supplier_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.exported")
def handle_supplier_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.imported")
def handle_supplier_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("supplier.expired")
def handle_supplier_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "supplier"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.created")
def handle_return_created(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.updated")
def handle_return_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.cancelled")
def handle_return_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.archived")
def handle_return_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.restored")
def handle_return_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.approved")
def handle_return_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.rejected")
def handle_return_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.paused")
def handle_return_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.resumed")
def handle_return_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.flagged")
def handle_return_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.verified")
def handle_return_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.assigned")
def handle_return_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.merged")
def handle_return_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.exported")
def handle_return_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.imported")
def handle_return_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("return.expired")
def handle_return_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "return"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.created")
def handle_ticket_created(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.updated")
def handle_ticket_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.cancelled")
def handle_ticket_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.archived")
def handle_ticket_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.restored")
def handle_ticket_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.approved")
def handle_ticket_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.rejected")
def handle_ticket_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.paused")
def handle_ticket_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.resumed")
def handle_ticket_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.flagged")
def handle_ticket_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("refund.partial")
def handle_refund_partial(event, store):
    order = store[event["id"]]
    amount = event["amount"]
    if amount <= 0 or amount > order["balance"]:
        raise ValueError("invalid refund amount")
    order["balance"] -= amount
    order["status"] = "refunded" if order["balance"] == 0 else "partially_refunded"
    return order


@handler("ticket.verified")
def handle_ticket_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.assigned")
def handle_ticket_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.merged")
def handle_ticket_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.exported")
def handle_ticket_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.imported")
def handle_ticket_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("ticket.expired")
def handle_ticket_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "ticket"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.created")
def handle_review_created(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.updated")
def handle_review_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.cancelled")
def handle_review_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.archived")
def handle_review_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.restored")
def handle_review_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.approved")
def handle_review_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.rejected")
def handle_review_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.paused")
def handle_review_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.resumed")
def handle_review_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.flagged")
def handle_review_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.verified")
def handle_review_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.assigned")
def handle_review_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.merged")
def handle_review_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.exported")
def handle_review_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.imported")
def handle_review_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("review.expired")
def handle_review_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "review"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.created")
def handle_basket_created(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.updated")
def handle_basket_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.cancelled")
def handle_basket_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.archived")
def handle_basket_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.restored")
def handle_basket_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.approved")
def handle_basket_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.rejected")
def handle_basket_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.paused")
def handle_basket_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.resumed")
def handle_basket_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.flagged")
def handle_basket_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.verified")
def handle_basket_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.assigned")
def handle_basket_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.merged")
def handle_basket_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.exported")
def handle_basket_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.imported")
def handle_basket_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("basket.expired")
def handle_basket_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "basket"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.created")
def handle_wishlist_created(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.updated")
def handle_wishlist_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.cancelled")
def handle_wishlist_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.archived")
def handle_wishlist_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.restored")
def handle_wishlist_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.approved")
def handle_wishlist_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.rejected")
def handle_wishlist_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.paused")
def handle_wishlist_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.resumed")
def handle_wishlist_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.flagged")
def handle_wishlist_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.verified")
def handle_wishlist_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.assigned")
def handle_wishlist_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.merged")
def handle_wishlist_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.exported")
def handle_wishlist_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.imported")
def handle_wishlist_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("wishlist.expired")
def handle_wishlist_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "wishlist"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.created")
def handle_address_created(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.updated")
def handle_address_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.cancelled")
def handle_address_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.archived")
def handle_address_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.restored")
def handle_address_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.approved")
def handle_address_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.rejected")
def handle_address_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.paused")
def handle_address_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.resumed")
def handle_address_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.flagged")
def handle_address_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.verified")
def handle_address_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.assigned")
def handle_address_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.merged")
def handle_address_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.exported")
def handle_address_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.imported")
def handle_address_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("address.expired")
def handle_address_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "address"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.created")
def handle_account_created(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "created"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.updated")
def handle_account_updated(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "updated"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.cancelled")
def handle_account_cancelled(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "cancelled"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.archived")
def handle_account_archived(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "archived"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.restored")
def handle_account_restored(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "restored"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.approved")
def handle_account_approved(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "approved"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.rejected")
def handle_account_rejected(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "rejected"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.paused")
def handle_account_paused(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "paused"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.resumed")
def handle_account_resumed(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "resumed"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.flagged")
def handle_account_flagged(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "flagged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.verified")
def handle_account_verified(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "verified"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.assigned")
def handle_account_assigned(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "assigned"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.merged")
def handle_account_merged(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "merged"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.exported")
def handle_account_exported(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "exported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.imported")
def handle_account_imported(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "imported"
    record.setdefault("history", []).append(event.get("at"))
    return record


@handler("account.expired")
def handle_account_expired(event, store):
    record = store.setdefault(event["id"], {"kind": "account"})
    record["status"] = "expired"
    record.setdefault("history", []).append(event.get("at"))
    return record
