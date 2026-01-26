from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from business.order import OrderService
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["orders"])
order_service = OrderService()


# Request models for API
class CreateOrderRequest(BaseModel):
    """Request model for creating an order"""
    orderId: str = Field(..., min_length=1, description="Unique identifier for the order")
    numItems: int = Field(..., ge=1, le=100, description="Number of items to generate (1-100)")
    
    @field_validator('orderId')
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        """Validate orderId is not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError('orderId cannot be empty or whitespace')
        return v.strip()


class UpdateOrderRequest(BaseModel):
    """Request model for updating an order status"""
    orderId: str = Field(..., min_length=1, description="Unique identifier for the order")
    status: str = Field(..., min_length=1, description="New status for the order")
    
    @field_validator('orderId')
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        """Validate orderId is not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError('orderId cannot be empty or whitespace')
        return v.strip()
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is not empty after stripping whitespace"""
        if not v or not v.strip():
            raise ValueError('status cannot be empty or whitespace')
        return v.strip()


# Response models
class OrderResponse(BaseModel):
    """Response model for order operations"""
    success: bool
    message: str
    data: Dict[str, Any] = None


class ErrorResponse(BaseModel):
    """Response model for errors"""
    success: bool = False
    error: str
    details: str = None


@router.post(
    "/create-order",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Order created successfully"},
        400: {"description": "Validation error or bad request"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable (Kafka/Schema Registry)"}
    }
)
async def create_order(request: CreateOrderRequest):
    """
    Create a new order
    
    This endpoint receives orderId and numItems, then auto-generates:
    - customerId
    - orderDate (current timestamp in ISO8601)
    - items array (with random itemId, quantity, price)
    - totalAmount (calculated from items)
    - currency (random)
    - status (always 'pending' for new orders)
    
    The order is validated, stored, and published to Kafka.
    """
    try:
        logger.info(f"Received create order request: orderId={request.orderId}, numItems={request.numItems}")
        
        # Call business logic layer
        order = order_service.create_order(
            order_id=request.orderId,
            num_items=request.numItems
        )
        
        return OrderResponse(
            success=True,
            message=f"Order '{request.orderId}' created successfully",
            data=order
        )
    
    except ValueError as e:
        # Validation errors (400 Bad Request)
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Validation Error",
                "details": str(e)
            }
        )
    
    except ConnectionError as e:
        # Kafka connection errors (503 Service Unavailable)
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "error": "Service Unavailable",
                "details": "Kafka broker or Schema Registry is not available. Please try again later."
            }
        )
    
    except Exception as e:
        # Generic errors (500 Internal Server Error)
        logger.error(f"Unexpected error: {str(e)}")
        
        # Check if it's a schema registry error
        if 'schema' in str(e).lower() or 'registry' in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "success": False,
                    "error": "Schema Registry Error",
                    "details": str(e)
                }
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "Internal Server Error",
                "details": str(e)
            }
        )


@router.put(
    "/update-order",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Order updated successfully"},
        400: {"description": "Validation error or bad request"},
        404: {"description": "Order not found"},
        500: {"description": "Internal server error"},
        503: {"description": "Service unavailable (Kafka/Schema Registry)"}
    }
)
async def update_order(request: UpdateOrderRequest):
    """
    Update an existing order's status.
    
    This endpoint receives orderId and status, validates them (status can be any
    non-empty string), updates the order in storage, and publishes the update
    event to Kafka.
    """
    try:
        logger.info(f"Received update order request: orderId={request.orderId}, status={request.status}")
        
        # Call business logic layer
        updated_order = order_service.update_order_status(
            order_id=request.orderId,
            new_status=request.status
        )
        
        return OrderResponse(
            success=True,
            message=f"Order '{request.orderId}' updated successfully",
            data=updated_order
        )
    
    except ValueError as e:
        # Check if it's a "not found" error or validation error
        if "not found" in str(e).lower():
            logger.warning(f"Order not found: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "success": False,
                    "error": "Not Found",
                    "details": str(e)
                }
            )
        else:
            # Other validation errors
            logger.warning(f"Validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": "Validation Error",
                    "details": str(e)
                }
            )
    
    except ConnectionError as e:
        # Kafka connection errors (503 Service Unavailable)
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "error": "Service Unavailable",
                "details": "Kafka broker or Schema Registry is not available. Please try again later."
            }
        )
    
    except Exception as e:
        # Generic errors (500 Internal Server Error)
        logger.error(f"Unexpected error: {str(e)}")
        
        # Check if it's a schema registry error
        if 'schema' in str(e).lower() or 'registry' in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "success": False,
                    "error": "Schema Registry Error",
                    "details": str(e)
                }
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": "Internal Server Error",
                "details": str(e)
            }
        )

