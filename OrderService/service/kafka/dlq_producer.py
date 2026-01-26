from typing import Dict, Any
from confluent_kafka import Producer
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro import loads as avro_loads
from config.settings import settings
from datetime import datetime
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DLQProducer:
    """
    Dead Letter Queue Producer for handling failed messages
    
    This producer sends failed messages to a DLQ topic with metadata about:
    - Original message content
    - Error details
    - Retry count
    - Timestamps
    - Processing context
    """
    
    def __init__(self):
        self.producer = None
        self.avro_schema = None
        self._load_avro_schema()
    
    def _load_avro_schema(self):
        """Load Avro schema from file for DLQ messages"""
        try:
            with open(settings.AVRO_SCHEMA_PATH, 'r') as schema_file:
                self.avro_schema = schema_file.read()
            logger.info(f"Loaded Avro schema for DLQ from {settings.AVRO_SCHEMA_PATH}")
        except FileNotFoundError:
            logger.error(f"Avro schema file not found at {settings.AVRO_SCHEMA_PATH}")
            raise
        except Exception as e:
            logger.error(f"Error loading Avro schema: {str(e)}")
            raise
    
    def _create_producer(self) -> AvroProducer:
        """Create and configure Kafka producer for DLQ with Avro serialization"""
        try:
            # DLQ schema includes original order data plus metadata
            dlq_schema_str = json.dumps({
                "type": "record",
                "name": "DLQMessage",
                "namespace": "com.ecommerce.dlq",
                "fields": [
                    {"name": "originalMessage", "type": "string"},
                    {"name": "errorMessage", "type": "string"},
                    {"name": "errorType", "type": "string"},
                    {"name": "retryCount", "type": "int"},
                    {"name": "failedAttempts", "type": "int"},
                    {"name": "firstFailureTimestamp", "type": "string"},
                    {"name": "lastFailureTimestamp", "type": "string"},
                    {"name": "originalTopic", "type": "string"},
                    {"name": "originalPartition", "type": "int"},
                    {"name": "originalOffset", "type": "long"},
                    {"name": "consumerGroup", "type": "string"}
                ]
            })
            
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
                default_value_schema=avro_loads(dlq_schema_str)
            )
            
            logger.info(f"DLQ producer created successfully. DLQ Topic: {settings.KAFKA_DLQ_TOPIC}")
            return producer
            
        except Exception as e:
            logger.error(f"Failed to create DLQ producer: {str(e)}")
            raise
    
    def connect(self):
        """Establish connection to Kafka broker"""
        try:
            if self.producer is None:
                self.producer = self._create_producer()
                logger.info("Connected to Kafka for DLQ successfully")
        except Exception as e:
            logger.error(f"Error connecting to Kafka for DLQ: {str(e)}")
            raise ConnectionError(f"Failed to connect to Kafka broker for DLQ: {str(e)}")
    
    def send_to_dlq(
        self,
        message_value: Dict[str, Any],
        message_key: str,
        error: Exception,
        retry_count: int,
        original_topic: str,
        original_partition: int,
        original_offset: int,
        first_failure_timestamp: str = None
    ) -> bool:
        """
        Send a failed message to the Dead Letter Queue
        
        Args:
            message_value: The original message content (order data)
            message_key: The message key (orderId)
            error: The exception that caused the failure
            retry_count: Number of times processing was attempted
            original_topic: Topic the message came from
            original_partition: Partition the message came from
            original_offset: Offset of the original message
            first_failure_timestamp: When the first failure occurred
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure producer is connected
            if self.producer is None:
                self.connect()
            
            current_timestamp = datetime.utcnow().isoformat() + 'Z'
            
            # Create DLQ message with metadata
            dlq_message = {
                'originalMessage': json.dumps(message_value),
                'errorMessage': str(error),
                'errorType': error.__class__.__name__,
                'retryCount': retry_count,
                'failedAttempts': retry_count + 1,  # Total attempts including initial
                'firstFailureTimestamp': first_failure_timestamp or current_timestamp,
                'lastFailureTimestamp': current_timestamp,
                'originalTopic': original_topic,
                'originalPartition': original_partition,
                'originalOffset': original_offset,
                'consumerGroup': settings.KAFKA_CONSUMER_GROUP
            }
            
            # Publish to DLQ topic
            self.producer.produce(
                topic=settings.KAFKA_DLQ_TOPIC,
                key=message_key,
                value=dlq_message,
                callback=self._delivery_callback
            )
            
            # Wait for message to be delivered
            self.producer.flush(timeout=10)
            
            logger.error(
                f"Message sent to DLQ | "
                f"OrderID: {message_key} | "
                f"Error: {error.__class__.__name__} | "
                f"Retry Count: {retry_count} | "
                f"Original Topic: {original_topic} | "
                f"Offset: {original_offset}"
            )
            
            return True
            
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to send message to DLQ: {str(e)}")
            logger.critical(f"Original message key: {message_key}, error: {error}")
            return False
    
    def _delivery_callback(self, err, msg):
        """Callback for DLQ message delivery reports"""
        if err:
            logger.critical(f"DLQ message delivery FAILED: {err}")
        else:
            logger.info(
                f"DLQ message delivered to {msg.topic()} "
                f"[{msg.partition()}] at offset {msg.offset()}"
            )
    
    def close(self):
        """Close the DLQ producer connection"""
        if self.producer:
            self.producer.flush()
            logger.info("DLQ producer closed")
            self.producer = None


# Singleton instance
dlq_producer = DLQProducer()
