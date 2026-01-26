from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.controllers import order_router
from service.kafka import KafkaConsumerService, dlq_producer
from business.order import OrderProcessor
from config.settings import settings
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="E-Commerce Order Consumer Service with Kafka and Avro",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(order_router)

# Global instances
kafka_consumer = KafkaConsumerService()
order_processor = OrderProcessor()


@app.on_event("startup")
async def startup_event():
    """Run on application startup - start Kafka consumer"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Kafka Bootstrap Servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Schema Registry URL: {settings.SCHEMA_REGISTRY_URL}")
    logger.info(f"Kafka Topic: {settings.KAFKA_TOPIC}")
    logger.info(f"Consumer Group: {settings.KAFKA_CONSUMER_GROUP}")
    
    try:
        # Set the message handler to process orders
        kafka_consumer.set_message_handler(order_processor.process_order_event)
        
        # Start consuming messages in background
        kafka_consumer.start_consuming([settings.KAFKA_TOPIC])
        
        logger.info("✅ Kafka consumer started successfully - listening for order events")
        
    except Exception as e:
        logger.error(f"❌ Failed to start Kafka consumer: {str(e)}")
        logger.warning("⚠️  API will still be available, but order events won't be processed")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown - stop Kafka consumer and DLQ producer"""
    logger.info(f"Shutting down {settings.APP_NAME}")
    
    try:
        kafka_consumer.stop_consuming()
        kafka_consumer.close()
        logger.info("Kafka consumer stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping Kafka consumer: {str(e)}")
    
    try:
        dlq_producer.close()
        logger.info("DLQ producer closed successfully")
    except Exception as e:
        logger.error(f"Error closing DLQ producer: {str(e)}")


@app.get("/", tags=["health"])
async def root():
    """Root endpoint - health check"""
    order_count = order_processor.get_order_count()
    
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "role": "Consumer",
        "kafka_broker": settings.KAFKA_BOOTSTRAP_SERVERS,
        "schema_registry": settings.SCHEMA_REGISTRY_URL,
        "consuming_topic": settings.KAFKA_TOPIC,
        "consumer_group": settings.KAFKA_CONSUMER_GROUP,
        "processed_orders": order_count
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "consumer_running": kafka_consumer.is_running
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {settings.API_HOST}:{settings.API_PORT}")
    
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level="info"
    )

