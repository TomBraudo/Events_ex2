import json
import time
from typing import Dict, Any
from confluent_kafka import Producer
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro import loads as avro_loads
from config.settings import settings
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StatusUpdateProducerService:
    """
    Kafka producer service for status update events with Avro serialization
    
    This producer publishes lightweight status update events to a separate topic,
    allowing async order updates without synchronous calls to OrderService.
    """
    
    def __init__(self):
        self.producer = None
        self.avro_schema = None
        self.schema_cache_path = settings.BASE_DIR / "schemas" / ".status_update_schema_cache"
        self._load_avro_schema()
    
    def _load_avro_schema(self):
        """Load status update Avro schema from file with caching support"""
        try:
            schema_path = settings.BASE_DIR / "schemas" / "status_update.avsc"
            with open(schema_path, 'r') as schema_file:
                self.avro_schema = schema_file.read()
            logger.info(f"Loaded status update Avro schema from {schema_path}")
            
            # Cache the schema for fallback
            self._cache_schema(self.avro_schema)
            
        except FileNotFoundError:
            logger.error(f"Status update Avro schema file not found")
            
            # Try to load from cache
            cached_schema = self._load_cached_schema()
            if cached_schema:
                logger.warning("Using cached status update schema as fallback")
                self.avro_schema = cached_schema
            else:
                raise
        except Exception as e:
            logger.error(f"Error loading status update Avro schema: {str(e)}")
            raise
    
    def _cache_schema(self, schema: str):
        """Cache schema locally for fallback"""
        try:
            self.schema_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.schema_cache_path, 'w') as cache_file:
                cache_file.write(schema)
            logger.debug("Status update schema cached successfully")
        except Exception as e:
            logger.warning(f"Failed to cache status update schema (non-critical): {str(e)}")
    
    def _load_cached_schema(self) -> str:
        """Load schema from cache if available"""
        try:
            if self.schema_cache_path.exists():
                with open(self.schema_cache_path, 'r') as cache_file:
                    return cache_file.read()
        except Exception as e:
            logger.warning(f"Failed to load cached status update schema: {str(e)}")
        return None
    
    def _create_producer(self) -> AvroProducer:
        """Create and configure Kafka producer with Avro serialization"""
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
            
            logger.info(f"Status update Kafka producer created successfully")
            return producer
            
        except Exception as e:
            logger.error(f"Failed to create status update Kafka producer: {str(e)}")
            raise
    
    def connect(self):
        """Establish connection to Kafka broker"""
        try:
            if self.producer is None:
                self.producer = self._create_producer()
                logger.info("Status update producer connected to Kafka successfully")
        except Exception as e:
            logger.error(f"Error connecting status update producer to Kafka: {str(e)}")
            raise ConnectionError(f"Failed to connect to Kafka broker: {str(e)}")
    
    def publish_status_update(self, order_id: str, new_status: str) -> bool:
        """
        Publish status update event to Kafka topic with Avro serialization
        
        Args:
            order_id: Order ID to update
            new_status: New status value
            
        Returns:
            bool: True if successful
            
        Raises:
            ConnectionError: If Kafka broker is not available after retries
            Exception: For other errors during publishing
        """
        last_exception = None
        status_topic = settings.KAFKA_STATUS_UPDATE_TOPIC
        
        for attempt in range(settings.PRODUCER_MAX_RETRIES + 1):
            try:
                # Ensure producer is connected
                if self.producer is None:
                    self.connect()
                
                # Create status update event
                status_update_event = {
                    "orderId": order_id,
                    "status": new_status,
                    "updateTimestamp": datetime.utcnow().isoformat() + 'Z',
                    "eventType": "STATUS_UPDATE"
                }
                
                # Publish message
                self.producer.produce(
                    topic=status_topic,
                    key=order_id,
                    value=status_update_event,
                    callback=self._delivery_callback
                )
                
                # Wait for message to be delivered
                remaining_messages = self.producer.flush(timeout=settings.PRODUCER_FLUSH_TIMEOUT_SECONDS)
                
                if remaining_messages > 0:
                    raise Exception(f"Failed to flush {remaining_messages} messages within timeout")
                
                logger.info(
                    f"Successfully published status update event: "
                    f"orderId={order_id}, status={new_status}, topic={status_topic}"
                )
                return True
                
            except BufferError as e:
                last_exception = e
                logger.error(f"Local producer queue is full (attempt {attempt + 1}/{settings.PRODUCER_MAX_RETRIES + 1}): {str(e)}")
                
                if attempt < settings.PRODUCER_MAX_RETRIES:
                    backoff_ms = settings.PRODUCER_RETRY_BACKOFF_MS * (2 ** attempt)
                    logger.warning(f"Retrying in {backoff_ms}ms...")
                    time.sleep(backoff_ms / 1000.0)
                else:
                    raise Exception(f"Failed to publish status update after {settings.PRODUCER_MAX_RETRIES + 1} attempts - queue full: {str(e)}")
            
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
                        f"Transient error publishing status update for {order_id} "
                        f"(attempt {attempt + 1}/{settings.PRODUCER_MAX_RETRIES + 1}): {str(e)}. "
                        f"Retrying in {backoff_ms}ms..."
                    )
                    time.sleep(backoff_ms / 1000.0)
                    # Try to reconnect
                    self.producer = None
                    continue
                
                # Non-transient error or max retries exceeded
                if 'connection' in error_msg or 'broker' in error_msg or 'timeout' in error_msg:
                    logger.error(f"Kafka connection error after {attempt + 1} attempts: {str(e)}")
                    raise ConnectionError(f"Kafka broker not available after {attempt + 1} attempts: {str(e)}")
                
                if 'schema' in error_msg or 'registry' in error_msg:
                    logger.error(f"Schema Registry error: {str(e)}")
                    raise Exception(f"Schema Registry error: {str(e)}")
                
                logger.error(f"Error publishing status update event after {attempt + 1} attempts: {str(e)}")
                raise Exception(f"Failed to publish status update: {str(e)}")
        
        # Should never reach here, but just in case
        raise Exception(f"Failed to publish status update after {settings.PRODUCER_MAX_RETRIES + 1} attempts: {str(last_exception)}")
    
    def _delivery_callback(self, err, msg):
        """Callback for message delivery reports"""
        if err:
            logger.error(f"Status update message delivery failed: {err}")
        else:
            logger.info(f"Status update delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")
    
    def close(self):
        """Close the producer connection"""
        if self.producer:
            self.producer.flush()
            logger.info("Status update Kafka producer closed")
            self.producer = None


# Singleton instance
status_update_producer_service = StatusUpdateProducerService()
