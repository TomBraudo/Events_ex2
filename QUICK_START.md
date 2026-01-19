# 🚀 Quick Start Guide

## Start the System

```bash
# From project root
docker-compose up -d
```

Wait 30-60 seconds for all services to initialize.

## Test the Complete Flow

### 1. Create an Order (Producer)

```bash
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORDER-001", "numItems": 3}'
```

### 2. Get Order Details with Shipping (Consumer)

```bash
# Wait 2-3 seconds for consumer to process
curl "http://localhost:8001/api/order-details?orderId=ORDER-001"
```

You'll see the order with calculated `shippingCost` (2% of totalAmount)!

### 3. Update Order Status (Producer)

```bash
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORDER-001", "status": "confirmed"}'
```

### 4. Get All Order IDs from Topic (Consumer)

```bash
curl "http://localhost:8001/api/getAllOrderIdsFromTopic?topicName=order-events"
```

## Access Points

### APIs
- **CartService (Producer)**: http://localhost:8000
  - Swagger: http://localhost:8000/docs
- **OrderService (Consumer)**: http://localhost:8001
  - Swagger: http://localhost:8001/docs

### Infrastructure
- **Kafka**: localhost:9092
- **Schema Registry**: http://localhost:8081

## View Logs

```bash
# Producer logs
docker-compose logs -f cart-service

# Consumer logs
docker-compose logs -f order-service

# All logs
docker-compose logs -f
```

## Check Consumer Status

```bash
curl http://localhost:8001/health
```

Should show: `"consumer_running": true`

## Stop Everything

```bash
docker-compose down
```

## Clean Everything (including data)

```bash
docker-compose down -v
```

## Valid Order Statuses

- `pending` (default for new orders)
- `confirmed`
- `shipped`
- `delivered`
- `cancelled`

