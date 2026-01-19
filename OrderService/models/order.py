from pydantic import BaseModel, Field
from typing import List
from enum import Enum


class OrderStatus(str, Enum):
    """Enum for valid order statuses"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItem(BaseModel):
    """Order item model"""
    itemId: str = Field(..., description="Unique identifier for the item")
    quantity: int = Field(..., description="Quantity of the item")
    price: float = Field(..., description="Price of a single unit")

    class Config:
        json_schema_extra = {
            "example": {
                "itemId": "ITEM-LAPTOP-123",
                "quantity": 2,
                "price": 999.99
            }
        }


class Order(BaseModel):
    """Order model matching Avro schema"""
    orderId: str = Field(..., description="Unique identifier for the order")
    customerId: str = Field(..., description="Unique identifier for the customer")
    orderDate: str = Field(..., description="Timestamp in ISO 8601 format")
    items: List[OrderItem] = Field(..., description="Array of order items")
    totalAmount: float = Field(..., description="Total cost of the order")
    currency: str = Field(..., description="Currency code (e.g., USD, EUR)")
    status: str = Field(..., description="Status of the order")

    class Config:
        json_schema_extra = {
            "example": {
                "orderId": "ORDER-001",
                "customerId": "CUST-1234",
                "orderDate": "2026-01-13T10:30:00Z",
                "items": [
                    {
                        "itemId": "ITEM-LAPTOP-123",
                        "quantity": 2,
                        "price": 999.99
                    }
                ],
                "totalAmount": 1999.98,
                "currency": "USD",
                "status": "pending"
            }
        }


class OrderWithShipping(Order):
    """Order model with calculated shipping cost"""
    shippingCost: float = Field(..., description="Shipping cost (2% of totalAmount)")

    class Config:
        json_schema_extra = {
            "example": {
                "orderId": "ORDER-001",
                "customerId": "CUST-1234",
                "orderDate": "2026-01-13T10:30:00Z",
                "items": [
                    {
                        "itemId": "ITEM-LAPTOP-123",
                        "quantity": 2,
                        "price": 999.99
                    }
                ],
                "totalAmount": 1999.98,
                "currency": "USD",
                "status": "pending",
                "shippingCost": 39.99
            }
        }

