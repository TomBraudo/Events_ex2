# E-Commerce Platform - Order Management System

A microservices-based e-commerce platform with event-driven architecture using **Apache Kafka**, **Schema Registry**, and **Avro serialization**.

## 🎯 Project Overview

This system implements an order management service (CartService) that publishes order events to Kafka. When a customer places or updates an order, the events are broadcast to all downstream consumers (inventory, billing, shipping) while maintaining order sequence consistency.

## 📁 Project Structure

```
Events_ex2/
├── CartService/              # Order Management Microservice (Producer)
│   ├── api/                  # API Layer
│   │   └── controllers/      # Request handlers
│   ├── business/             # Business Logic Layer
│   │   └── order/            # Order business logic
│   ├── service/              # Service Layer
│   │   └── kafka/            # Kafka producer with Avro
│   ├── models/               # Pydantic data models
│   ├── utils/                # Utilities (generator, storage)
│   ├── config/               # Configuration
│   ├── schemas/              # Avro schemas
│   ├── main.py               # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   └── README.md
│
├── OrderService/             # Order Consumer Microservice (Consumer)
│   ├── api/                  # API Layer
│   │   └── controllers/      # Request handlers
│   ├── business/             # Business Logic Layer
│   │   └── order/            # Order processing logic
│   ├── service/              # Service Layer
│   │   └── kafka/            # Kafka consumer with Avro
│   ├── models/               # Pydantic data models
│   ├── utils/                # Utilities (storage)
│   ├── config/               # Configuration
│   ├── schemas/              # Avro schemas
│   ├── main.py               # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   └── README.md
│
├── docker-compose.yml        # Docker Compose configuration
├── README.md                 # This file
└── QUICK_START.md
```

## 🚀 Quick Start

### Prerequisites
- Docker Desktop
- Docker Compose

### Start the System

```bash
# Start all services (Kafka, Zookeeper, Schema Registry, CartService)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f cart-service
```

The CartService API will be available at: **http://localhost:8000**

### API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🎯 Key Features

### ✅ Implemented Features

1. **RESTful API Endpoints**
   - `POST /api/create-order` - Create new orders
   - `PUT /api/update-order` - Update order status

2. **Event-Driven Architecture**
   - Kafka integration with message ordering
   - Avro serialization with Schema Registry (Bonus!)
   - Event broadcasting to all consumers

3. **Comprehensive Validation**
   - Non-empty IDs
   - Valid ISO 8601 dates
   - Items array not empty
   - Quantity >= 1
   - Price > 0
   - TotalAmount > 0 and matches item sum
   - Currency is 3-letter code
   - Status enum validation

4. **Robust Error Handling**
   - Validation errors (400)
   - Not found errors (404)
   - Kafka connection errors (503)
   - Schema Registry errors (503)
   - Generic errors (500)

5. **Layered Architecture**
   - API Layer: HTTP handling
   - Business Layer: Business logic
   - Service Layer: External integrations

6. **Auto-Generation**
   - Customer ID
   - Order date (ISO 8601)
   - Items array with random data
   - Total amount calculation
   - Currency selection
   - Initial status (pending)

## 📊 System Architecture

```
┌─────────────┐                          ┌─────────────┐
│   Client    │                          │   Client    │
└──────┬──────┘                          └──────┬──────┘
       │ HTTP (POST/PUT)                        │ HTTP (GET)
       ▼                                        ▼
┌─────────────────────────────┐      ┌─────────────────────────────┐
│   CartService (Producer)    │      │  OrderService (Consumer)    │
│   FastAPI - Port 8000       │      │   FastAPI - Port 8001       │
│  - Create orders            │      │  - Get order details        │
│  - Update order status      │      │  - Get all order IDs        │
└──────────┬──────────────────┘      └──────────┬──────────────────┘
           │                                     ▲
           ▼                                     │
┌──────────────────────────────┐                │
│   Kafka Producer Service     │                │
│  (Avro Serialization)        │                │
└──────────┬───────────────────┘                │
           │                                     │
           ▼                                     │
┌──────────────────────────────┐                │
│    Schema Registry           │◄───────────────┤
│    (Port 8081)               │                │
└──────────┬───────────────────┘                │
           │                                     │
           ▼                                     │
┌──────────────────────────────┐                │
│      Apache Kafka            │                │
│    (Port 9092)               │                │
│    Topic: order-events       │────────────────┘
└──────────┬───────────────────┘
           │                          ▲
           │                          │
           ▼                          │
    ┌──────┴──────┐         ┌────────┴─────────┐
    │             │         │  Kafka Consumer   │
┌───▼───┐  ┌─────▼─────┐   │  (Avro Deser.)    │
│Inventory│ │  Billing  │   │  - Calculate      │
│Service  │ │  Service  │   │    Shipping (2%)  │
└─────────┘ └───────────┘   │  - Store Orders   │
                             └───────────────────┘
```

