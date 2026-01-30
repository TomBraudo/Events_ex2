# Async Status Update Implementation

## Overview

This document describes the **asynchronous event-driven status update flow** that allows updating order statuses without synchronous calls between services.

## Architecture

```
┌─────────────┐                  ┌──────────────┐                  ┌──────────────┐
│   Client    │                  │  CartService │                  │   OrderService│
│             │                  │  (Producer)  │                  │  (Consumer)  │
└──────┬──────┘                  └──────┬───────┘                  └──────┬───────┘
       │                                │                                 │
       │  PUT /update-order             │                                 │
       │  {orderId, status}             │                                 │
       ├───────────────────────────────>│                                 │
       │                                │                                 │
       │                                │ Publish to                      │
       │                                │ order-status-updates            │
       │                                ├────────────────────────────────>│
       │                                │                                 │
       │  202 Accepted                  │                                 │
       │  (Event published)             │                                 │
       │<───────────────────────────────┤                                 │
       │                                │                                 │
       │                                │         Poll & Process          │
       │                                │         ┌──────────┐            │
       │                                │         │ Check if │            │
       │                                │         │  order   │            │
       │                                │         │ exists?  │            │
       │                                │         └────┬─────┘            │
       │                                │              │                  │
       │                                │         YES  │   NO             │
       │                                │         ┌────┴────┐             │
       │                                │         │         │             │
       │                                │    Update &    Send to          │
       │                                │     Save       DLQ              │
       │                                │         │         │             │
       │                                │    Commit   Commit              │
       │                                │    Offset   Offset              │
       │                                │                                 │
```

## Flow Details

### 1. Client Sends Update Request

```bash
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORD-123",
    "status": "shipped"
  }'
```

**Response: 202 Accepted**
```json
{
  "success": true,
  "message": "Status update event published for order 'ORD-123'. Processing asynchronously.",
  "data": {
    "orderId": "ORD-123",
    "status": "shipped",
    "message": "Status update event published. Processing asynchronously.",
    "eventType": "STATUS_UPDATE"
  }
}
```

### 2. CartService Publishes Event

**Topic:** `order-status-updates`

**Schema:** `status_update.avsc`
```json
{
  "orderId": "ORD-123",
  "status": "shipped",
  "updateTimestamp": "2026-01-30T12:00:00Z",
  "eventType": "STATUS_UPDATE"
}
```

**Key Points:**
- ✅ No synchronous call to OrderService
- ✅ Fast response (fire and forget)
- ✅ Loose coupling maintained
- ✅ Doesn't check if order exists (async validation)

### 3. OrderService Consumes Event

**Consumer:** `status_update_consumer_service`

**Processing Logic:**
```python
def process_status_update_event(status_update_data):
    order_id = status_update_data['orderId']
    new_status = status_update_data['status']
    
    # Check if order exists
    existing_order = storage.get_order(order_id)
    
    if not existing_order:
        # Order doesn't exist → raise exception → DLQ
        raise ValueError(f"Order {order_id} not found")
    
    # Update status
    existing_order['status'] = new_status
    storage.save_order(existing_order)
```

### 4. Two Possible Outcomes

#### ✅ Order Exists: Success

1. Order found in storage
2. Status updated
3. Order saved
4. Offset committed
5. **Result:** Order successfully updated

#### ❌ Order Not Found: DLQ

1. Order not found in storage
2. `ValueError` raised
3. Consumer retries 3 times (1s, 2s, 4s backoff)
4. Still fails after 3 retries
5. Event sent to DLQ
6. Offset committed
7. **Result:** Event in DLQ for investigation

## Topics

| Topic Name | Purpose | Schema | Consumers |
|------------|---------|--------|-----------|
| `order-events` | Full order creation events | `order.avsc` | OrderService |
| `order-status-updates` | Status update events | `status_update.avsc` | OrderService |
| `order-events-dlq` | Dead letter queue | `dlq.avsc` | Manual/monitoring |

## Schemas

### Status Update Schema (`status_update.avsc`)

```json
{
  "type": "record",
  "name": "OrderStatusUpdate",
  "namespace": "com.ecommerce.order",
  "fields": [
    {
      "name": "orderId",
      "type": "string",
      "doc": "Unique identifier for the order to update"
    },
    {
      "name": "status",
      "type": "string",
      "doc": "New status for the order"
    },
    {
      "name": "updateTimestamp",
      "type": "string",
      "doc": "Timestamp when update was requested (ISO 8601 format)"
    },
    {
      "name": "eventType",
      "type": "string",
      "default": "STATUS_UPDATE",
      "doc": "Type of event (STATUS_UPDATE)"
    }
  ]
}
```

## Error Handling & DLQ

### Reasons for DLQ in Status Updates

