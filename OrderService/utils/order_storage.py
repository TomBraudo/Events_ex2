from typing import Dict, Optional, Any, List
from threading import Lock
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderStorage:
    """Thread-safe in-memory storage for orders with shipping costs"""
    
    def __init__(self):
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
    
    def save_order(self, order_with_shipping: Dict[str, Any]) -> None:
        """
        Save an order with shipping cost to storage
        
        Args:
            order_with_shipping: Order dictionary with shippingCost field
        """
        with self._lock:
            order_id = order_with_shipping.get("orderId")
            if order_id:
                self._orders[order_id] = order_with_shipping
                logger.info(f"Order saved to storage: {order_id}, shippingCost: {order_with_shipping.get('shippingCost')}")
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an order by ID
        
        Args:
            order_id: The order ID to retrieve
            
        Returns:
            Order dictionary with shipping cost if found, None otherwise
        """
        with self._lock:
            return self._orders.get(order_id)
    
    def order_exists(self, order_id: str) -> bool:
        """
        Check if an order exists
        
        Args:
            order_id: The order ID to check
            
        Returns:
            True if order exists, False otherwise
        """
        with self._lock:
            return order_id in self._orders
    
    def get_all_orders(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all orders (for debugging/testing)
        
        Returns:
            Dictionary of all orders with shipping costs
        """
        with self._lock:
            return self._orders.copy()
    
    def get_all_order_ids(self) -> List[str]:
        """
        Get all order IDs
        
        Returns:
            List of all order IDs
        """
        with self._lock:
            return list(self._orders.keys())
    
    def get_order_count(self) -> int:
        """
        Get count of stored orders
        
        Returns:
            Number of orders in storage
        """
        with self._lock:
            return len(self._orders)
    
    def clear(self) -> None:
        """Clear all orders from storage"""
        with self._lock:
            self._orders.clear()
            logger.info("Order storage cleared")


# Singleton instance
order_storage = OrderStorage()

