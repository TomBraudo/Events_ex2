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
    AVRO_SCHEMA_PATH: Path = BASE_DIR / "schemas" / "order.avsc"
    
    # Kafka Consumer Settings
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "order-service-group")
    KAFKA_CONSUMER_CONFIG = {
        'group.id': KAFKA_CONSUMER_GROUP,
        'client.id': 'order-service-consumer',
        'auto.offset.reset': 'earliest',  # Read from beginning to get all messages
        'enable.auto.commit': True,
        'auto.commit.interval.ms': 5000,
        'max.poll.interval.ms': 300000,
    }
    
    # Business Logic Settings
    SHIPPING_COST_PERCENTAGE: float = 0.02  # 2% of totalAmount
    
    # API Settings
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8001"))


settings = Settings()

