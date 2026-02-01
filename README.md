# Exercise 2 - Event-Driven E-Commerce System

## 1. Student Information
**Full Name:** Tom Braudo
**ID Number:** 324182914

**Full Name:** Dan Toledano
**ID Number:** 207254384

---

## 2. Topic Names

| Topic Name | Purpose |
|------------|---------|
| **order-events** | Main event topic containing all order events (ORDER_CREATED and STATUS_UPDATED) using Avro Union schema for type-safe event processing |
| **order-events-dlq** | Dead Letter Queue for failed messages after 3 retries with exponential backoff. Contains enriched metadata for debugging and reprocessing |

---

## 3. Message Key

**Key:** `orderId` (Order ID string)

**Why:**
- Kafka guarantees message ordering within a partition
- All events for the same order go to the same partition
- Ensures order creation is processed before status updates
- Prevents race conditions between concurrent updates to the same order

---

## 4. Error Handling

### Dead Letter Queue (DLQ)
- Failed messages sent to `order-events-dlq` after 3 retries
- Exponential backoff: 1s → 2s → 4s
- Enriched with error metadata, timestamps, original offset
- Monitoring via `/api/dlq/messages` endpoint

**Why:** Prevents data loss, allows investigation, doesn't block processing

### Manual Offset Management
- `enable.auto.commit: False`
- Offsets committed only after successful processing or DLQ placement
- Commit retries with exponential backoff

**Why:** At-least-once delivery, prevents silent message loss

### Producer Retries
- Application-level retries: 3 attempts with exponential backoff
- Reconnects on transient errors (network, broker unavailable)
- Returns 503 when Kafka unavailable

**Why:** Handles transient failures, proper HTTP error codes

### Business Validation
- **Duplicate detection:** Existing orderIds rejected → DLQ
- **Status validation:** Only valid enum values (pending, confirmed, shipped, delivered, cancelled)
- **Transition validation:** State machine prevents invalid transitions (e.g., delivered → pending)

**Why:** Data integrity, invalid events isolated in DLQ

### Schema Registry Resilience
- Local schema caching (`.event_schema_cache`)
- Fallback to cache if Schema Registry unavailable

**Why:** Service starts even during Schema Registry maintenance

### Consumer Error Tracking
- Tracks consecutive poll errors
- Stops after 10 consecutive errors

**Why:** Prevents infinite loops, enables health checks

---

## API Endpoints

### CartService (Producer) - Port 8000
- **POST** `/api/create-order` - Create new order
- **PUT** `/api/update-order` - Update order status

### OrderService (Consumer) - Port 8001
- **GET** `/api/order-details?orderId=X` - Get order with shipping cost
- **GET** `/api/getAllOrderIdsFromTopic?topicName=X` - Get all orderIds from topic
- **GET** `/api/dlq/messages` - View DLQ messages
- **GET** `/api/dlq/info` - DLQ configuration

---

## Architecture Highlights

- **Avro Union Schema** with Schema Registry (10 bonus points)
- **Single topic** (`order-events`) for scalability
- **Event envelope** with `eventType` field routes to appropriate handlers
- **At-least-once delivery** with manual offset management
- **Comprehensive error handling** at all layers

---

## Running the System

```bash
docker-compose up -d
```

Services:
- CartService: http://localhost:8000
- OrderService: http://localhost:8001
- Kafka: localhost:9092
- Schema Registry: localhost:8081

---

## Testing

```bash
# Create order
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORD-001", "numItems": 2}'

# Update status
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORD-001", "status": "shipped"}'

# Get order details
curl "http://localhost:8001/api/order-details?orderId=ORD-001"

# Get all orders from topic
curl "http://localhost:8001/api/getAllOrderIdsFromTopic?topicName=order-events"

# Check DLQ
curl http://localhost:8001/api/dlq/messages
```
