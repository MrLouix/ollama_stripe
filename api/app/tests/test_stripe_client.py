"""
Unit tests for Stripe client service.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.stripe_client import (
    create_customer,
    create_subscription,
    cancel_subscription,
    create_billing_portal_session,
    create_usage_record,
    list_prices,
    get_subscription,
)


@pytest.mark.asyncio
async def test_create_customer_success():
    """Test creating a Stripe customer successfully."""
    with patch("stripe.Customer.create") as mock_create:
        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"
        mock_create.return_value = mock_customer
        
        customer_id = await create_customer(
            email="test@example.com",
            name="Test User",
            metadata={"tenant_id": "abc123"}
        )
        
        assert customer_id == "cus_test123"
        mock_create.assert_called_once_with(
            email="test@example.com",
            name="Test User",
            metadata={"tenant_id": "abc123"}
        )


@pytest.mark.asyncio
async def test_create_customer_without_metadata():
    """Test creating a Stripe customer without metadata."""
    with patch("stripe.Customer.create") as mock_create:
        mock_customer = MagicMock()
        mock_customer.id = "cus_test456"
        mock_create.return_value = mock_customer
        
        customer_id = await create_customer(
            email="user@example.com",
            name="Another User"
        )
        
        assert customer_id == "cus_test456"
        mock_create.assert_called_once_with(
            email="user@example.com",
            name="Another User",
            metadata={}
        )


@pytest.mark.asyncio
async def test_create_subscription_success():
    """Test creating a Stripe subscription successfully."""
    with patch("stripe.Subscription.create") as mock_create:
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_test123"
        mock_subscription.status = "active"
        mock_subscription.__getitem__ = MagicMock(side_effect=lambda key: {
            "items": {"data": [{"id": "si_test123"}]}
        }[key])
        mock_create.return_value = mock_subscription
        
        result = await create_subscription(
            customer_id="cus_test123",
            price_id="price_test123",
            metadata={"tenant_id": "abc123"}
        )
        
        assert result["subscription_id"] == "sub_test123"
        assert result["item_id"] == "si_test123"
        assert result["status"] == "active"
        mock_create.assert_called_once_with(
            customer="cus_test123",
            items=[{"price": "price_test123"}],
            metadata={"tenant_id": "abc123"}
        )


@pytest.mark.asyncio
async def test_create_subscription_without_metadata():
    """Test creating a Stripe subscription without metadata."""
    with patch("stripe.Subscription.create") as mock_create:
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_test456"
        mock_subscription.status = "trialing"
        mock_subscription.__getitem__ = MagicMock(side_effect=lambda key: {
            "items": {"data": [{"id": "si_test456"}]}
        }[key])
        mock_create.return_value = mock_subscription
        
        result = await create_subscription(
            customer_id="cus_test456",
            price_id="price_test456"
        )
        
        assert result["subscription_id"] == "sub_test456"
        assert result["item_id"] == "si_test456"
        assert result["status"] == "trialing"
        mock_create.assert_called_once_with(
            customer="cus_test456",
            items=[{"price": "price_test456"}],
            metadata={}
        )


@pytest.mark.asyncio
async def test_cancel_subscription_immediate():
    """Test canceling a subscription immediately."""
    with patch("stripe.Subscription.delete") as mock_delete:
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_test123"
        mock_subscription.status = "canceled"
        mock_subscription.cancel_at_period_end = False
        mock_delete.return_value = mock_subscription
        
        result = await cancel_subscription("sub_test123", immediately=True)
        
        assert result["status"] == "canceled"
        assert result["subscription_id"] == "sub_test123"
        mock_delete.assert_called_once_with("sub_test123")


@pytest.mark.asyncio
async def test_cancel_subscription_at_period_end():
    """Test canceling a subscription at period end."""
    with patch("stripe.Subscription.modify") as mock_modify:
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_test123"
        mock_subscription.status = "active"
        mock_subscription.cancel_at_period_end = True
        mock_modify.return_value = mock_subscription
        
        result = await cancel_subscription("sub_test123", immediately=False)
        
        assert result["status"] == "active"
        assert result["cancel_at_period_end"] is True
        mock_modify.assert_called_once_with(
            "sub_test123",
            cancel_at_period_end=True
        )


@pytest.mark.asyncio
async def test_create_billing_portal_session():
    """Test creating a billing portal session."""
    with patch("stripe.billing_portal.Session.create") as mock_create:
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/session/test123"
        mock_create.return_value = mock_session
        
        url = await create_billing_portal_session(
            customer_id="cus_test123",
            return_url="https://example.com/billing"
        )
        
        assert url == "https://billing.stripe.com/session/test123"
        mock_create.assert_called_once_with(
            customer="cus_test123",
            return_url="https://example.com/billing"
        )


@pytest.mark.asyncio
async def test_create_usage_record_success():
    """Test recording usage to Stripe."""
    with patch("stripe.SubscriptionItem.create_usage_record") as mock_create:
        mock_record = MagicMock()
        mock_record.id = "mbur_test123"
        mock_record.quantity = 1000
        mock_record.timestamp = 1234567890
        mock_create.return_value = mock_record
        
        result = await create_usage_record(
            subscription_item_id="si_test123",
            quantity=1000,
            action="increment"
        )
        
        assert result["id"] == "mbur_test123"
        assert result["quantity"] == 1000
        assert result["timestamp"] == 1234567890
        mock_create.assert_called_once_with(
            "si_test123",
            quantity=1000,
            action="increment"
        )


@pytest.mark.asyncio
async def test_create_usage_record_default_action():
    """Test recording usage with default action."""
    with patch("stripe.SubscriptionItem.create_usage_record") as mock_create:
        mock_record = MagicMock()
        mock_record.id = "mbur_test456"
        mock_record.quantity = 500
        mock_record.timestamp = 1234567891
        mock_create.return_value = mock_record
        
        result = await create_usage_record(
            subscription_item_id="si_test456",
            quantity=500
        )
        
        assert result["id"] == "mbur_test456"
        assert result["quantity"] == 500
        mock_create.assert_called_once_with(
            "si_test456",
            quantity=500,
            action="increment"
        )


@pytest.mark.asyncio
async def test_list_prices_all():
    """Test listing all Stripe prices."""
    with patch("stripe.Price.list") as mock_list:
        mock_price1 = MagicMock()
        mock_price1.id = "price_test1"
        mock_price1.active = True
        mock_price1.unit_amount = 1000
        mock_price1.currency = "usd"
        mock_price1.recurring = {"interval": "month"}
        mock_price1.product = "prod_test1"
        
        mock_price2 = MagicMock()
        mock_price2.id = "price_test2"
        mock_price2.active = True
        mock_price2.unit_amount = 5000
        mock_price2.currency = "usd"
        mock_price2.recurring = {"interval": "year"}
        mock_price2.product = "prod_test2"
        
        mock_list.return_value = MagicMock(data=[mock_price1, mock_price2])
        
        prices = await list_prices()
        
        assert len(prices) == 2
        assert prices[0]["id"] == "price_test1"
        assert prices[0]["unit_amount"] == 1000
        assert prices[0]["recurring"]["interval"] == "month"
        assert prices[1]["id"] == "price_test2"
        assert prices[1]["unit_amount"] == 5000
        assert prices[1]["recurring"]["interval"] == "year"
        mock_list.assert_called_once_with(active=True, limit=100)


@pytest.mark.asyncio
async def test_list_prices_active_only():
    """Test listing only active Stripe prices."""
    with patch("stripe.Price.list") as mock_list:
        mock_price = MagicMock()
        mock_price.id = "price_active"
        mock_price.active = True
        mock_price.unit_amount = 2000
        mock_price.currency = "usd"
        mock_price.recurring = {"interval": "month"}
        mock_price.product = "prod_test"
        
        mock_list.return_value = MagicMock(data=[mock_price])
        
        prices = await list_prices(active=True)
        
        assert len(prices) == 1
        assert prices[0]["id"] == "price_active"
        mock_list.assert_called_once_with(active=True, limit=100)


@pytest.mark.asyncio
async def test_get_subscription_success():
    """Test getting a Stripe subscription."""
    with patch("stripe.Subscription.retrieve") as mock_retrieve:
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_test123"
        mock_subscription.status = "active"
        mock_subscription.customer = "cus_test123"
        mock_subscription.current_period_start = 1234567890
        mock_subscription.current_period_end = 1237159890
        mock_subscription.cancel_at_period_end = False
        mock_retrieve.return_value = mock_subscription
        
        result = await get_subscription("sub_test123")
        
        assert result["id"] == "sub_test123"
        assert result["status"] == "active"
        assert result["customer"] == "cus_test123"
        assert result["current_period_start"] == 1234567890
        assert result["current_period_end"] == 1237159890
        assert result["cancel_at_period_end"] is False
        mock_retrieve.assert_called_once_with("sub_test123")


@pytest.mark.asyncio
async def test_stripe_api_error():
    """Test handling Stripe API errors."""
    import stripe
    
    with patch("stripe.Customer.create") as mock_create:
        mock_create.side_effect = stripe.error.StripeError("API Error")
        
        with pytest.raises(stripe.error.StripeError):
            await create_customer("test@example.com", "Test User")
