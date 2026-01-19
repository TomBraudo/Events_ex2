# OrderService - E-Commerce Order Consumer

A consumer microservice that listens to Kafka order events, processes them, calculates shipping costs, and provides APIs to retrieve order details.

## 🚀 Features

- ✅ **Kafka Consumer** with Avro deserialization
- ✅ **Background Event Processing** (threaded consumer)
- ✅ **Schema Registry Integration** for type-safe deserialization
- ✅ **Automatic Shipping Cost Calculation** (2% of totalAmount)
- ✅ **RESTful API** for order retrieval
- ✅ **In-Memory Storage** for processed orders
- ✅ **Layered Architecture** (API, Business, Service)

## 📁 Project Structure

```
OrderService/
├── api/
│   └── controllers/
│       ├── __init__.py
│       └── order_controller.py       # API endpoints
├── business/
│   └── order/
│       ├── __init__.py
│       └── order_processor.py        # Business logic
├── service/
│   └── kafka/
│       ├── __init__.py
│       └── consumer.py               # Kafka consumer with Avro
├── models/
│   ├── __init__.py
│   └── order.py                      # Pydantic models
├── utils/
│   ├── __init__.py
│   └── order_storage.py              # In-memory storage
├── config/
│   ├── __init__.py
│   └── settings.py                   # Configuration
├── schemas/
│   └── order.avsc                    # Avro schema (matches producer)
├── main.py                           # FastAPI application
├── requirements.txt
└── Dockerfile
```

## 🔄 How It Works

### Event Flow

```
┌──────────────────┐
│  Kafka Topic     │
│  "order-events"  │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────┐
│  Kafka Consumer          │
│  (Background Thread)     │
│  - Avro Deserialization  │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  Order Processor         │
│  - Calculate Shipping    │
│    (2% of totalAmount)   │
│  - Validate Order        │
│  - Store in Memory       │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│  In-Memory Storage       │
│  (Orders + Shipping)     │
└──────────────────────────┘
```

### Processing Logic

When an order event is received:
1. **Deserialize** from Avro using Schema Registry
2. **Validate** order data with Pydantic models
3. **Calculate** shipping cost: `shippingCost = totalAmount * 0.02` (2%)
4. **Store** order with shipping cost in memory
5. **Log** the processed order

## 📋 API Endpoints

### 1. GET `/api/order-details`

Retrieve a processed order with shipping cost.

**Query Parameters:**
- `orderId` (required) - The order ID to retrieve

**Example Request:**
```bash
curl "http://localhost:8001/api/order-details?orderId=ORDER-001"
```

**Example Response (200 OK):**
```json
{
  "success": true,
  "message": "Order 'ORDER-001' retrieved successfully",
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
    "status": "pending",
    "shippingCost": 39.99
  }
}
```

**Error Responses:**
- `400` - Missing or empty orderId
- `404` - Order not found
- `500` - Internal server error

### 2. GET `/api/getAllOrderIdsFromTopic`

Read all order IDs from a specific Kafka topic.

**Query Parameters:**
- `topicName` (required) - The Kafka topic name to read from

**Example Request:**
```bash
curl "http://localhost:8001/api/getAllOrderIdsFromTopic?topicName=order-events"
```

**Example Response (200 OK):**
```json
{
  "success": true,
  "message": "Successfully retrieved order IDs from topic 'order-events'",
  "topicName": "order-events",
  "orderIds": [
    "ORDER-001",
    "ORDER-002",
    "ORDER-003"
  ],
  "count": 3
}
```

**Error Responses:**
- `400` - Missing or empty topicName
- `503` - Kafka broker or Schema Registry not available
- `500` - Internal server error

### 3. GET `/api/stats`

Get statistics about processed orders.

**Example Request:**
```bash
curl "http://localhost:8001/api/stats"
```

**Example Response:**
```json
{
  "success": true,
  "totalOrders": 5,
  "orderIds": ["ORDER-001", "ORDER-002", "ORDER-003", "ORDER-004", "ORDER-005"]
}
```

### Health Endpoints

- `GET /` - Root endpoint with service info
- `GET /health` - Health check

## 🐳 Running with Docker Compose

### Start All Services

```bash
# From project root (Events_ex2/)
docker-compose up -d
```

This starts:
- Zookeeper
- Kafka
- Schema Registry
- CartService (Producer) - Port 8000
- OrderService (Consumer) - Port 8001

