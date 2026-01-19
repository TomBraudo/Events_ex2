import os
from pathlib import Path


class Settings:
    """Configuration settings for the application"""
    
    # Application Settings
    APP_NAME: str = "CartService"
    APP_VERSION: str = "1.0.0"
    
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC: str = os.getenv("KAFKA_TOPIC", "order-events")
    
    # Schema Registry Settings
    SCHEMA_REGISTRY_URL: str = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    
    # Avro Schema Path
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    AVRO_SCHEMA_PATH: Path = BASE_DIR / "schemas" / "order.avsc"
    
    # Kafka Producer Settings
    KAFKA_PRODUCER_CONFIG = {
        'client.id': 'cart-service-producer',
        'acks': 'all',  # Wait for all replicas to acknowledge
        'retries': 3,
        'max.in.flight.requests.per.connection': 1,  # Ensure ordering
        'enable.idempotence': True,  # Prevent duplicates
    }
    
    # API Settings
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))


settings = Settings()