1. **Order doesn't exist** (most common)
   - User tries to update non-existent order
   - Order was deleted
   - Order ID typo

2. **Invalid status value**
   - Empty or null status
   - Whitespace-only status

3. **Storage errors**
   - Memory corruption
   - Thread safety issues (rare)

### Retry Behavior

**Configuration:**
- Max retries: 3
- Backoff: Exponential (1s, 2s, 4s)
- Total time: ~7 seconds before DLQ

**Example Timeline:**
```
Attempt 1 → Order not found → Fail → Wait 1s
Attempt 2 → Order not found → Fail → Wait 2s
Attempt 3 → Order not found → Fail → Wait 4s
Attempt 4 → Order not found → Fail → Send to DLQ
```

### Monitoring DLQ

Check failed status updates:
```bash
# View DLQ messages
curl http://localhost:8001/api/dlq/messages

# DLQ info
curl http://localhost:8001/api/dlq/info
```

## Trade-offs

### ✅ Advantages

1. **Async & Fast**
   - Client gets immediate response (202 Accepted)
   - No waiting for OrderService validation

2. **Loose Coupling**
   - CartService doesn't depend on OrderService API
   - Services can be deployed independently

3. **Scalable**
   - Status updates can be queued and processed in parallel
   - High throughput

4. **Resilient**
   - Retries handle transient failures
   - DLQ preserves failed updates for investigation

### ❌ Trade-offs

1. **Eventual Consistency**
   - Client doesn't know immediately if order exists
   - Status might not be updated instantly

2. **No Immediate Validation**
   - Client gets 202 even if order doesn't exist
   - Must check DLQ for failures

3. **Complexity**
   - Separate topic and schema
   - Additional consumer to maintain
   - DLQ monitoring required

## Configuration

### CartService (`docker-compose.yml`)

```yaml
environment:
  KAFKA_STATUS_UPDATE_TOPIC: order-status-updates
```

### OrderService (`docker-compose.yml`)

```yaml
environment:
  KAFKA_STATUS_UPDATE_TOPIC: order-status-updates
  DLQ_MAX_RETRIES: 3
  DLQ_RETRY_BACKOFF_MS: 1000
```

## Testing

### Test Case 1: Update Existing Order

```bash
# 1. Create order
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORD-TEST-001", "numItems": 2}'

# 2. Update status (should succeed)
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORD-TEST-001", "status": "shipped"}'

# 3. Verify update (wait 1-2 seconds for async processing)
curl "http://localhost:8001/api/order-details?orderId=ORD-TEST-001"
```

**Expected:** Status changed to "shipped"

### Test Case 2: Update Non-Existent Order (DLQ)

```bash
# Update order that doesn't exist
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "DOES-NOT-EXIST", "status": "shipped"}'

# Check DLQ (wait ~8 seconds for retries + DLQ)
curl http://localhost:8001/api/dlq/messages
```

**Expected:**
- 202 Accepted response
- After ~8 seconds, event appears in DLQ
- Error message: "Order DOES-NOT-EXIST not found"

### Test Case 3: Invalid Status

```bash
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "ORD-001", "status": "   "}'
```

**Expected:** 400 Bad Request (immediate validation)

## Comparison with Alternatives

### Alternative 1: Synchronous (Rejected)

```python
# CartService calls OrderService API
order = requests.get(f"http://orderservice:8001/api/order-details?orderId={order_id}")
if not order:
    raise HTTPException(404, "Order not found")

order['status'] = new_status
kafka_producer.publish(order)
```

**Problems:**
- ❌ Tight coupling
- ❌ Increased latency
- ❌ OrderService must be available
- ❌ Breaks event-driven principles

### Alternative 2: Move Endpoint to OrderService (Considered)

```python
# OrderService owns updates
OrderService.PUT /update-order → Check storage → Update → Publish
```

**Pros:**
- ✅ Immediate validation (has the data)
- ✅ Simpler architecture

**Cons:**
- ❌ OrderService handles both reads and writes
- ❌ Less clear separation of concerns

### Current Implementation: Async Events (Chosen)

**Best for:**
- Event-driven architecture
- High throughput
- Service independence
- Scalability

**Acceptable if:**
- Client can handle 202 Accepted
- Eventual consistency is okay
- DLQ monitoring is in place

## Summary

This async status update implementation provides:

1. **Event-Driven Architecture** - Pure async, no sync calls
2. **Non-Existent Order Handling** - Automatically sent to DLQ
3. **Retry Logic** - 3 retries with exponential backoff
4. **Loose Coupling** - Services remain independent
5. **Scalability** - High throughput status updates

**Flow:** Client → CartService (202) → Kafka → OrderService → Validate → Update or DLQ
