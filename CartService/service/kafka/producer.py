import json
import time
from typing import Dict, Any
from confluent_kafka import Producer
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro import loads as avro_loads
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KafkaProducerService:
    """
    Kafka producer service with Avro serialization and Schema Registry support
    
    Features:
    - Schema caching: Falls back to local schema if Schema Registry unavailable
    - Retry logic: Handles transient failures with exponential backoff
    """
    
    def __init__(self):
        self.producer = None
        self.avro_schema = None
        self.schema_cache_path = settings.BASE_DIR / "schemas" / ".event_schema_cache"
        self._load_avro_schema()
    
    def _load_avro_schema(self):
        """
        Load Avro schema from file with caching support
        
        This ensures the service can start even if Schema Registry is temporarily unavailable
        by using a locally cached schema.
        """
        try:
            with open(settings.AVRO_SCHEMA_PATH, 'r') as schema_file:
                self.avro_schema = schema_file.read()
            logger.info(f"Loaded Avro schema from {settings.AVRO_SCHEMA_PATH}")
            
            # Cache the schema for fallback
            self._cache_schema(self.avro_schema)
            
        except FileNotFoundError:
            logger.error(f"Avro schema file not found at {settings.AVRO_SCHEMA_PATH}")
            
            # Try to load from cache
            cached_schema = self._load_cached_schema()
            if cached_schema:
                logger.warning("Using cached schema as fallback")
                self.avro_schema = cached_schema
            else:
                raise
        except Exception as e:
            logger.error(f"Error loading Avro schema: {str(e)}")
            raise
    
    def _cache_schema(self, schema: str):
        """Cache schema locally for fallback"""
        try:
            self.schema_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.schema_cache_path, 'w') as cache_file:
                cache_file.write(schema)
            logger.debug("Schema cached successfully")
        except Exception as e:
            logger.warning(f"Failed to cache schema (non-critical): {str(e)}")
    
    def _load_cached_schema(self) -> str:
        """Load schema from cache if available"""
        try:
            if self.schema_cache_path.exists():
                with open(self.schema_cache_path, 'r') as cache_file:
                    return cache_file.read()
        except Exception as e:
            logger.warning(f"Failed to load cached schema: {str(e)}")
        return None
    
    def _create_producer(self) -> AvroProducer:
        """
        Create and configure Kafka producer with Avro serialization
        
        Uses cached schema if Schema Registry is unavailable during creation.
        """
        try:
            producer_config = {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'schema.registry.url': settings.SCHEMA_REGISTRY_URL,
                **settings.KAFKA_PRODUCER_CONFIG
            }
            
            # Simple string schema for the key (orderId)
            key_schema_str = '"string"'
            
            producer = AvroProducer(
                producer_config,
                default_key_schema=avro_loads(key_schema_str),
                default_value_schema=avro_loads(self.avro_schema)
            )
            
            logger.info(f"Kafka producer created successfully. Bootstrap servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")
            return producer
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # If Schema Registry error and we have cached schema, try to continue
            if 'schema' in error_msg or 'registry' in error_msg:
                logger.warning(f"Schema Registry error during producer creation: {str(e)}")
                logger.warning("Attempting to use cached schema for producer creation")
                # The producer will still try to connect to Schema Registry later
                # but at least we can initialize with cached schema
            
            logger.error(f"Failed to create Kafka producer: {str(e)}")
            raise
    
    def connect(self):
        """Establish connection to Kafka broker"""
        try:
            if self.producer is None:
                self.producer = self._create_producer()
                logger.info("Connected to Kafka successfully")
        except Exception as e:
            logger.error(f"Error connecting to Kafka: {str(e)}")
            raise ConnectionError(f"Failed to connect to Kafka broker: {str(e)}")
    
    def publish_order_event(self, order: Dict[str, Any]) -> bool:
        """
        Publish order creation event to Kafka topic with Avro serialization
        
        Wraps order in event envelope with ORDER_CREATED type.
        
        Args:
            order: Order dictionary to be published
            
        Returns:
            bool: True if successful
            
        Raises:
            ConnectionError: If Kafka broker is not available after retries
            Exception: For other errors during publishing
        """
        from datetime import datetime
        
        order_id = order.get('orderId', 'Unknown')
        
        # Wrap order in event envelope
        event = {
            'eventType': 'ORDER_CREATED',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'orderId': order_id,
            'payload': order
        }
        
        return self._publish_event(event, order_id)
    
    def publish_status_update_event(self, order_id: str, new_status: str) -> bool:
        """
        Publish status update event to Kafka topic with Avro serialization
        
        Wraps status update in event envelope with STATUS_UPDATED type.
        
        Args:
            order_id: Order ID to update
            new_status: New status value
            
        Returns:
            bool: True if successful
            
        Raises:
            ConnectionError: If Kafka broker is not available after retries
            Exception: For other errors during publishing
        """
        from datetime import datetime
        
        # Wrap status update in event envelope
        event = {
            'eventType': 'STATUS_UPDATED',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'orderId': order_id,
            'payload': {
                'orderId': order_id,
                'status': new_status
            }
        }
        
        return self._publish_event(event, order_id)
    
    def _publish_event(self, event: Dict[str, Any], order_id: str) -> bool:
        """
        Internal method to publish event with retry logic
        
        Args:
            event: Event envelope to publish
            order_id: Order ID for logging
            
        Returns:
            bool: True if successful
        """
        last_exception = None
        event_type = event.get('eventType')
        
        for attempt in range(settings.PRODUCER_MAX_RETRIES + 1):
            try:
                # Ensure producer is connected
                if self.producer is None:
                    self.connect()
                
                # Use orderId as the key for partitioning
                key = order_id
                
                # Publish message
                self.producer.produce(
                    topic=settings.KAFKA_TOPIC,
                    key=key,
                    value=event,
                    callback=self._delivery_callback
                )
                
                # Wait for message to be delivered (flush with configurable timeout)
                remaining_messages = self.producer.flush(timeout=settings.PRODUCER_FLUSH_TIMEOUT_SECONDS)
                
                if remaining_messages > 0:
                    raise Exception(f"Failed to flush {remaining_messages} messages within timeout")
                
                logger.info(f"Successfully published {event_type} event for orderId: {order_id}")
                return True
                
            except BufferError as e:
                last_exception = e
                logger.error(f"Local producer queue is full (attempt {attempt + 1}/{settings.PRODUCER_MAX_RETRIES + 1}): {str(e)}")
                
                if attempt < settings.PRODUCER_MAX_RETRIES:
                    backoff_ms = settings.PRODUCER_RETRY_BACKOFF_MS * (2 ** attempt)
                    logger.warning(f"Retrying in {backoff_ms}ms...")
                    time.sleep(backoff_ms / 1000.0)
                else:
                    raise Exception(f"Failed to publish event after {settings.PRODUCER_MAX_RETRIES + 1} attempts - queue full: {str(e)}")
            
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                
                # Check if this is a transient error worth retrying
                is_transient = any(term in error_msg for term in [
                    'connection', 'broker', 'timeout', 'network', 'temporary', 'unavailable'
                ])
                
                if is_transient and attempt < settings.PRODUCER_MAX_RETRIES:
                    backoff_ms = settings.PRODUCER_RETRY_BACKOFF_MS * (2 ** attempt)
                    logger.warning(
                        f"Transient error publishing order {order_id} "
                        f"(attempt {attempt + 1}/{settings.PRODUCER_MAX_RETRIES + 1}): {str(e)}. "
                        f"Retrying in {backoff_ms}ms..."
                    )
                    time.sleep(backoff_ms / 1000.0)
                    # Try to reconnect
                    self.producer = None
                    continue
                
                # Non-transient error or max retries exceeded
                if 'connection' in error_msg or 'broker' in error_msg or 'timeout' in error_msg or 'network' in error_msg:
                    logger.error(f"Kafka connection error after {attempt + 1} attempts: {str(e)}")
                    raise ConnectionError(f"Kafka broker not available after {attempt + 1} attempts: {str(e)}")
                
                if 'schema' in error_msg or 'registry' in error_msg:
                    logger.error(f"Schema Registry error: {str(e)}")
                    raise Exception(f"Schema Registry error: {str(e)}")
                
                logger.error(f"Error publishing order event after {attempt + 1} attempts: {str(e)}")
                raise Exception(f"Failed to publish event: {str(e)}")
        
        # Should never reach here, but just in case
        raise Exception(f"Failed to publish event after {settings.PRODUCER_MAX_RETRIES + 1} attempts: {str(last_exception)}")
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery reports"""
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")
    
    def close(self):
        """Close the producer connection"""
        if self.producer:
            self.producer.flush()
            logger.info("Kafka producer closed")
            self.producer = None


# Singleton instance
kafka_producer_service = KafkaProducerService()

