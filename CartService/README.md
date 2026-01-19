# CartService - E-Commerce Order Management with Kafka & Avro

A microservice for managing e-commerce orders with event-driven architecture using **Apache Kafka**, **Schema Registry**, and **Avro serialization**.

## 🚀 Features

- ✅ **RESTful API** with FastAPI
- ✅ **Kafka Integration** with Avro serialization
- ✅ **Schema Registry** for schema management (Bonus Points!)
- ✅ **Layered Architecture** (API, Business, Service)
- ✅ **Comprehensive Validation** (Pydantic models)
- ✅ **Error Handling** (Connection, Broker, Schema Registry errors)
- ✅ **Docker Compose** setup for easy deployment

## 📁 Project Structure

```
CartService/
├── api/
│   └── controllers/
│       ├── __init__.py
│       └── order_controller.py       # API endpoints
├── business/
│   └── order/
│       ├── __init__.py
│       └── order_service.py          # Business logic
├── service/
│   └── kafka/
│       ├── __init__.py
│       └── producer.py               # Kafka producer with Avro
├── models/
│   ├── __init__.py
│   └── order.py                      # Pydantic models
├── utils/
│   ├── __init__.py
│   ├── order_generator.py            # Order data generator
│   └── order_storage.py              # In-memory storage
├── config/
│   ├── __init__.py
│   └── settings.py                   # Configuration
├── schemas/
│   └── order.avsc                    # Avro schema
├── main.py                           # FastAPI application
├── requirements.txt
└── Dockerfile
```

## 🛠️ Technology Stack

- **Python 3.11**
- **FastAPI** - Modern web framework
- **Pydantic** - Data validation
- **Confluent Kafka** - Kafka client with Avro support
- **Apache Kafka** - Message broker
- **Schema Registry** - Schema management
- **Docker & Docker Compose**

## 📋 API Endpoints

### 1. POST `/api/create-order`

Creates a new order and publishes it to Kafka.

**Request Body:**
```json
{
  "orderId": "ORDER-001",
  "numItems": 3
}
```

**Auto-Generated Fields:**
- `customerId` - Random customer ID
- `orderDate` - Current timestamp (ISO 8601)
- `items[]` - Array of items with random itemId, quantity, price
- `totalAmount` - Calculated from items
- `currency` - Random currency code (USD, EUR, etc.)
- `status` - Always "pending" for new orders

**Response (201 Created):**
```json
{
  "success": true,
  "message": "Order 'ORDER-001' created successfully",
  "data": {
    "orderId": "ORDER-001",
    "customerId": "CUST-1234",
    "orderDate": "2026-01-13T10:30:00Z",
    "items": [
      {
        "itemId": "ITEM-LAPTOP-123",
        "quantity": 2,
        "price": 999.99
      }
    ],
    "totalAmount": 1999.98,
    "currency": "USD",
    "status": "pending"
  }
}
```

### 2. PUT `/api/update-order`

Updates an existing order's status and publishes the update to Kafka.

**Request Body:**
```json
{
  "orderId": "ORDER-001",
  "status": "confirmed"
}
```

**Valid Statuses:**
- `pending`
- `confirmed`
- `shipped`
- `delivered`
- `cancelled`

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Order 'ORDER-001' updated successfully",
  "data": {
    "orderId": "ORDER-001",
    "status": "confirmed",
    ...
  }
}
```

### Health Endpoints

- `GET /` - Root endpoint with service info
- `GET /health` - Health check

## ✅ Validation Rules

### Order Level
- ✅ `orderId`: Non-empty string
- ✅ `customerId`: Non-empty string
- ✅ `orderDate`: Valid ISO 8601 format
- ✅ `items`: Array must not be empty
- ✅ `totalAmount`: Must be > 0 and equal sum of (price × quantity)
- ✅ `currency`: 3-letter code (USD, EUR, etc.)
- ✅ `status`: Valid enum value

### OrderItem Level
- ✅ `itemId`: Non-empty string
- ✅ `quantity`: Integer >= 1
- ✅ `price`: Must be > 0

## 🐳 Running with Docker Compose

### Prerequisites
- Docker Desktop installed
- Docker Compose installed

### Start All Services

```bash
# From the project root (Events_ex2/)
docker-compose up -d
```

This will start:
- **Zookeeper** (port 2181)
- **Kafka** (port 9092)
- **Schema Registry** (port 8081)
- **CartService** (port 8000)

### Check Service Status

```bash
docker-compose ps
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f cart-service
docker-compose logs -f kafka
docker-compose logs -f schema-registry
```

### Stop Services

```bash
docker-compose down
```

### Clean Everything (including volumes)

```bash
docker-compose down -v
```

## 🧪 Testing the API

### Using cURL

**Create Order:**
```bash
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORDER-001",
    "numItems": 3
  }'
