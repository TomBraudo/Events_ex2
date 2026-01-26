from typing import Dict, Any
from models import Order, OrderWithShipping
from utils.order_storage import order_storage
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderProcessor:
    """Business logic for processing orders from Kafka"""
    
    def __init__(self):
        self.storage = order_storage
        self.shipping_percentage = settings.SHIPPING_COST_PERCENTAGE
    
    def calculate_shipping_cost(self, total_amount: float) -> float:
        """
        Calculate shipping cost as 2% of totalAmount
        
        Args:
            total_amount: The order's total amount
            
        Returns:
            Calculated shipping cost (rounded to 2 decimal places)
        """
        shipping_cost = total_amount * self.shipping_percentage
        return round(shipping_cost, 2)
    
    def process_order_event(self, order_data: Dict[str, Any]) -> None:
        """
        Process an incoming order event from Kafka
        
        This method:
        1. Validates the order data
        2. Calculates shipping cost
        3. Stores the order with shipping cost
        
        Args:
            order_data: Order dictionary from Kafka (Avro deserialized)
        
        Raises:
            Exception: If processing fails (for DLQ retry logic)
        """
        order_id = order_data.get('orderId', 'Unknown')
        
        # TEST: Simulate failure for DLQ testing
        if order_id.startswith("TEST-FAIL"):
            logger.error(f"Simulated processing failure for {order_id}")
            raise ValueError(f"Simulated processing failure for {order_id}")
        
        # Validate order data using Pydantic model
        try:
            order = Order(**order_data)
            logger.info(f"Order validated: {order_id}")
        except Exception as e:
            logger.error(f"Order validation failed for {order_id}: {str(e)}")
            raise  # Re-raise for DLQ handling
        
        # Calculate shipping cost
        shipping_cost = self.calculate_shipping_cost(order.totalAmount)
        logger.info(f"Calculated shipping cost for {order_id}: {shipping_cost} (2% of {order.totalAmount})")
        
        # Create order with shipping cost
        order_with_shipping_data = {
            **order_data,
            'shippingCost': shipping_cost
        }
        
        # Validate with OrderWithShipping model
        order_with_shipping = OrderWithShipping(**order_with_shipping_data)
        
        # Store in memory
        self.storage.save_order(order_with_shipping.model_dump())
        
        logger.info(
            f"Order processed and stored: {order_id}, "
            f"status: {order.status}, "
            f"totalAmount: {order.totalAmount}, "
            f"shippingCost: {shipping_cost}"
        )
    
    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """
        Retrieve order details with shipping cost
        
        Args:
            order_id: The order ID to retrieve
            
        Returns:
            Order dictionary with shipping cost
            
        Raises:
            ValueError: If order not found
        """
        order = self.storage.get_order(order_id)
        
        if not order:
            raise ValueError(f"Order with ID '{order_id}' not found")
        
        return order
    
    def get_all_stored_order_ids(self) -> list:
        """
        Get all order IDs from storage
        
        Returns:
            List of order IDs
        """
        return self.storage.get_all_order_ids()
    
    def get_order_count(self) -> int:
        """
        Get count of stored orders
        
        Returns:
            Number of orders in storage
        """
        return self.storage.get_order_count()


# Singleton instance
order_processor = OrderProcessor()

