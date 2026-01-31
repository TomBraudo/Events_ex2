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
    
    def process_event(self, event: Dict[str, Any]) -> None:
        """
        Route event based on eventType
        
        Args:
            event: Event envelope with eventType and payload
            
        Raises:
            ValueError: If unknown event type
        """
        event_type = event.get('eventType')
        
        if event_type == 'ORDER_CREATED':
            payload = event.get('payload')
            self.process_order_event(payload)
        elif event_type == 'STATUS_UPDATED':
            payload = event.get('payload')
            self.process_status_update_event(payload)
        else:
            raise ValueError(f"Unknown event type: {event_type}")
    
    def process_order_event(self, order_data: Dict[str, Any]) -> None:
        """
        Process an incoming order event from Kafka
        
        This method:
        1. Validates the order data
        2. Checks for duplicate orderId
        3. Calculates shipping cost
        4. Stores the order with shipping cost
        
        Args:
            order_data: Order dictionary from Kafka (Avro deserialized)
        
        Raises:
            ValueError: If duplicate orderId or validation fails (will be sent to DLQ after retries)
            Exception: If processing fails (for DLQ retry logic)
        """
        order_id = order_data.get('orderId', 'Unknown')
        
        # TEST: Simulate failure for DLQ testing
        if order_id.startswith("TEST-FAIL"):
            logger.error(f"Simulated processing failure for {order_id}")
            raise ValueError(f"Simulated processing failure for {order_id}")
        
        # Check for duplicate order ID
        if self.storage.order_exists(order_id):
            error_msg = f"Duplicate order ID: {order_id} already exists. Cannot create duplicate order."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
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
    
    def process_status_update_event(self, status_update_data: Dict[str, Any]) -> None:
        """
        Process a status update event from Kafka
        
        This method:
        1. Validates that the order exists
        2. Updates the order status
        3. Stores the updated order
        
        If the order doesn't exist, raises ValueError which will trigger
        retry logic and eventually send to DLQ.
        
        Args:
            status_update_data: Status update dictionary from Kafka (Avro deserialized)
        
        Raises:
            ValueError: If order not found (will be sent to DLQ after retries)
            Exception: If processing fails
        """
        order_id = status_update_data.get('orderId', 'Unknown')
        new_status = status_update_data.get('status')
        
        logger.info(f"Processing status update event for order: {order_id}, new status: {new_status}")
        
        # Check if order exists in storage
        existing_order = self.storage.get_order(order_id)
        
        if not existing_order:
            error_msg = f"Order {order_id} not found. Cannot update status. Sending to DLQ."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Validate new status is not empty
        if not new_status or not str(new_status).strip():
            error_msg = f"Invalid status update for order {order_id}: status is empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Update status
        old_status = existing_order.get('status')
        existing_order['status'] = new_status
        
        # Save updated order
        self.storage.save_order(existing_order)
        
        logger.info(
            f"Status update successful: order {order_id}, "
            f"status changed from '{old_status}' to '{new_status}'"
        )


# Singleton instance
order_processor = OrderProcessor()

