import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure the service root (where main.py lives) is on sys.path
CURRENT_DIR = os.path.dirname(__file__)
SERVICE_ROOT = os.path.dirname(CURRENT_DIR)
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)

from main import app
from api.controllers import order_controller


client = TestClient(app)
# Client that doesn't raise server exceptions - returns 500 responses instead
client_no_raise = TestClient(app, raise_server_exceptions=False)


#
# /api/order-details tests (5)
#


def test_order_details_happy_path(monkeypatch):
    """Valid orderId should return 200 with populated data."""

    def mock_get_order_details(order_id: str):
        return {
            "orderId": order_id,
            "customerId": "CUST-1",
            "orderDate": "2026-01-13T10:30:00Z",
            "items": [],
            "totalAmount": 0.0,
            "currency": "USD",
            "status": "any",
            "shippingCost": 0.0,
        }

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_details", mock_get_order_details
    )

    response = client.get("/api/order-details", params={"orderId": "ORDER-123"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["orderId"] == "ORDER-123"


def test_order_details_missing_order_id_query_param():
    """Missing orderId should produce 422 from FastAPI query validation."""
    response = client.get("/api/order-details")
    assert response.status_code == 422


def test_order_details_empty_order_id():
    """Empty orderId should map to 400 Bad Request from explicit check."""
    response = client.get("/api/order-details", params={"orderId": "   "})

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "Bad Request"


def test_order_details_not_found(monkeypatch):
    """ValueError from order_processor should map to 404."""

    def mock_get_order_details(order_id: str):
        raise ValueError(f"Order with ID '{order_id}' not found")

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_details", mock_get_order_details
    )

    response = client.get("/api/order-details", params={"orderId": "MISSING-ORDER"})

    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["error"] == "Not Found"


def test_order_details_internal_error(monkeypatch):
    """Unexpected exception should map to 500."""

    def mock_get_order_details(order_id: str):
        raise RuntimeError("Unexpected error")

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_details", mock_get_order_details
    )

    response = client.get("/api/order-details", params={"orderId": "ORDER-123"})

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["error"] == "Internal Server Error"


#
# /api/getAllOrderIdsFromTopic tests (5)
#


def test_get_all_order_ids_from_topic_happy_path(monkeypatch):
    """Valid topicName should return 200 with list of orderIds."""

    def mock_get_all_messages_from_topic(topic_name: str):
        return [
            {"orderId": "ORDER-1"},
            {"orderId": "ORDER-2"},
        ]

    monkeypatch.setattr(
        order_controller.kafka_consumer,
        "get_all_messages_from_topic",
        mock_get_all_messages_from_topic,
    )

    response = client.get(
        "/api/getAllOrderIdsFromTopic", params={"topicName": "order-events"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert body["orderIds"] == ["ORDER-1", "ORDER-2"]


def test_get_all_order_ids_from_topic_missing_topic_name():
    """Missing topicName should cause 422 from FastAPI query validation."""
    response = client.get("/api/getAllOrderIdsFromTopic")
    assert response.status_code == 422


def test_get_all_order_ids_from_topic_empty_topic_name():
    """Empty topicName should map to 400 Bad Request."""
    response = client.get(
        "/api/getAllOrderIdsFromTopic", params={"topicName": "   "}
    )

    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "Bad Request"


def test_get_all_order_ids_from_topic_kafka_unavailable(monkeypatch):
    """ConnectionError from consumer should map to 503."""

    def mock_get_all_messages_from_topic(topic_name: str):
        raise ConnectionError("Kafka not available")

    monkeypatch.setattr(
        order_controller.kafka_consumer,
        "get_all_messages_from_topic",
        mock_get_all_messages_from_topic,
    )

    response = client.get(
        "/api/getAllOrderIdsFromTopic", params={"topicName": "order-events"}
    )

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "Service Unavailable"


def test_get_all_order_ids_from_topic_generic_error(monkeypatch):
    """Other exceptions should map to 500 or 503 depending on message, here 503 via keyword."""

    def mock_get_all_messages_from_topic(topic_name: str):
        raise RuntimeError("broker timeout")

    monkeypatch.setattr(
        order_controller.kafka_consumer,
        "get_all_messages_from_topic",
        mock_get_all_messages_from_topic,
    )

    response = client.get(
        "/api/getAllOrderIdsFromTopic", params={"topicName": "order-events"}
    )

    # Because 'broker' is in the error message, controller maps it to 503
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "Service Unavailable"


#
# /api/stats tests (5)
#


def test_stats_happy_path(monkeypatch):
    """Stats should return success=True, count and orderIds."""

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_count", lambda: 2
    )
    monkeypatch.setattr(
        order_controller.order_processor,
        "get_all_stored_order_ids",
        lambda: ["ORDER-1", "ORDER-2"],
    )

    response = client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["totalOrders"] == 2
    assert body["orderIds"] == ["ORDER-1", "ORDER-2"]


def test_stats_zero_orders(monkeypatch):
    """Stats should handle zero orders gracefully."""

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_count", lambda: 0
    )
    monkeypatch.setattr(
        order_controller.order_processor,
        "get_all_stored_order_ids",
        lambda: [],
    )

    response = client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["totalOrders"] == 0
    assert body["orderIds"] == []


def test_stats_many_orders(monkeypatch):
    """Stats should work with multiple IDs."""

    ids = [f"ORDER-{i}" for i in range(5)]

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_count", lambda: len(ids)
    )
    monkeypatch.setattr(
        order_controller.order_processor,
        "get_all_stored_order_ids",
        lambda: ids,
    )

    response = client.get("/api/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["totalOrders"] == 5
    assert body["orderIds"] == ids


def test_stats_does_not_raise_on_processor_error_get_order_count(monkeypatch):
    """If get_order_count fails, endpoint would currently propagate; this checks current behavior."""

    def failing_get_order_count():
        raise RuntimeError("failed to count")

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_count", failing_get_order_count
    )

    response = client_no_raise.get("/api/stats")

    # Current implementation does not handle this, so it's a 500 from FastAPI
    assert response.status_code == 500


def test_stats_does_not_raise_on_processor_error_get_ids(monkeypatch):
    """If get_all_stored_order_ids fails, endpoint should currently raise 500."""

    monkeypatch.setattr(
        order_controller.order_processor, "get_order_count", lambda: 1
    )

    def failing_get_ids():
        raise RuntimeError("failed to get ids")

    monkeypatch.setattr(
        order_controller.order_processor,
        "get_all_stored_order_ids",
        failing_get_ids,
    )

    response = client_no_raise.get("/api/stats")

    assert response.status_code == 500


