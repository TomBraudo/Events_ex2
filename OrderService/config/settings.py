import os
from pathlib import Path


class Settings:
    """Configuration settings for OrderService (Consumer)"""
    
    # Application Settings
    APP_NAME: str = "OrderService"
    APP_VERSION: str = "1.0.0"
    
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC: str = os.getenv("KAFKA_TOPIC", "order-events")
    
    # Schema Registry Settings
    SCHEMA_REGISTRY_URL: str = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    
    # Avro Schema Path
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    AVRO_SCHEMA_PATH: Path = BASE_DIR / "schemas" / "order_event.avsc"
    
    # Kafka Consumer Settings
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "order-service-group")
    KAFKA_CONSUMER_CONFIG = {
        'group.id': KAFKA_CONSUMER_GROUP,
        'client.id': 'order-service-consumer',
        'auto.offset.reset': 'earliest',  # Read from beginning to get all messages
        'enable.auto.commit': False,  # Manual offset management for DLQ support
        'max.poll.interval.ms': 300000,
    }
    
    # Dead Letter Queue (DLQ) Settings
    KAFKA_DLQ_TOPIC: str = os.getenv("KAFKA_DLQ_TOPIC", "order-events-dlq")
    DLQ_MAX_RETRIES: int = int(os.getenv("DLQ_MAX_RETRIES", "3"))
    DLQ_RETRY_BACKOFF_MS: int = int(os.getenv("DLQ_RETRY_BACKOFF_MS", "1000"))  # Initial backoff in ms
    DLQ_MAX_BACKOFF_MS: int = int(os.getenv("DLQ_MAX_BACKOFF_MS", "30000"))  # Max backoff 30 seconds
    
    # Kafka Producer Settings (for DLQ)
    KAFKA_PRODUCER_CONFIG = {
        'client.id': 'order-service-dlq-producer',
        'acks': 'all',  # Wait for all replicas
        'retries': 3,
        'max.in.flight.requests.per.connection': 1,
        'enable.idempotence': True,  # Prevent duplicate DLQ messages
        'compression.type': 'gzip',
    }
    
    # DLQ Producer Retry Configuration
    DLQ_PRODUCER_MAX_RETRIES: int = int(os.getenv("DLQ_PRODUCER_MAX_RETRIES", "3"))
    DLQ_PRODUCER_RETRY_BACKOFF_MS: int = int(os.getenv("DLQ_PRODUCER_RETRY_BACKOFF_MS", "1000"))
    DLQ_FLUSH_TIMEOUT_SECONDS: int = int(os.getenv("DLQ_FLUSH_TIMEOUT_SECONDS", "10"))
    
    # Consumer Commit Retry Configuration
    CONSUMER_COMMIT_MAX_RETRIES: int = int(os.getenv("CONSUMER_COMMIT_MAX_RETRIES", "3"))
    CONSUMER_COMMIT_RETRY_BACKOFF_MS: int = int(os.getenv("CONSUMER_COMMIT_RETRY_BACKOFF_MS", "500"))
    
    # Consumer Error Tracking
    CONSUMER_MAX_CONSECUTIVE_ERRORS: int = int(os.getenv("CONSUMER_MAX_CONSECUTIVE_ERRORS", "10"))
    
    # Business Logic Settings
    SHIPPING_COST_PERCENTAGE: float = 0.02  # 2% of totalAmount
    
    # API Settings
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8001"))


settings = Settings()

