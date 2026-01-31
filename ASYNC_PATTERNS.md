# Async Event-Driven Patterns

## Overview

Both order creation and status updates follow the **same async event-driven pattern**:
1. Producer accepts request (201/202)
2. Publishes event to Kafka
3. Consumer validates asynchronously
4. Success → Save | Failure → Retry → DLQ

## Pattern Comparison

| Aspect | Order Creation | Status Update |
|--------|----------------|---------------|
| **Endpoint** | `POST /create-order` | `PUT /update-order` |
| **Producer** | CartService | CartService |
| **Response** | 201 Created | 202 Accepted |
| **Topic** | `order-events` | `order-status-updates` |
| **Consumer** | OrderService | OrderService |
| **Success Case** | Order doesn't exist → Create | Order exists → Update |
| **Failure Case** | **Duplicate ID** → DLQ | **Order not found** → DLQ |

## Side-by-Side Flow

### Order Creation Flow

```
Client sends:
  POST /create-order
  {"orderId": "ORD-123", "numItems": 2}

CartService:
  ✅ Validates input (not empty, numItems 1-100)
  ✅ Generates full order
  ✅ Publishes to order-events topic
  ← Returns 201 Created immediately

OrderService Consumer:
  Receives event from order-events
  ↓
  Check: Does order ID already exist?
  ├─ NO → Process, calculate shipping, save ✅
  └─ YES → ValueError("Duplicate order ID")
            ↓
            Retry 3 times (1s, 2s, 4s)
            ↓
            Still duplicate → DLQ 📮
```

### Status Update Flow

```
Client sends:
  PUT /update-order
  {"orderId": "ORD-123", "status": "shipped"}

CartService:
  ✅ Validates input (not empty)
  ✅ Creates status update event
  ✅ Publishes to order-status-updates topic
  ← Returns 202 Accepted immediately

OrderService Consumer:
  Receives event from order-status-updates
  ↓
  Check: Does order exist in storage?
  ├─ YES → Update status, save ✅
  └─ NO → ValueError("Order not found")
           ↓
           Retry 3 times (1s, 2s, 4s)
           ↓
           Still not found → DLQ 📮
```

## Key Insight: Inverse Validation

**Order Creation:**
- ✅ Success when: Order ID is **new** (doesn't exist)
- ❌ Failure when: Order ID is **duplicate** (already exists)

**Status Update:**
- ✅ Success when: Order ID **exists** (can update)
- ❌ Failure when: Order ID **doesn't exist** (can't update)

**Both follow the same DLQ pattern for their respective failure cases!**

## DLQ Messages

### Duplicate Order in DLQ

```json
{
  "originalMessage": "{\"orderId\":\"ORD-123\",\"customerId\":\"CUST-001\",...}",
  "errorMessage": "Duplicate order ID: ORD-123 already exists. Cannot create duplicate order.",
  "errorType": "ValueError",
  "retryCount": 3,
  "failedAttempts": 4,
  "firstFailureTimestamp": "2026-01-30T12:00:00Z",
  "lastFailureTimestamp": "2026-01-30T12:00:07Z",
  "originalTopic": "order-events",
  "originalPartition": 0,
  "originalOffset": 456,
  "consumerGroup": "order-service-group"
}
```

### Non-Existent Order in DLQ

```json
{
  "originalMessage": "{\"orderId\":\"ORD-999\",\"status\":\"shipped\",...}",
  "errorMessage": "Order ORD-999 not found. Cannot update status. Sending to DLQ.",
  "errorType": "ValueError",
  "retryCount": 3,
  "failedAttempts": 4,
  "firstFailureTimestamp": "2026-01-30T12:00:00Z",
  "lastFailureTimestamp": "2026-01-30T12:00:07Z",
  "originalTopic": "order-status-updates",
  "originalPartition": 0,
  "originalOffset": 789,
  "consumerGroup": "order-service-group-status-updates"
}
```

## Testing Scenarios

### Test 1: Normal Order Creation

```bash
# Create order (succeeds)
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORD-001", "numItems": 2}'
```

**Result:** ✅ 201 Created → Order processed and stored

### Test 2: Duplicate Order Creation → DLQ

```bash
# First order (succeeds)
curl -X POST http://localhost:8000/api/create-order \
  -d '{"orderId": "DUP-001", "numItems": 2}'

# Duplicate order (goes to DLQ)
curl -X POST http://localhost:8000/api/create-order \
  -d '{"orderId": "DUP-001", "numItems": 3}'
```

