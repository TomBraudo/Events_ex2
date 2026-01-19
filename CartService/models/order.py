from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List
from enum import Enum
from datetime import datetime
from decimal import Decimal


class OrderStatus(str, Enum):
    """Enum for valid order statuses"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItem(BaseModel):
    """Order item model with validation"""
    itemId: str = Field(..., min_length=1, description="Unique identifier for the item")
    quantity: int = Field(..., ge=1, description="Quantity of the item (must be >= 1)")
    price: float = Field(..., gt=0, description="Price of a single unit (must be > 0)")

    @field_validator('itemId')
    @classmethod
    def validate_item_id(cls, v: str) -> str:
        """Validate itemId is not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError('itemId cannot be empty or whitespace')
        return v.strip()

    @field_validator('price')
    @classmethod
    def validate_price(cls, v: float) -> float:
        """Ensure price is positive"""
        if v <= 0:
            raise ValueError('price must be greater than 0')
        return round(v, 2)  # Round to 2 decimal places


class Order(BaseModel):
    """Order model with comprehensive validation"""
    orderId: str = Field(..., min_length=1, description="Unique identifier for the order")
    customerId: str = Field(..., min_length=1, description="Unique identifier for the customer")
    orderDate: str = Field(..., description="Timestamp in ISO 8601 format")
    items: List[OrderItem] = Field(..., min_length=1, description="Array of order items (cannot be empty)")
    totalAmount: float = Field(..., gt=0, description="Total cost of the order (must be > 0)")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (3-letter, e.g., USD, EUR)")
    status: OrderStatus = Field(..., description="Status of the order")

    @field_validator('orderId', 'customerId')
    @classmethod
    def validate_ids(cls, v: str) -> str:
        """Validate IDs are not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError('ID fields cannot be empty or whitespace')
        return v.strip()

    @field_validator('orderDate')
    @classmethod
    def validate_order_date(cls, v: str) -> str:
        """Validate orderDate is in ISO 8601 format"""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except (ValueError, AttributeError):
            raise ValueError('orderDate must be in valid ISO 8601 format')

    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency is 3 uppercase letters"""
        if not v or len(v) != 3:
            raise ValueError('currency must be a 3-letter code')
        if not v.isalpha():
            raise ValueError('currency must contain only letters')
        return v.upper()

    @field_validator('items')
    @classmethod
    def validate_items_not_empty(cls, v: List[OrderItem]) -> List[OrderItem]:
        """Validate items array is not empty"""
        if not v or len(v) == 0:
            raise ValueError('items array cannot be empty')
        return v

    @model_validator(mode='after')
    def validate_total_amount(self) -> 'Order':
        """Validate totalAmount equals sum of (price * quantity) for all items"""
        calculated_total = sum(item.price * item.quantity for item in self.items)
        calculated_total = round(calculated_total, 2)
        
        # Allow small floating point differences (0.01)
        if abs(self.totalAmount - calculated_total) > 0.01:
            raise ValueError(
                f'totalAmount ({self.totalAmount}) must equal the sum of item prices * quantities ({calculated_total})'
            )
        return self

