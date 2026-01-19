import json
from typing import Dict, Any
from confluent_kafka import Producer
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro import loads as avro_loads
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KafkaProducerService:
    """Kafka producer service with Avro serialization and Schema Registry support"""
    
    def __init__(self):
        self.producer = None
        self.avro_schema = None
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
            
            logger.info(f"Kafka producer created successfully. Bootstrap servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")
            return producer
            
        except Exception as e:
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
        Publish order event to Kafka topic with Avro serialization
        
        Args:
            order: Order dictionary to be published
            
        Returns:
            bool: True if successful, False otherwise
            
        Raises:
            ConnectionError: If Kafka broker is not available
            Exception: For other errors during publishing
        """
        try:
            # Ensure producer is connected
            if self.producer is None:
                self.connect()
            
            # Use orderId as the key for partitioning (ensures order events from same order go to same partition)
            # AvroProducer will serialize this as a string using the key schema
            key = order.get('orderId', '')
            
            # Publish message
            self.producer.produce(
                topic=settings.KAFKA_TOPIC,
                key=key,
                value=order,
                callback=self._delivery_callback
            )
            
            # Wait for message to be delivered (flush)
            self.producer.flush(timeout=10)
            
            logger.info(f"Successfully published order event for orderId: {order.get('orderId')}")
            return True
            
        except BufferError as e:
            logger.error(f"Local producer queue is full: {str(e)}")
            raise Exception(f"Failed to publish event - queue full: {str(e)}")
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for connection-related errors
            if any(term in error_msg for term in ['connection', 'broker', 'timeout', 'network']):
                logger.error(f"Kafka connection error: {str(e)}")
                raise ConnectionError(f"Kafka broker not available: {str(e)}")
            
            # Check for schema registry errors
            if 'schema' in error_msg or 'registry' in error_msg:
                logger.error(f"Schema Registry error: {str(e)}")
                raise Exception(f"Schema Registry error: {str(e)}")
            
            # Generic error
            logger.error(f"Error publishing order event: {str(e)}")
            raise Exception(f"Failed to publish event: {str(e)}")
    
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

