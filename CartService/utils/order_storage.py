from typing import Dict, Optional, Any
from threading import Lock


class OrderStorage:
    """Thread-safe in-memory storage for orders"""
    
    def __init__(self):
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
    
    def save_order(self, order: Dict[str, Any]) -> None:
        """
        Save an order to storage
        
        Args:
            order: Order dictionary with orderId field
        """
        with self._lock:
            order_id = order.get("orderId")
            if order_id:
                self._orders[order_id] = order
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an order by ID
        
        Args:
            order_id: The order ID to retrieve
            
        Returns:
            Order dictionary if found, None otherwise
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
    
    def update_order_status(self, order_id: str, new_status: str) -> bool:
        """
        Update the status of an existing order
        
        Args:
            order_id: The order ID to update
            new_status: The new status value
            
        Returns:
            True if update successful, False if order not found
        """
        with self._lock:
            if order_id in self._orders:
                self._orders[order_id]["status"] = new_status
                return True
            return False
    
    def get_all_orders(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all orders (for debugging/testing)
        
        Returns:
            Dictionary of all orders
        """
        with self._lock:
            return self._orders.copy()
    
    def clear(self) -> None:
        """Clear all orders from storage"""
        with self._lock:
            self._orders.clear()


# Singleton instance
order_storage = OrderStorage()