```

**Update Order:**
```bash
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORDER-001",
    "status": "confirmed"
  }'
```

### Using Python

```python
import requests

# Create order
response = requests.post(
    "http://localhost:8000/api/create-order",
    json={"orderId": "ORDER-001", "numItems": 3}
)
print(response.json())

# Update order
response = requests.put(
    "http://localhost:8000/api/update-order",
    json={"orderId": "ORDER-001", "status": "confirmed"}
)
print(response.json())
```

### API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🔧 Local Development (Without Docker)

### 1. Install Dependencies

```bash
cd CartService
pip install -r requirements.txt
```

### 2. Start Kafka & Schema Registry

You'll need to run Kafka and Schema Registry separately:

```bash
# From project root
docker-compose up zookeeper kafka schema-registry -d
```

### 3. Run the Application

```bash
cd CartService
python main.py
```

The service will be available at http://localhost:8000

## 📊 Kafka Topics

- **Topic Name**: `order-events`
- **Key**: `orderId` (ensures ordering per order)
- **Value**: Order object serialized with Avro
- **Auto-created**: Yes

### View Messages (using kafka-console-consumer)

```bash
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic order-events \
  --from-beginning
```

## ⚠️ Error Handling

The API handles various error scenarios:

### Validation Errors (400)
- Empty or invalid fields
- Invalid currency format
- Items array is empty
- TotalAmount doesn't match item calculations

### Not Found (404)
- Order doesn't exist for update

### Service Unavailable (503)
- Kafka broker not available
- Schema Registry not available
- Connection timeout

### Internal Server Error (500)
- Unexpected errors

## 🎯 Architecture Highlights

### Layered Architecture
- **API Layer**: Request handling, validation, response formatting
- **Business Layer**: Business logic, orchestration
- **Service Layer**: External integrations (Kafka, Schema Registry)

### Key Design Decisions
1. **Avro + Schema Registry**: Ensures schema evolution and compatibility
2. **Idempotent Producer**: Prevents duplicate messages
3. **Ordered Messages**: Uses orderId as partition key
4. **In-memory Storage**: Simple tracking (can be replaced with DB)
5. **Rollback Support**: Reverts changes if Kafka publish fails

## 📝 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `SCHEMA_REGISTRY_URL` | `http://localhost:8081` | Schema Registry URL |
| `KAFKA_TOPIC` | `order-events` | Kafka topic name |
| `API_HOST` | `0.0.0.0` | API host |
| `API_PORT` | `8000` | API port |

## 🐛 Troubleshooting

### Kafka Connection Errors
```bash
# Check if Kafka is running
docker-compose ps kafka

# Check Kafka logs
docker-compose logs kafka

# Restart Kafka
docker-compose restart kafka
```

### Schema Registry Errors
```bash
# Check Schema Registry health
curl http://localhost:8081/

# View registered schemas
curl http://localhost:8081/subjects
```

### CartService Not Starting
```bash
# Check logs
docker-compose logs cart-service

# Rebuild image
docker-compose up --build cart-service
```

## 🎓 Bonus Features (Schema Registry)

This implementation uses **Avro with Schema Registry** for:
- ✅ Schema versioning and evolution
- ✅ Backward/forward compatibility
- ✅ Centralized schema management
- ✅ Efficient binary serialization

## 📄 License

This is a demonstration project for educational purposes.

