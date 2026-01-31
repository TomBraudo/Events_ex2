from typing import Dict, Any
from models import Order
from utils.order_generator import OrderGenerator
from service.kafka import KafkaProducerService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderService:
    """Business logic for order management - Producer only (no storage)"""
    
    def __init__(self):
        self.kafka_producer = KafkaProducerService()
    
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
        # Generate order with auto-generated fields
        order_dict = OrderGenerator.generate_order(order_id, num_items)
        
        # Validate order using Pydantic model
        try:
            order_model = Order(**order_dict)
            logger.info(f"Order validation successful for orderId: {order_id}")
        except Exception as e:
            logger.error(f"Order validation failed: {str(e)}")
            raise ValueError(f"Order validation failed: {str(e)}")
        
        # Publish to Kafka (CartService is producer-only, OrderService stores data)
        try:
            self.kafka_producer.publish_order_event(order_dict)
            logger.info(f"Order event published to Kafka: {order_id}")
        except ConnectionError as e:
            logger.error(f"Failed to publish to Kafka: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error publishing to Kafka: {str(e)}")
            raise
        
        return order_dict
    
    def update_order_status(self, order_id: str, new_status: str) -> Dict[str, Any]:
        """
        Update the status of an existing order (async event-driven approach)
        
        This publishes a status update event to Kafka. OrderService consumer
        will validate if the order exists and update it, or send to DLQ if not found.
        
        Args:
            order_id: The order ID to update
            new_status: The new status value
            
        Returns:
            Status update event confirmation
            
        Raises:
            ValueError: If status is invalid
            ConnectionError: If Kafka broker is not available
            Exception: For other errors
        """
        # Validate new status
        if not new_status or not new_status.strip():
            raise ValueError("Status cannot be empty or whitespace")
        new_status = new_status.strip()
        
        logger.info(f"Publishing status update event: {order_id} -> '{new_status}'")
        
        # Publish status update to Kafka (async - fire and forget)
        try:
            self.kafka_producer.publish_status_update_event(order_id, new_status)
            
            logger.info(
                f"Status update event published successfully for {order_id}. "
                f"OrderService will process asynchronously."
            )
            
            return {
                "orderId": order_id,
                "status": new_status,
                "message": "Status update event published. Processing asynchronously.",
                "eventType": "STATUS_UPDATED"
            }
            
        except ConnectionError as e:
            logger.error(f"Failed to publish status update to Kafka: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error publishing status update: {str(e)}")
            raise


# Singleton instance
order_service = OrderService()