### Check Logs

```bash
# View OrderService logs
docker-compose logs -f order-service

# View all logs
docker-compose logs -f
```

### Verify Consumer is Running

```bash
curl http://localhost:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "OrderService",
  "consumer_running": true
}
```

## 🧪 Testing the Consumer

### Step 1: Create an Order (Producer)

```bash
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORDER-001",
    "numItems": 3
  }'
```

### Step 2: Verify Consumer Processed It

Check logs:
```bash
docker-compose logs order-service | grep "ORDER-001"
```

You should see:
```
Received order event: ORDER-001, status: pending
Calculated shipping cost for ORDER-001: 39.99 (2% of 1999.98)
Order processed and stored: ORDER-001, status: pending, totalAmount: 1999.98, shippingCost: 39.99
```

### Step 3: Retrieve Order Details

```bash
curl "http://localhost:8001/api/order-details?orderId=ORDER-001"
```

### Step 4: Get All Order IDs from Topic

```bash
curl "http://localhost:8001/api/getAllOrderIdsFromTopic?topicName=order-events"
```

## 🔧 Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `SCHEMA_REGISTRY_URL` | `http://localhost:8081` | Schema Registry URL |
| `KAFKA_TOPIC` | `order-events` | Topic to consume from |
| `KAFKA_CONSUMER_GROUP` | `order-service-group` | Consumer group ID |
| `API_HOST` | `0.0.0.0` | API host |
| `API_PORT` | `8001` | API port |

## 📊 Business Logic

### Shipping Cost Calculation

```python
shippingCost = totalAmount * 0.02  # 2% of order total
```

**Example:**
- Order total: $1999.98
- Shipping cost: $39.99 (2%)

### Order Processing

1. Receives order event from Kafka
2. Deserializes using Avro + Schema Registry
3. Validates with Pydantic models
4. Calculates shipping cost
5. Stores order with shipping cost
6. Logs processing details

## 🎯 Architecture Highlights

### Layered Architecture

- **API Layer**: HTTP endpoints, request/response handling
- **Business Layer**: Order processing, shipping calculation
- **Service Layer**: Kafka consumer, Avro deserialization

### Key Features

1. **Background Consumer**: Runs in separate thread
2. **Avro + Schema Registry**: Type-safe deserialization
3. **Message Ordering**: Kafka partitioning ensures order
4. **Thread-Safe Storage**: Lock-protected in-memory storage
5. **Error Handling**: Comprehensive error handling and logging

### Consumer Configuration

- **Group ID**: `order-service-group`
- **Auto Offset Reset**: `earliest` (reads all messages from beginning)
- **Auto Commit**: Enabled
- **Max Poll Interval**: 300 seconds

## 🐛 Troubleshooting

### Consumer Not Receiving Messages

```bash
# Check if consumer is running
curl http://localhost:8001/health

# Check consumer logs
docker-compose logs order-service

# Restart consumer
docker-compose restart order-service
```

### Kafka Connection Errors

```bash
# Check Kafka is running
docker-compose ps kafka

# Check Kafka logs
docker-compose logs kafka

# Restart Kafka stack
docker-compose restart zookeeper kafka schema-registry
```

### No Orders in Storage

```bash
# Check stats endpoint
curl http://localhost:8001/api/stats

# Verify orders exist in Kafka topic
docker exec -it kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic order-events \
  --from-beginning
```

## 📖 API Documentation

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## 🔗 Related Services

- **CartService (Producer)**: http://localhost:8000
- **Kafka Broker**: localhost:9092
- **Schema Registry**: http://localhost:8081

## 📝 Example Usage Flow

```bash
# 1. Create order (Producer)
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORDER-001", "numItems": 2}'

# 2. Wait a moment for consumer to process...

# 3. Get order details with shipping cost (Consumer)
curl "http://localhost:8001/api/order-details?orderId=ORDER-001"

# 4. Update order status (Producer)
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORDER-001", "status": "confirmed"}'

# 5. Get updated order details (Consumer)
curl "http://localhost:8001/api/order-details?orderId=ORDER-001"

# 6. Get all order IDs from topic
curl "http://localhost:8001/api/getAllOrderIdsFromTopic?topicName=order-events"
```

## 📄 License

This is a demonstration project for educational purposes.