## 🧪 Testing the Complete Flow

### Step 1: Create Order (Producer)

```bash
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORDER-001",
    "numItems": 3
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Order 'ORDER-001' created successfully",
  "data": {
    "orderId": "ORDER-001",
    "customerId": "CUST-1234",
    "orderDate": "2026-01-13T10:30:00Z",
    "items": [...],
    "totalAmount": 1999.98,
    "currency": "USD",
    "status": "pending"
  }
}
```

### Step 2: Get Order Details with Shipping (Consumer)

```bash
# Wait a moment for consumer to process...
curl "http://localhost:8001/api/order-details?orderId=ORDER-001"
```

**Response:**
```json
{
  "success": true,
  "message": "Order 'ORDER-001' retrieved successfully",
  "data": {
    "orderId": "ORDER-001",
    "totalAmount": 1999.98,
    "shippingCost": 39.99,
    ...
  }
}
```

### Step 3: Update Order Status (Producer)

```bash
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORDER-001",
    "status": "confirmed"
  }'
```

### Step 4: Get All Order IDs from Topic (Consumer)

```bash
curl "http://localhost:8001/api/getAllOrderIdsFromTopic?topicName=order-events"
```

**Response:**
```json
{
  "success": true,
  "topicName": "order-events",
  "orderIds": ["ORDER-001", "ORDER-002", ...],
  "count": 5
}
```

## 🎓 Bonus Features

### ✨ Avro + Schema Registry Implementation

This project uses **Avro serialization with Schema Registry** for:
- ✅ Schema versioning and evolution
- ✅ Backward/forward compatibility
- ✅ Centralized schema management
- ✅ Efficient binary serialization
- ✅ Type safety across services

**Schema Registry UI**: http://localhost:8081

## 📋 Services

| Service | Port | Role | Description |
|---------|------|------|-------------|
| CartService | 8000 | Producer | Create/update orders, publish to Kafka |
| OrderService | 8001 | Consumer | Process orders, calculate shipping costs |
| Kafka | 9092 | Broker | Distributed message broker |
| Zookeeper | 2181 | Coordinator | Kafka coordination service |
| Schema Registry | 8081 | Registry | Avro schema management |

## 🛠️ Technology Stack

- **Python 3.11**
- **FastAPI** - Modern web framework
- **Pydantic** - Data validation
- **Confluent Kafka** - Kafka client with Avro support
- **Apache Kafka** - Distributed message broker
- **Schema Registry** - Schema management
- **Docker & Docker Compose** - Containerization

## 🔧 Configuration

Environment variables (set in `docker-compose.yml`):

```yaml
KAFKA_BOOTSTRAP_SERVERS: kafka:29092
SCHEMA_REGISTRY_URL: http://schema-registry:8081
KAFKA_TOPIC: order-events
API_HOST: 0.0.0.0
API_PORT: 8000
```

## 📊 Kafka Topic Details

- **Topic Name**: `order-events`
- **Partitioning**: By `orderId` (ensures order consistency)
- **Serialization**: Avro with Schema Registry
- **Replication Factor**: 1 (demo environment)

### View Kafka Messages

```bash
# Connect to Kafka container
docker exec -it kafka bash

# View messages in order-events topic
kafka-console-consumer --bootstrap-server localhost:9092 \
  --topic order-events --from-beginning
```

## 🐛 Troubleshooting

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f cart-service
docker-compose logs -f kafka
docker-compose logs -f schema-registry
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart cart-service
```

### Clean Restart

```bash
# Stop and remove everything
docker-compose down -v

# Start fresh
docker-compose up -d
```

## 📖 Documentation

- **CartService README**: [CartService/README.md](CartService/README.md)
- **API Documentation**: http://localhost:8000/docs
- **Schema Registry**: http://localhost:8081

## ✅ Validation Summary

All crucial and realistic validations implemented:
- ✅ Non-empty string fields (orderId, customerId, itemId)
- ✅ Valid ISO 8601 date format
- ✅ Items array not empty
- ✅ Quantity >= 1 (integer)
- ✅ Price > 0 (decimal)
- ✅ TotalAmount > 0 and equals sum of (price × quantity)
- ✅ Currency is 3-letter uppercase code
- ✅ Status matches enum values (pending, confirmed, shipped, delivered, cancelled)

## 🎯 Next Steps

To extend this system, you could:
1. Add consumer services (Inventory, Billing, Shipping)
2. Implement database persistence
3. Add authentication/authorization
4. Implement monitoring and metrics
5. Add circuit breakers and retry logic
6. Implement SAGA pattern for distributed transactions

## 📄 License

This is a demonstration project for educational purposes.
