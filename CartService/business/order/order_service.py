from typing import Dict, Any
from models import Order
from utils.order_generator import OrderGenerator
from utils.order_storage import order_storage
from service.kafka import KafkaProducerService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderService:
    """Business logic for order management"""
    
    def __init__(self):
        self.kafka_producer = KafkaProducerService()
        self.storage = order_storage
    
    def create_order(self, order_id: str, num_items: int) -> Dict[str, Any]:
        """
        Create a new order with auto-generated fields
        
        Args:
            order_id: The order ID (from API request)
            num_items: Number of items to generate
            
        Returns:
            The created order dictionary
            
        Raises:
            ValueError: If validation fails
            ConnectionError: If Kafka broker is not available
            Exception: For other errors
        """
        # Check if order already exists
        if self.storage.order_exists(order_id):
            raise ValueError(f"Order with ID '{order_id}' already exists")
        
        # Generate order with auto-generated fields
        order_dict = OrderGenerator.generate_order(order_id, num_items)
        
        # Validate order using Pydantic model
        try:
            order_model = Order(**order_dict)
            logger.info(f"Order validation successful for orderId: {order_id}")
        except Exception as e:
            logger.error(f"Order validation failed: {str(e)}")
            raise ValueError(f"Order validation failed: {str(e)}")
        
        # Save to storage
        self.storage.save_order(order_dict)
        logger.info(f"Order saved to storage: {order_id}")
        
        # Publish to Kafka
        try:
            self.kafka_producer.publish_order_event(order_dict)
            logger.info(f"Order event published to Kafka: {order_id}")
        except ConnectionError as e:
            # Remove from storage if Kafka publish fails
            logger.error(f"Failed to publish to Kafka, rolling back: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error publishing to Kafka: {str(e)}")
            raise
        
        return order_dict
    
    def update_order_status(self, order_id: str, new_status: str) -> Dict[str, Any]:
        """
        Update the status of an existing order
        
        Args:
            order_id: The order ID to update
            new_status: The new status value
            
        Returns:
            The updated order dictionary
            
        Raises:
            ValueError: If order not found or status is invalid
            ConnectionError: If Kafka broker is not available
            Exception: For other errors
        """
        # Check if order exists
        order = self.storage.get_order(order_id)
        if not order:
            raise ValueError(f"Order with ID '{order_id}' not found")
        
        # Validate new status (allow any non-empty string)
        if not new_status or not new_status.strip():
            raise ValueError("Status cannot be empty or whitespace")
        new_status = new_status.strip()
        
        # Update status in storage
        old_status = order.get("status")
        self.storage.update_order_status(order_id, new_status)
        logger.info(f"Order status updated: {order_id} from '{old_status}' to '{new_status}'")
        
        # Get updated order
        updated_order = self.storage.get_order(order_id)
        
        # Publish update event to Kafka
        try:
            self.kafka_producer.publish_order_event(updated_order)
            logger.info(f"Order update event published to Kafka: {order_id}")
        except ConnectionError as e:
            # Rollback status change if Kafka publish fails
            self.storage.update_order_status(order_id, old_status)
            logger.error(f"Failed to publish to Kafka, rolling back: {str(e)}")
            raise
        except Exception as e:
            # Rollback status change
            self.storage.update_order_status(order_id, old_status)
            logger.error(f"Error publishing to Kafka, rolling back: {str(e)}")
            raise
        
        return updated_order


# Singleton instance
order_service = OrderService()

