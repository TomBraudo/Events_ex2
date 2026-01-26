from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from business.order import OrderProcessor
from service.kafka import KafkaConsumerService, dlq_producer
from models import OrderWithShipping
from config.settings import settings
from typing import Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["orders"])
order_processor = OrderProcessor()
kafka_consumer = KafkaConsumerService()


# Response models
class OrderDetailsResponse(BaseModel):
    """Response model for order details"""
    success: bool
    message: str
    data: OrderWithShipping = None


class OrderIdsResponse(BaseModel):
    """Response model for getAllOrderIdsFromTopic"""
    success: bool
    message: str
    topicName: str
    orderIds: List[str]
    count: int


class ErrorResponse(BaseModel):
    """Response model for errors"""
    success: bool = False
    error: str
    details: str = None


@router.get(
    "/order-details",
    response_model=OrderDetailsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Order details retrieved successfully"},
        400: {"description": "Bad request - missing orderId"},
        404: {"description": "Order not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_order_details(
    orderId: str = Query(..., description="The order ID to retrieve")
):
    """
    Get order details with shipping cost
    
    This endpoint retrieves a stored order (processed from Kafka events)
    and returns it with the calculated shipping cost (2% of totalAmount).
    
    Query Parameters:
    - orderId: The unique identifier of the order
    """
    try:
        if not orderId or not orderId.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "Bad Request",
                    "details": "orderId parameter is required and cannot be empty"
                }
            )
        
        logger.info(f"Received request for order details: {orderId}")
        
        # Get order from business logic layer
        order_data = order_processor.get_order_details(orderId)
        
        # Validate with Pydantic model
        order_with_shipping = OrderWithShipping(**order_data)
        
        return OrderDetailsResponse(
            success=True,
            message=f"Order '{orderId}' retrieved successfully",
            data=order_with_shipping
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    
    except ValueError as e:
        # Order not found
        logger.warning(f"Order not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": "Not Found",
                "details": str(e)
            }
        )
    
    except Exception as e:
        # Generic errors
        logger.error(f"Error retrieving order details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "Internal Server Error",
                "details": str(e)
            }
        )


@router.get(
    "/getAllOrderIdsFromTopic",
    response_model=OrderIdsResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Order IDs retrieved successfully"},
        400: {"description": "Bad request - missing topicName"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable (Kafka/Schema Registry)"}
    }
)
async def get_all_order_ids_from_topic(
    topicName: str = Query(..., description="The Kafka topic name to read from")
):
    """
    Get all order IDs from a specific Kafka topic
    
    This endpoint reads all messages from the specified Kafka topic
    and returns a list of all order IDs found in that topic.
    
    Query Parameters:
    - topicName: The name of the Kafka topic to read from (e.g., "order-events")
    """
    try:
        if not topicName or not topicName.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "Bad Request",
                    "details": "topicName parameter is required and cannot be empty"
                }
            )
        
        logger.info(f"Received request to get all order IDs from topic: {topicName}")
        
        # Read all messages from the topic
        try:
            messages = kafka_consumer.get_all_messages_from_topic(topicName)
        except ConnectionError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "success": False,
                    "error": "Service Unavailable",
                    "details": "Kafka broker or Schema Registry is not available"
                }
            )
        
        # Extract order IDs from messages
        order_ids = [msg.get('orderId', 'Unknown') for msg in messages if msg]
        
        logger.info(f"Retrieved {len(order_ids)} order IDs from topic '{topicName}'")
        
        return OrderIdsResponse(
            success=True,
            message=f"Successfully retrieved order IDs from topic '{topicName}'",
            topicName=topicName,
            orderIds=order_ids,
            count=len(order_ids)
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    
    except Exception as e:
        # Check for Kafka/Schema Registry errors
        error_msg = str(e).lower()
        if any(term in error_msg for term in ['connection', 'broker', 'timeout', 'network', 'schema', 'registry']):
            logger.error(f"Kafka/Schema Registry error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "success": False,
                    "error": "Service Unavailable",
                    "details": str(e)
                }
            )
        
        # Generic errors
        logger.error(f"Error reading from topic: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "Internal Server Error",
                "details": str(e)
            }
        )


@router.get(
    "/stats",
    tags=["stats"],
    status_code=status.HTTP_200_OK
)
async def get_stats():
    """
    Get statistics about processed orders
    
    Returns the count of orders currently stored in memory.
    """
    count = order_processor.get_order_count()
    order_ids = order_processor.get_all_stored_order_ids()
    
    return {
        "success": True,
        "totalOrders": count,
        "orderIds": order_ids
    }


@router.get(
    "/dlq/info",
    tags=["dlq"],
    status_code=status.HTTP_200_OK
)
async def get_dlq_info():
    """
    Get Dead Letter Queue (DLQ) configuration and statistics
    
    Returns:
    - DLQ topic name
    - Max retry count
    - Retry backoff configuration
    - Consumer status
    """
    return {
        "success": True,
        "dlqConfig": {
            "dlqTopic": settings.KAFKA_DLQ_TOPIC,
            "maxRetries": settings.DLQ_MAX_RETRIES,
            "initialBackoffMs": settings.DLQ_RETRY_BACKOFF_MS,
            "maxBackoffMs": settings.DLQ_MAX_BACKOFF_MS,
            "retryStrategy": "exponential_backoff"
        },
        "consumerStats": {
            "isRunning": kafka_consumer.is_running,
            "consumerGroup": settings.KAFKA_CONSUMER_GROUP
        }
    }


@router.get(
    "/dlq/messages",
    tags=["dlq"],
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "DLQ messages retrieved successfully"},
        503: {"description": "Service unavailable (Kafka)"}
    }
)
async def get_dlq_messages():
    """
    Retrieve all messages from the Dead Letter Queue
    
    This endpoint reads all messages from the DLQ topic to help
    with monitoring and debugging failed message processing.
    """
    try:
        logger.info(f"Reading messages from DLQ topic: {settings.KAFKA_DLQ_TOPIC}")
        
        # Read all messages from DLQ topic
        dlq_messages = kafka_consumer.get_all_messages_from_topic(
            settings.KAFKA_DLQ_TOPIC,
            timeout_seconds=5
        )
        
        return {
            "success": True,
            "dlqTopic": settings.KAFKA_DLQ_TOPIC,
            "messageCount": len(dlq_messages),
            "messages": dlq_messages
        }
        
    except Exception as e:
        logger.error(f"Error reading from DLQ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "error": "Failed to read from DLQ",
                "details": str(e)
            }
        )

