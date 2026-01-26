import random
import string
from datetime import datetime
from typing import List, Dict, Any
from models import OrderItem


class OrderGenerator:
    """Utility class for generating order data"""
    
    CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD"]
    ITEM_NAMES = ["laptop", "phone", "tablet", "monitor", "keyboard", "mouse", "headset", "camera", "speaker", "watch"]
    
    @staticmethod
    def generate_customer_id() -> str:
        """Generate a random customer ID"""
        return f"CUST-{random.randint(1000, 9999)}"
    
    @staticmethod
    def generate_item_id() -> str:
        """Generate a random item ID"""
        item_name = random.choice(OrderGenerator.ITEM_NAMES)
        return f"ITEM-{item_name.upper()}-{random.randint(100, 999)}"
    
    @staticmethod
    def generate_order_date() -> str:
        """Generate current datetime in ISO 8601 format"""
        return datetime.utcnow().isoformat() + "Z"
    
    @staticmethod
    def generate_currency() -> str:
        """Generate a random currency code"""
        return random.choice(OrderGenerator.CURRENCIES)
    
    @staticmethod
    def generate_initial_status() -> str:
        """Generate initial order status (always 'pending' for new orders)"""
        return "pending"
    
    @staticmethod
    def generate_items(num_items: int) -> List[Dict[str, Any]]:
        """
        Generate random order items
        
        Args:
            num_items: Number of items to generate
            
        Returns:
            List of OrderItem dictionaries
        """
        items = []
        for _ in range(num_items):
            item = {
                "itemId": OrderGenerator.generate_item_id(),
                "quantity": random.randint(1, 5),
                "price": round(random.uniform(10.0, 500.0), 2)
            }
            items.append(item)
        return items
    
    @staticmethod
    def calculate_total_amount(items: List[Dict[str, Any]]) -> float:
        """
        Calculate total amount from items
        
        Args:
            items: List of order items
            
        Returns:
            Total amount rounded to 2 decimal places
        """
        total = sum(item["price"] * item["quantity"] for item in items)
        return round(total, 2)
    
    @staticmethod
    def generate_order(order_id: str, num_items: int) -> Dict[str, Any]:
        """
        Generate a complete order with auto-generated fields
        
        Args:
            order_id: The order ID (provided by the API)
            num_items: Number of items to generate
            
        Returns:
            Complete order dictionary
        """
        items = OrderGenerator.generate_items(num_items)
        total_amount = OrderGenerator.calculate_total_amount(items)
        
        order = {
            "orderId": order_id,
            "customerId": OrderGenerator.generate_customer_id(),
            "orderDate": OrderGenerator.generate_order_date(),
            "items": items,
            "totalAmount": total_amount,
            "currency": OrderGenerator.generate_currency(),
            "status": OrderGenerator.generate_initial_status()
        }
        
        return order

