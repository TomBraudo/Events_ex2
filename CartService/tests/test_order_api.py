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


client = TestClient(app)


#
# /api/create-order tests (5)
#


def test_create_order_happy_path(monkeypatch):
    """Valid request should return 201 with success=True and data payload."""

    def mock_create_order(self, order_id: str, num_items: int):
        return {
            "orderId": order_id,
            "numItems": num_items,
            "status": "pending",
        }

    from business.order.order_service import OrderService

    monkeypatch.setattr(OrderService, "create_order", mock_create_order)

    payload = {"orderId": "ORDER-123", "numItems": 3}
    response = client.post("/api/create-order", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["orderId"] == "ORDER-123"
    assert body["data"]["numItems"] == 3


def test_create_order_validation_error_empty_order_id():
    """Empty orderId (whitespace) should trigger 422 from Pydantic validator."""
    payload = {"orderId": "   ", "numItems": 3}
    response = client.post("/api/create-order", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


def test_create_order_too_many_items():
    """numItems > 100 should be rejected by Pydantic with 422."""
    payload = {"orderId": "ORDER-123", "numItems": 101}
    response = client.post("/api/create-order", json=payload)

    assert response.status_code == 422


def test_create_order_too_few_items():
    """numItems < 1 should be rejected by Pydantic with 422."""
    payload = {"orderId": "ORDER-123", "numItems": 0}
    response = client.post("/api/create-order", json=payload)

    assert response.status_code == 422


def test_create_order_kafka_unavailable(monkeypatch):
    """If business layer raises ConnectionError, API should return 503."""

    def mock_create_order(self, order_id: str, num_items: int):
        raise ConnectionError("Kafka broker not available")

    from business.order.order_service import OrderService

    monkeypatch.setattr(OrderService, "create_order", mock_create_order)

    payload = {"orderId": "ORDER-123", "numItems": 3}
    response = client.post("/api/create-order", json=payload)

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "Service Unavailable"


#
# /api/update-order tests (5)
#


def test_update_order_happy_path(monkeypatch):
    """Valid update should return 200 with updated order."""

    def mock_update_order_status(self, order_id: str, new_status: str):
        return {
            "orderId": order_id,
            "status": new_status,
        }

    from business.order.order_service import OrderService

    monkeypatch.setattr(OrderService, "update_order_status", mock_update_order_status)

    payload = {"orderId": "ORDER-123", "status": "IN_PROGRESS"}
    response = client.put("/api/update-order", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "IN_PROGRESS"


def test_update_order_not_found(monkeypatch):
    """ValueError containing 'not found' should map to 404."""

    def mock_update_order_status(self, order_id: str, new_status: str):
        raise ValueError(f"Order with ID '{order_id}' not found")

    from business.order.order_service import OrderService

    monkeypatch.setattr(OrderService, "update_order_status", mock_update_order_status)

    payload = {"orderId": "MISSING-ORDER", "status": "any"}
    response = client.put("/api/update-order", json=payload)

    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["error"] == "Not Found"


def test_update_order_validation_error_empty_order_id():
    """Empty orderId should map to 422 from Pydantic validator."""
    payload = {"orderId": "   ", "status": "any"}
    response = client.put("/api/update-order", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


def test_update_order_validation_error_empty_status():
    """Empty status should map to 422 from Pydantic validator."""
    payload = {"orderId": "ORDER-123", "status": "   "}
    response = client.put("/api/update-order", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body


def test_update_order_kafka_unavailable(monkeypatch):
    """ConnectionError from business layer should map to 503."""

    def mock_update_order_status(self, order_id: str, new_status: str):
        raise ConnectionError("Kafka broker not available")

    from business.order.order_service import OrderService

    monkeypatch.setattr(OrderService, "update_order_status", mock_update_order_status)

    payload = {"orderId": "ORDER-123", "status": "any"}
    response = client.put("/api/update-order", json=payload)

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "Service Unavailable"


