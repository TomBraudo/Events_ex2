from typing import Dict, Any, List, Optional, Callable
from confluent_kafka import Consumer
from confluent_kafka.avro import AvroConsumer
from confluent_kafka.avro import loads as avro_loads
from config.settings import settings
import logging
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KafkaConsumerService:
    """Kafka consumer service with Avro deserialization and Schema Registry support"""
    
    def __init__(self):
        self.consumer: Optional[AvroConsumer] = None
        self.avro_schema = None
        self.is_running = False
        self.consumer_thread: Optional[threading.Thread] = None
        self.message_handler: Optional[Callable] = None
        self._load_avro_schema()
    
    def _load_avro_schema(self):
        """Load Avro schema from file"""
        try:
            with open(settings.AVRO_SCHEMA_PATH, 'r') as schema_file:
                self.avro_schema = schema_file.read()
            logger.info(f"Loaded Avro schema from {settings.AVRO_SCHEMA_PATH}")
        except FileNotFoundError:
            logger.error(f"Avro schema file not found at {settings.AVRO_SCHEMA_PATH}")
            raise
        except Exception as e:
            logger.error(f"Error loading Avro schema: {str(e)}")
            raise
    
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
    
    def _consume_loop(self):
        """Main consumer loop that runs in background thread"""
        logger.info("Consumer loop started")
        
        while self.is_running:
            try:
                # Poll for messages (timeout 1 second)
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
                
                # Message successfully received
                order_data = msg.value()  # Already deserialized by AvroConsumer
                
                if order_data:
                    order_id = order_data.get('orderId', 'Unknown')
                    logger.info(f"Received order event: {order_id}, status: {order_data.get('status')}")
                    
                    # Call the message handler if set
                    if self.message_handler:
                        try:
                            self.message_handler(order_data)
                        except Exception as e:
                            logger.error(f"Error in message handler for order {order_id}: {str(e)}")
                
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