**Result:** 
- First: ✅ 201 Created → Processed
- Second: ✅ 201 Created → Consumer detects duplicate → DLQ (~7 seconds)

### Test 3: Normal Status Update

```bash
# Create order first
curl -X POST http://localhost:8000/api/create-order \
  -d '{"orderId": "ORD-002", "numItems": 2}'

# Update status (succeeds)
curl -X PUT http://localhost:8000/api/update-order \
  -d '{"orderId": "ORD-002", "status": "shipped"}'
```

**Result:** ✅ 202 Accepted → Status updated

### Test 4: Update Non-Existent Order → DLQ

```bash
# Try to update order that doesn't exist
curl -X PUT http://localhost:8000/api/update-order \
  -d '{"orderId": "NEVER-EXISTED", "status": "shipped"}'
```

**Result:** ✅ 202 Accepted → Consumer detects not found → DLQ (~7 seconds)

### Test 5: Check DLQ

```bash
# Wait ~8 seconds after failures, then check
curl http://localhost:8001/api/dlq/messages
```

## Why This Pattern?

### Benefits

1. **Consistent Architecture**
   - Same pattern for create and update
   - Easy to understand and maintain

2. **Producer Independence**
   - CartService never calls OrderService API
   - No synchronous dependencies
   - Fast responses (201/202)

3. **Async Validation**
   - Duplicates detected at consumer
   - Non-existent orders detected at consumer
   - Same retry + DLQ mechanism

4. **Data Integrity**
   - Duplicates don't silently overwrite
   - Invalid updates don't corrupt data
   - All failures preserved in DLQ

5. **Eventual Consistency**
   - Acceptable trade-off for decoupled services
   - DLQ provides audit trail

### Trade-offs

1. **No Immediate Validation**
   - Client doesn't know immediately if order is duplicate
   - Client doesn't know immediately if order exists for update
   - Must check DLQ for failures

2. **Eventual Consistency**
   - Small delay (~ms to seconds) between publish and process
   - Cannot synchronously confirm success/failure

3. **DLQ Monitoring Required**
   - Must monitor DLQ for failures
   - Need process to handle DLQ messages

## Configuration

Both flows use the same DLQ configuration:

```yaml
# docker-compose.yml
environment:
  KAFKA_DLQ_TOPIC: order-events-dlq
  DLQ_MAX_RETRIES: 3
  DLQ_RETRY_BACKOFF_MS: 1000
  DLQ_MAX_BACKOFF_MS: 30000
```

**Retry Timeline (both flows):**
- Attempt 1 → Fail → Wait 1s
- Attempt 2 → Fail → Wait 2s
- Attempt 3 → Fail → Wait 4s
- Attempt 4 → Fail → DLQ
- **Total: ~7 seconds from publish to DLQ**

## Exception Types Leading to DLQ

### From Order Creation (`order-events` topic)

1. **Duplicate Order ID** (new!)
   - `ValueError: Duplicate order ID: X already exists`
   
2. **Pydantic Validation Errors**
   - Missing fields, wrong types, invalid items

3. **TEST-FAIL Simulation**
   - `ValueError: Simulated processing failure`

4. **Storage Validation**
   - Empty orderId, type errors

### From Status Updates (`order-status-updates` topic)

1. **Order Not Found** (main case)
   - `ValueError: Order X not found`

2. **Invalid Status**
   - Empty or whitespace-only status

## Monitoring Both Flows

### Check All DLQ Messages

```bash
curl http://localhost:8001/api/dlq/messages
```

Returns messages from **both** topics:
- `originalTopic: "order-events"` - Failed order creations
- `originalTopic: "order-status-updates"` - Failed status updates

### Filter by Error Type

```bash
# Duplicates
curl http://localhost:8001/api/dlq/messages | jq '.messages[] | select(.errorMessage | contains("Duplicate"))'

# Not found
curl http://localhost:8001/api/dlq/messages | jq '.messages[] | select(.errorMessage | contains("not found"))'
```

## Summary

**Both flows are truly async event-driven:**

| | Order Creation | Status Update |
|---|---|---|
| **Producer validates** | Input format | Input format |
| **Producer checks** | Nothing | Nothing |
| **Producer returns** | 201 immediately | 202 immediately |
| **Consumer validates** | Not duplicate | Exists |
| **On validation failure** | Retry → DLQ | Retry → DLQ |
| **Same DLQ topic** | ✅ Yes | ✅ Yes |
| **Same retry logic** | ✅ Yes | ✅ Yes |
| **Same infrastructure** | ✅ Yes | ✅ Yes |

**Perfect symmetry: Both flows follow identical patterns with inverse business logic!**
