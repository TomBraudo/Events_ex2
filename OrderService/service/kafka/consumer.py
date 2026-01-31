from typing import Dict, Any, List, Optional, Callable, Tuple
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


class KafkaConsumerService:
    """
    Kafka consumer service with Avro deserialization, Schema Registry support,
    and Dead Letter Queue (DLQ) implementation
    """
    
    def __init__(self):
        self.consumer: Optional[AvroConsumer] = None
        self.avro_schema = None
        self.is_running = False
        self.consumer_thread: Optional[threading.Thread] = None
        self.message_handler: Optional[Callable] = None
        self.dlq_producer = None  # Will be initialized on first use
        self._dlq_lock = threading.Lock()  # Lock for thread-safe DLQ initialization
        
        # Error tracking
        self.consecutive_poll_errors = 0
        self.max_consecutive_errors = settings.CONSUMER_MAX_CONSECUTIVE_ERRORS
        
        # Schema caching
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
    
    def _create_consumer(self) -> AvroConsumer:
        """Create and configure Kafka consumer with Avro deserialization"""
        try:
            consumer_config = {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'schema.registry.url': settings.SCHEMA_REGISTRY_URL,
                **settings.KAFKA_CONSUMER_CONFIG
            }
            
            consumer = AvroConsumer(consumer_config)
            
            logger.info(f"Kafka consumer created successfully")
            logger.info(f"Bootstrap servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")
            logger.info(f"Consumer group: {settings.KAFKA_CONSUMER_GROUP}")
            return consumer
            
        except Exception as e:
            logger.error(f"Failed to create Kafka consumer: {str(e)}")
            raise
    
    def connect(self):
        """Establish connection to Kafka broker"""
        try:
            if self.consumer is None:
                self.consumer = self._create_consumer()
                logger.info("Connected to Kafka successfully")
        except Exception as e:
            logger.error(f"Error connecting to Kafka: {str(e)}")
            raise ConnectionError(f"Failed to connect to Kafka broker: {str(e)}")
    
    def subscribe(self, topics: List[str]):
        """
        Subscribe to Kafka topics
        
        Args:
            topics: List of topic names to subscribe to
        """
        try:
            if self.consumer is None:
                self.connect()
            
            self.consumer.subscribe(topics)
            logger.info(f"Subscribed to topics: {topics}")
            
        except Exception as e:
            logger.error(f"Error subscribing to topics: {str(e)}")
            raise
    
    def set_message_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """
        Set the callback function to handle received messages
        
        Args:
            handler: Callback function that receives the order dictionary
        """
        self.message_handler = handler
    
    def start_consuming(self, topics: List[str] = None):
        """
        Start consuming messages in a background thread
        
        Args:
            topics: List of topics to subscribe to (default: [settings.KAFKA_TOPIC])
        """
        if topics is None:
            topics = [settings.KAFKA_TOPIC]
        
        if self.is_running:
            logger.warning("Consumer is already running")
            return
        
        self.subscribe(topics)
        self.is_running = True
        
        # Start consumer in a separate thread
        self.consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
        self.consumer_thread.start()
        logger.info("Started consuming messages in background thread")
    
    def _get_dlq_producer(self):
        """
        Lazy initialization of DLQ producer with thread-safety
        
        Uses double-checked locking pattern to ensure only one instance is created
        even when called from multiple threads.
        """
        if self.dlq_producer is None:
            with self._dlq_lock:
                # Double-check after acquiring lock
                if self.dlq_producer is None:
                    from .dlq_producer import dlq_producer
                    self.dlq_producer = dlq_producer
                    self.dlq_producer.connect()
                    logger.info("DLQ producer initialized and connected")
        return self.dlq_producer
    
    def _calculate_backoff(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay in seconds
        
        Args:
            retry_count: Current retry attempt number
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff: initial_backoff * (2 ^ retry_count)
        backoff_ms = min(
            settings.DLQ_RETRY_BACKOFF_MS * (2 ** retry_count),
            settings.DLQ_MAX_BACKOFF_MS
        )
        return backoff_ms / 1000.0
    
    def _commit_offset_with_retry(self, msg) -> bool:
        """
        Commit offset with retry logic to prevent duplicate processing
        
        Args:
            msg: Kafka message to commit
            
        Returns:
            bool: True if committed successfully
        """
        for attempt in range(settings.CONSUMER_COMMIT_MAX_RETRIES + 1):
            try:
                self.consumer.commit(message=msg, asynchronous=False)
                logger.debug(
                    f"Offset committed: topic={msg.topic()}, "
                    f"partition={msg.partition()}, offset={msg.offset()}"
                )
                return True
                
            except Exception as commit_error:
                if attempt < settings.CONSUMER_COMMIT_MAX_RETRIES:
                    backoff_ms = settings.CONSUMER_COMMIT_RETRY_BACKOFF_MS * (2 ** attempt)
                    logger.warning(
                        f"Failed to commit offset (attempt {attempt + 1}/{settings.CONSUMER_COMMIT_MAX_RETRIES + 1}): {commit_error}. "
                        f"Retrying in {backoff_ms}ms..."
                    )
                    time.sleep(backoff_ms / 1000.0)
                else:
                    logger.error(
                        f"Failed to commit offset after {settings.CONSUMER_COMMIT_MAX_RETRIES + 1} attempts: {commit_error}. "
                        f"Message may be reprocessed on restart!"
                    )
                    return False
        
        return False
    
    def _process_message_with_retry(self, msg) -> bool:
        """
        Process a message with retry logic and DLQ support
        
        This method retries the SAME message multiple times with exponential backoff
        before sending to DLQ. It does NOT poll for new messages between retries.
        
        Args:
            msg: Kafka message
            
        Returns:
            bool: True if handled (success or sent to DLQ), False should never happen
        """
        event = msg.value()  # Already deserialized by AvroConsumer
        
        if not event:
            logger.warning("Received empty message, skipping")
            return True
        
        order_id = event.get('orderId', 'Unknown')
        event_type = event.get('eventType', 'UNKNOWN')
        first_failure_timestamp = None
        
        # Retry loop - process the same message up to MAX_RETRIES + 1 times
        for attempt in range(settings.DLQ_MAX_RETRIES + 1):
            try:
                logger.info(
                    f"Processing event: type={event_type}, orderId={order_id}, "
                    f"attempt: {attempt + 1}/{settings.DLQ_MAX_RETRIES + 1}"
                )
                
                # Call the message handler with the event envelope
                if self.message_handler:
                    self.message_handler(event)
                
                # Success!
                if attempt > 0:
                    logger.info(f"Order {order_id} processed successfully after {attempt} retries")
                else:
                    logger.info(f"Order {order_id} processed successfully")
                
                return True
                
            except Exception as e:
                error_type = e.__class__.__name__
                logger.error(
                    f"Error processing order {order_id} (attempt {attempt + 1}): "
                    f"{error_type}: {str(e)}"
                )
                
                # Track first failure timestamp
                if first_failure_timestamp is None:
                    first_failure_timestamp = datetime.utcnow().isoformat() + 'Z'
                
                # Check if this was the last attempt
                if attempt >= settings.DLQ_MAX_RETRIES:
                    # Max retries exceeded - send to DLQ
                    logger.error(
                        f"Max retries ({settings.DLQ_MAX_RETRIES}) exceeded for order {order_id}. "
                        f"Sending to DLQ..."
                    )
                    
                    try:
                        dlq_producer = self._get_dlq_producer()
                        success = dlq_producer.send_to_dlq(
                            message_value=event,
                            message_key=order_id,
                            error=e,
                            retry_count=attempt,
                            original_topic=msg.topic(),
                            original_partition=msg.partition(),
                            original_offset=msg.offset(),
                            first_failure_timestamp=first_failure_timestamp
                        )
                        
                        if success:
                            logger.info(f"Order {order_id} successfully sent to DLQ")
                            return True
                        else:
                            logger.critical(
                                f"CRITICAL: Failed to send order {order_id} to DLQ. "
                                f"Message will be lost!"
                            )
                            return True  # Commit anyway to avoid infinite loop
                            
                    except Exception as dlq_error:
                        logger.critical(
                            f"CRITICAL: Exception while sending to DLQ for order {order_id}: "
                            f"{str(dlq_error)}. Message will be lost!"
                        )
                        return True  # Commit anyway to avoid blocking partition
                
                else:
                    # Calculate backoff and wait before next retry
                    backoff_seconds = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Will retry order {order_id} in {backoff_seconds:.1f} seconds "
                        f"(retry {attempt + 1}/{settings.DLQ_MAX_RETRIES})"
                    )
                    time.sleep(backoff_seconds)
                    # Continue to next attempt
    
    def _consume_loop(self):
        """
        Main consumer loop with DLQ support
        
        This loop:
        1. Polls for messages
        2. Processes with retry logic (retries happen inside _process_message_with_retry)
        3. Commits offset after processing completes (success or DLQ)
        """
        logger.info("Consumer loop started with DLQ support")
        logger.info(f"DLQ Topic: {settings.KAFKA_DLQ_TOPIC}")
        logger.info(f"Max Retries: {settings.DLQ_MAX_RETRIES}")
        logger.info(f"Initial Backoff: {settings.DLQ_RETRY_BACKOFF_MS}ms")
        
        while self.is_running:
            try:
                # Poll for messages (timeout 1 second)
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    # Reset error counter on successful poll (even if no message)
                    self.consecutive_poll_errors = 0
                    continue
                
                if msg.error():
                    self.consecutive_poll_errors += 1
                    logger.error(
                        f"Consumer error ({self.consecutive_poll_errors}/{self.max_consecutive_errors}): "
                        f"{msg.error()}"
                    )
                    
                    # Check if we've exceeded max consecutive errors
                    if self.consecutive_poll_errors >= self.max_consecutive_errors:
                        logger.critical(
                            f"CRITICAL: Consumer exceeded {self.max_consecutive_errors} consecutive poll errors. "
                            f"Stopping consumer to prevent resource exhaustion."
                        )
                        self.is_running = False
                        break
                    
                    continue
                
                # Reset error counter on successful message
                self.consecutive_poll_errors = 0
                
                # Process message with retry logic (blocks until handled)
                self._process_message_with_retry(msg)
                
                # Commit offset after message is handled (success or DLQ) with retry
                self._commit_offset_with_retry(msg)
                
            except KeyboardInterrupt:
                logger.info("Consumer interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in consumer loop: {str(e)}")
                time.sleep(1)  # Wait before retrying
        
        logger.info("Consumer loop stopped")
    
    def stop_consuming(self):
        """Stop the consumer loop"""
        logger.info("Stopping consumer...")
        self.is_running = False
        
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)
        
        logger.info("Consumer stopped")
    
    def get_all_messages_from_topic(self, topic_name: str, timeout_seconds: int = 5) -> List[Dict[str, Any]]:
        """
        Read all messages from a specific topic (for getAllOrderIdsFromTopic endpoint)
        
        Args:
            topic_name: Name of the topic to read from
            timeout_seconds: How long to wait for messages
            
        Returns:
            List of all order dictionaries from the topic
        """
        messages = []
        temp_consumer = None
        
        try:
            # Create a temporary consumer with a unique group ID to read from beginning
            temp_config = {
                'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                'schema.registry.url': settings.SCHEMA_REGISTRY_URL,
                'group.id': f'temp-reader-{int(time.time())}',
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': False,
            }
            
            temp_consumer = AvroConsumer(temp_config)
            temp_consumer.subscribe([topic_name])
            
            logger.info(f"Reading all messages from topic: {topic_name}")
            
            # Read messages until timeout
            start_time = time.time()
            no_message_count = 0
            
            while time.time() - start_time < timeout_seconds:
                msg = temp_consumer.poll(timeout=0.5)
                
                if msg is None:
                    no_message_count += 1
                    # If no messages for 2 seconds, assume we've read everything
                    if no_message_count > 4:
                        break
                    continue
                
                if msg.error():
                    logger.error(f"Error reading message: {msg.error()}")
                    continue
                
                # Reset no message counter
                no_message_count = 0
                
                # Add message to list
                order_data = msg.value()
                if order_data:
                    messages.append(order_data)
            
            logger.info(f"Read {len(messages)} messages from topic {topic_name}")
            return messages
            
        except Exception as e:
            logger.error(f"Error reading from topic {topic_name}: {str(e)}")
            raise Exception(f"Failed to read from topic: {str(e)}")
        
        finally:
            if temp_consumer:
                temp_consumer.close()
    
    def close(self):
        """Close the consumer connection"""
        self.stop_consuming()
        
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer closed")
            self.consumer = None


# Singleton instance
kafka_consumer_service = KafkaConsumerService()

