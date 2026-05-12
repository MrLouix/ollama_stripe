"""Stripe API client for payment and subscription management"""

import stripe
from typing import Dict, Optional
from app.config import settings

# Initialize Stripe with API key
stripe.api_key = settings.stripe_secret_key


async def create_customer(email: str, name: str, metadata: Optional[Dict] = None) -> str:
    """
    Create a Stripe customer.
    
    Args:
        email: Customer email address
        name: Customer name
        metadata: Optional metadata dict
    
    Returns:
        Stripe customer ID
    """
    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata=metadata or {}
    )
    return customer.id


async def create_subscription(
    customer_id: str,
    price_id: str,
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Create a Stripe subscription.
    
    Args:
        customer_id: Stripe customer ID
        price_id: Stripe price ID
        metadata: Optional metadata dict
    
    Returns:
        Dict with subscription_id, item_id, and status
    """
    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        metadata=metadata or {}
    )
    
    return {
        "subscription_id": subscription.id,
        "item_id": subscription["items"]["data"][0]["id"],
        "status": subscription.status,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end
    }


async def create_usage_record(
    subscription_item_id: str,
    quantity: int,
    action: str = "increment"
) -> Dict:
    """
    Create a usage record for metered billing.
    
    Args:
        subscription_item_id: Stripe subscription item ID
        quantity: Usage quantity (e.g., number of tokens)
        action: "increment" or "set"
    
    Returns:
        Usage record details
    """
    usage_record = stripe.SubscriptionItem.create_usage_record(
        subscription_item_id,
        quantity=quantity,
        action=action
    )
    
    return {
        "id": usage_record.id,
        "quantity": usage_record.quantity,
        "timestamp": usage_record.timestamp
    }


async def cancel_subscription(subscription_id: str, immediately: bool = False) -> Dict:
    """
    Cancel a Stripe subscription.
    
    Args:
        subscription_id: Stripe subscription ID
        immediately: If True, cancel immediately. Otherwise, cancel at period end.
    
    Returns:
        Updated subscription details
    """
    if immediately:
        subscription = stripe.Subscription.delete(subscription_id)
    else:
        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True
        )
    
    return {
        "subscription_id": subscription.id,
        "status": subscription.status,
        "cancel_at_period_end": subscription.cancel_at_period_end
    }


async def get_subscription(subscription_id: str) -> Dict:
    """
    Retrieve subscription details from Stripe.
    
    Args:
        subscription_id: Stripe subscription ID
    
    Returns:
        Subscription details
    """
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    return {
        "id": subscription.id,
        "customer": subscription.customer,
        "status": subscription.status,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end
    }


async def create_billing_portal_session(customer_id: str, return_url: str) -> str:
    """
    Create a Stripe billing portal session for customer self-service.
    
    Args:
        customer_id: Stripe customer ID
        return_url: URL to redirect after portal session
    
    Returns:
        Portal session URL
    """
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url
    )
    
    return session.url


async def create_checkout_session(
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    metadata: Optional[Dict] = None
) -> str:
    """
    Create a Stripe Checkout session for new subscriptions.
    
    Args:
        customer_id: Stripe customer ID
        price_id: Stripe price ID
        success_url: URL to redirect on success
        cancel_url: URL to redirect on cancel
        metadata: Optional metadata dict
    
    Returns:
        Checkout session URL
    """
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata=metadata or {}
    )
    
    return session.url


async def list_prices(active: bool = True) -> list:
    """
    List available Stripe prices.
    
    Args:
        active: Only return active prices
    
    Returns:
        List of price objects
    """
    prices = stripe.Price.list(active=active, limit=100)
    
    return [
        {
            "id": price.id,
            "product": price.product,
            "unit_amount": price.unit_amount,
            "currency": price.currency,
            "recurring": price.recurring
        }
        for price in prices.data
    ]


async def retrieve_invoice(invoice_id: str) -> Dict:
    """
    Retrieve invoice details from Stripe.
    
    Args:
        invoice_id: Stripe invoice ID
    
    Returns:
        Invoice details
    """
    invoice = stripe.Invoice.retrieve(invoice_id)
    
    return {
        "id": invoice.id,
        "customer": invoice.customer,
        "subscription": invoice.subscription,
        "status": invoice.status,
        "amount_due": invoice.amount_due,
        "amount_paid": invoice.amount_paid,
        "currency": invoice.currency,
        "created": invoice.created
    }
