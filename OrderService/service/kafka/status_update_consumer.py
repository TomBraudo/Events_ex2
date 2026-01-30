from typing import Dict, Any, List, Optional, Callable
from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.avro import AvroConsumer
from confluent_kafka.avro import loads as avro_loads
from config.settings import settings
from datetime import datetime
import logging
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StatusUpdateConsumerService:
    """
    Kafka consumer service for status update events with Avro deserialization,
    Schema Registry support, and Dead Letter Queue (DLQ) implementation
    """
    
    def __init__(self):
        self.consumer: Optional[AvroConsumer] = None
        self.avro_schema = None
        self.is_running = False
        self.consumer_thread: Optional[threading.Thread] = None
        self.message_handler: Optional[Callable] = None
        self.dlq_producer = None
        self._dlq_lock = threading.Lock()
        
        # Error tracking
        self.consecutive_poll_errors = 0
        self.max_consecutive_errors = settings.CONSUMER_MAX_CONSECUTIVE_ERRORS
        
        # Schema caching
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
    
    def _create_consumer(self) -> AvroConsumer:
        """Create and configure Kafka consumer with Avro deserialization"""
        try:
            # Use separate consumer group for status updates
            consumer_config = {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'schema.registry.url': settings.SCHEMA_REGISTRY_URL,
                'group.id': f'{settings.KAFKA_CONSUMER_GROUP}-status-updates',
                'client.id': 'order-service-status-update-consumer',
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': False,
                'max.poll.interval.ms': 300000,
            }
            
            consumer = AvroConsumer(consumer_config)
            
            logger.info(f"Status update Kafka consumer created successfully")
            logger.info(f"Bootstrap servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")
            logger.info(f"Consumer group: {consumer_config['group.id']}")
            return consumer
            
        except Exception as e:
            logger.error(f"Failed to create status update Kafka consumer: {str(e)}")
            raise
    
    def connect(self):
        """Establish connection to Kafka broker"""
        try:
            if self.consumer is None:
                self.consumer = self._create_consumer()
                logger.info("Status update consumer connected to Kafka successfully")
        except Exception as e:
            logger.error(f"Error connecting status update consumer to Kafka: {str(e)}")
            raise ConnectionError(f"Failed to connect to Kafka broker: {str(e)}")
    
    def subscribe(self, topics: List[str]):
        """Subscribe to Kafka topics"""
        try:
            if self.consumer is None:
                self.connect()
            
            self.consumer.subscribe(topics)
            logger.info(f"Status update consumer subscribed to topics: {topics}")
            
        except Exception as e:
            logger.error(f"Error subscribing to topics: {str(e)}")
            raise
    
    def set_message_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """Set the callback function to handle received messages"""
        self.message_handler = handler
    
    def start_consuming(self, topics: List[str] = None):
        """Start consuming messages in a background thread"""
        if topics is None:
            topics = [settings.KAFKA_STATUS_UPDATE_TOPIC]
        
        if self.is_running:
            logger.warning("Status update consumer is already running")
            return
        
        self.subscribe(topics)
        self.is_running = True
        
        # Start consumer in a separate thread
        self.consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
        self.consumer_thread.start()
        logger.info("Started consuming status update messages in background thread")
    
    def _get_dlq_producer(self):
        """Lazy initialization of DLQ producer with thread-safety"""
        if self.dlq_producer is None:
            with self._dlq_lock:
                if self.dlq_producer is None:
                    from .dlq_producer import dlq_producer
                    self.dlq_producer = dlq_producer
                    self.dlq_producer.connect()
                    logger.info("DLQ producer initialized for status update consumer")
        return self.dlq_producer
    
    def _calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff delay in seconds"""
        backoff_ms = min(
            settings.DLQ_RETRY_BACKOFF_MS * (2 ** retry_count),
            settings.DLQ_MAX_BACKOFF_MS
        )
        return backoff_ms / 1000.0
    
    def _commit_offset_with_retry(self, msg) -> bool:
        """Commit offset with retry logic"""
        for attempt in range(settings.CONSUMER_COMMIT_MAX_RETRIES + 1):
            try:
                self.consumer.commit(message=msg, asynchronous=False)
                logger.debug(
                    f"Status update offset committed: topic={msg.topic()}, "
                    f"partition={msg.partition()}, offset={msg.offset()}"
                )
                return True
                
            except Exception as commit_error:
                if attempt < settings.CONSUMER_COMMIT_MAX_RETRIES:
                    backoff_ms = settings.CONSUMER_COMMIT_RETRY_BACKOFF_MS * (2 ** attempt)
                    logger.warning(
                        f"Failed to commit status update offset (attempt {attempt + 1}/{settings.CONSUMER_COMMIT_MAX_RETRIES + 1}): {commit_error}. "
                        f"Retrying in {backoff_ms}ms..."
                    )
                    time.sleep(backoff_ms / 1000.0)
                else:
                    logger.error(
                        f"Failed to commit status update offset after {settings.CONSUMER_COMMIT_MAX_RETRIES + 1} attempts: {commit_error}. "
                        f"Message may be reprocessed on restart!"
                    )
                    return False
        
        return False
    
    def _process_message_with_retry(self, msg) -> bool:
        """Process a message with retry logic and DLQ support"""
        status_update_data = msg.value()
        
        if not status_update_data:
            logger.warning("Received empty status update message, skipping")
            return True
        
        order_id = status_update_data.get('orderId', 'Unknown')
        first_failure_timestamp = None
        
        # Retry loop
        for attempt in range(settings.DLQ_MAX_RETRIES + 1):
            try:
                logger.info(
                    f"Processing status update event: {order_id}, "
                    f"status: {status_update_data.get('status')}, "
                    f"attempt: {attempt + 1}/{settings.DLQ_MAX_RETRIES + 1}"
                )
                
                # Call the message handler
                if self.message_handler:
                    self.message_handler(status_update_data)
                
                # Success!
                if attempt > 0:
                    logger.info(f"Status update for {order_id} processed successfully after {attempt} retries")
                else:
                    logger.info(f"Status update for {order_id} processed successfully")
                
                return True
                
            except Exception as e:
                error_type = e.__class__.__name__
                logger.error(
                    f"Error processing status update for {order_id} (attempt {attempt + 1}): "
                    f"{error_type}: {str(e)}"
                )
                
                # Track first failure timestamp
                if first_failure_timestamp is None:
                    first_failure_timestamp = datetime.utcnow().isoformat() + 'Z'
                
                # Check if this was the last attempt
                if attempt >= settings.DLQ_MAX_RETRIES:
                    # Max retries exceeded - send to DLQ
                    logger.error(
                        f"Max retries ({settings.DLQ_MAX_RETRIES}) exceeded for status update {order_id}. "
                        f"Sending to DLQ..."
                    )
                    
                    try:
                        dlq_producer = self._get_dlq_producer()
                        success = dlq_producer.send_to_dlq(
                            message_value=status_update_data,
                            message_key=order_id,
                            error=e,
                            retry_count=attempt,
                            original_topic=msg.topic(),
                            original_partition=msg.partition(),
                            original_offset=msg.offset(),
                            first_failure_timestamp=first_failure_timestamp
                        )
                        
                        if success:
                            logger.info(f"Status update for {order_id} successfully sent to DLQ")
                            return True
                        else:
                            logger.critical(
                                f"CRITICAL: Failed to send status update for {order_id} to DLQ. "
                                f"Message will be lost!"
                            )
                            return True
                            
                    except Exception as dlq_error:
                        logger.critical(
                            f"CRITICAL: Exception while sending status update to DLQ for {order_id}: "
                            f"{str(dlq_error)}. Message will be lost!"
                        )
                        return True
                
                else:
                    # Calculate backoff and wait before next retry
                    backoff_seconds = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Will retry status update for {order_id} in {backoff_seconds:.1f} seconds "
                        f"(retry {attempt + 1}/{settings.DLQ_MAX_RETRIES})"
                    )
                    time.sleep(backoff_seconds)
    
    def _consume_loop(self):
        """Main consumer loop with DLQ support"""
        logger.info("Status update consumer loop started with DLQ support")
        logger.info(f"DLQ Topic: {settings.KAFKA_DLQ_TOPIC}")
        logger.info(f"Max Retries: {settings.DLQ_MAX_RETRIES}")
        
        while self.is_running:
            try:
                # Poll for messages
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    self.consecutive_poll_errors = 0
                    continue
                
                if msg.error():
                    self.consecutive_poll_errors += 1
                    logger.error(
                        f"Status update consumer error ({self.consecutive_poll_errors}/{self.max_consecutive_errors}): "
                        f"{msg.error()}"
                    )
                    
                    if self.consecutive_poll_errors >= self.max_consecutive_errors:
                        logger.critical(
                            f"CRITICAL: Status update consumer exceeded {self.max_consecutive_errors} consecutive poll errors. "
                            f"Stopping consumer."
                        )
                        self.is_running = False
                        break
                    
                    continue
                
                # Reset error counter on successful message
                self.consecutive_poll_errors = 0
                
                # Process message with retry logic
                self._process_message_with_retry(msg)
                
                # Commit offset after message is handled
                self._commit_offset_with_retry(msg)
                
            except KeyboardInterrupt:
                logger.info("Status update consumer interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in status update consumer loop: {str(e)}")
                time.sleep(1)
        
        logger.info("Status update consumer loop stopped")
    
    def stop_consuming(self):
        """Stop the consumer loop"""
        logger.info("Stopping status update consumer...")
        self.is_running = False
        
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)
        
        logger.info("Status update consumer stopped")
    
    def close(self):
        """Close the consumer connection"""
        self.stop_consuming()
        
        if self.consumer:
            self.consumer.close()
            logger.info("Status update Kafka consumer closed")
            self.consumer = None


# Singleton instance
status_update_consumer_service = StatusUpdateConsumerService()
