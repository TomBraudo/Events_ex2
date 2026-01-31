# Error Handling & Resilience Mechanisms

This document summarizes the error handling and resilience patterns implemented across the microservices architecture.

---

## 1. Dead Letter Queue (DLQ)

**Location:** `OrderService/service/kafka/dlq_producer.py`

**Purpose:** Capture and preserve messages that fail processing after all retry attempts.

**Implementation:**
- Failed messages sent to dedicated `order-events-dlq` topic
- Enriched with failure metadata (error type, retry count, timestamps, original offset)
- DLQ sends include retry logic to prevent message loss
- Monitoring API available at `GET /api/dlq/info` and `GET /api/dlq/messages`

**Configuration:**
```env
KAFKA_DLQ_TOPIC=order-events-dlq
DLQ_MAX_RETRIES=3
DLQ_RETRY_BACKOFF_MS=1000
DLQ_MAX_BACKOFF_MS=30000
```

**Key Feature:** Messages are committed to DLQ even if critical failure occurs to avoid infinite retry loops.

---

## 2. Message Processing Retry (Exponential Backoff)

**Location:** `OrderService/service/kafka/consumer.py` → `_process_message_with_retry()`

**Purpose:** Retry failed message processing with increasing delays before resorting to DLQ.

**Implementation:**
- Retries same message up to `DLQ_MAX_RETRIES` (default: 3)
- Exponential backoff: `min(1000ms * 2^attempt, 30000ms)`
- Tracks first failure timestamp across retries
- Only commits offset after successful processing or DLQ placement

**Retry Sequence:**
```
Attempt 0 → Process → Fail → Wait 1s
Attempt 1 → Process → Fail → Wait 2s  
Attempt 2 → Process → Fail → Wait 4s
Attempt 3 → Process → Fail → Send to DLQ → Commit
```

---

## 3. Manual Offset Management

**Location:** `OrderService/service/kafka/consumer.py`

**Purpose:** Prevent message loss by controlling exactly when offsets are committed.

**Implementation:**
- `enable.auto.commit: False` in consumer config
- Offsets committed only after:
  - ✅ Successful message processing, OR
  - ✅ Successful DLQ placement (after max retries)
- Uses `_commit_offset_with_retry()` with its own retry logic

**Key Benefit:** Failed messages are reprocessed on consumer restart, not silently dropped.

---

## 4. Consumer Commit Retries

**Location:** `OrderService/service/kafka/consumer.py` → `_commit_offset_with_retry()`

**Purpose:** Ensure offsets are committed even during transient Kafka issues.

**Implementation:**
- Retries offset commits up to `CONSUMER_COMMIT_MAX_RETRIES` (default: 3)
- Exponential backoff: `500ms * 2^attempt`
- Synchronous commits (`asynchronous=False`) for guaranteed completion
- Critical logging if all commit attempts fail

**Configuration:**
```env
CONSUMER_COMMIT_MAX_RETRIES=3
CONSUMER_COMMIT_RETRY_BACKOFF_MS=500
```

---

## 5. Producer Publish Retries

**Location:** `CartService/service/kafka/producer.py` → `publish_order_event()`

**Purpose:** Handle transient network/Kafka failures when publishing events.

**Implementation:**
- Application-level retries (beyond Kafka client retries)
- Retry count: `PRODUCER_MAX_RETRIES` (default: 3)
- Exponential backoff: `1000ms * 2^attempt`
- Reconnects producer on transient errors
- Configurable flush timeout

**Configuration:**
```env
PRODUCER_MAX_RETRIES=3
PRODUCER_RETRY_BACKOFF_MS=1000
PRODUCER_FLUSH_TIMEOUT_SECONDS=10
```

**Error Types:**
- **Transient** (retry): Network errors, broker not available, timeouts
- **Non-transient** (fail fast): Schema errors, connection refused, generic errors after retries

---

## 6. DLQ Producer Retries

**Location:** `OrderService/service/kafka/dlq_producer.py` → `send_to_dlq()`

**Purpose:** Prevent data loss by retrying DLQ sends themselves.

**Implementation:**
- Retries DLQ sends up to `DLQ_PRODUCER_MAX_RETRIES` (default: 3)
- Exponential backoff: `1000ms * 2^attempt`
- Reconnects DLQ producer between retry attempts
- Critical logging if DLQ send ultimately fails

**Configuration:**
```env
DLQ_PRODUCER_MAX_RETRIES=3
DLQ_PRODUCER_RETRY_BACKOFF_MS=1000
DLQ_FLUSH_TIMEOUT_SECONDS=10
```

**Fallback:** Even if DLQ send critically fails, offset is still committed to prevent infinite loop.

---

## 7. Consumer Poll Error Tracking

**Location:** `OrderService/service/kafka/consumer.py` → `_consume_loop()`

**Purpose:** Detect and prevent degradation from persistent Kafka connectivity issues.

**Implementation:**
- Tracks consecutive poll errors
- Stops consumer after `CONSUMER_MAX_CONSECUTIVE_ERRORS` (default: 10)
- Resets counter on successful poll (even if no message)
- Critical logging triggers consumer shutdown

**Configuration:**
```env
CONSUMER_MAX_CONSECUTIVE_ERRORS=10
```

**Why:** Prevents infinite error loops and resource exhaustion when Kafka persistently unavailable.

---

## 8. Schema Caching

**Location:** All Kafka services (`producer.py`, `consumer.py`, `dlq_producer.py`)

**Purpose:** Allow services to start/run even when Schema Registry temporarily unavailable.

**Implementation:**
- Caches Avro schema to local files on successful load:
  - `.schema_cache` (producer/consumer)
  - `.dlq_schema_cache` (DLQ producer)
- Falls back to cached schema if Schema Registry unreachable
- Cache automatically updated on each successful schema load

**Files:**
- `CartService/schemas/.schema_cache`
- `OrderService/schemas/.schema_cache`
- `OrderService/schemas/.dlq_schema_cache`

**Benefit:** Service resilience during Schema Registry maintenance/outages.

---

## 9. Thread-Safe DLQ Initialization

**Location:** `OrderService/service/kafka/consumer.py` → `_get_dlq_producer()`

**Purpose:** Prevent race conditions when initializing DLQ producer.

**Implementation:**
- Uses `threading.Lock()` for synchronization
- Double-checked locking pattern
- Lazy initialization (only creates DLQ producer when first needed)

```python
def _get_dlq_producer(self):
    if self.dlq_producer is None:
        with self._dlq_lock:  # Thread-safe
            if self.dlq_producer is None:
                from .dlq_producer import dlq_producer
                self.dlq_producer = dlq_producer
                self.dlq_producer.connect()
    return self.dlq_producer
```

---

## 10. Input Validation

**Locations:**
- `OrderService/utils/order_storage.py` → `save_order()`
- `CartService/utils/order_generator.py` → `generate_order()`

**Purpose:** Defensive programming to catch invalid data early.

**Implementation:**

### Order Storage Validation
```python
# Type check
if not isinstance(order_with_shipping, dict):
    raise TypeError(...)

# Field validation
if not order_id or not order_id.strip():
    raise ValueError("orderId must be non-empty string")
```

### Order Generator Validation
```python
# Type checks
if not isinstance(order_id, str):
    raise TypeError(...)
if not isinstance(num_items, int):
    raise TypeError(...)

# Range validation
if num_items < 1 or num_items > 100:
    raise ValueError(...)
```

---

## 11. Duplicate Order Detection

**Location:** `OrderService/business/order/order_processor.py`

**Purpose:** Prevent duplicate orders from overwriting existing data.

**Implementation:**
- Check if orderId already exists in storage before processing
- Raise ValueError if duplicate detected
- Propagate to DLQ after retry attempts

**Code:**
```python
def process_order_event(self, order_data):
    order_id = order_data.get('orderId')
    
    # Check for duplicate
    if self.storage.order_exists(order_id):
        raise ValueError(f"Duplicate order ID: {order_id} already exists")
    
    # Continue processing...
```

**Flow:**
1. First order with ID "ORD-001" → Processed & stored ✅
2. Second order with ID "ORD-001" → Duplicate detected → Retry → DLQ 📮

**Why DLQ instead of silent overwrite:**
- Preserves data integrity
- Alerts to potential bugs or user errors
- Allows investigation of duplicate submissions
- Follows same pattern as status updates for non-existent orders

## 12. Exception Propagation

**Location:** `OrderService/business/order/order_processor.py`

**Purpose:** Ensure processing exceptions reach consumer retry logic.

**Implementation:**
- Removed outer `try-except` that was swallowing exceptions
- Re-raises validation errors with `raise` keyword
- Allows consumer's `_process_message_with_retry()` to handle failures

**Before (incorrect):**
```python
try:
    process()
except Exception as e:
    logger.error(e)  # Silent failure - offset still committed
```

**After (correct):**
```python
try:
    process()
except Exception as e:
    logger.error(e)
    raise  # Propagate to consumer for retry/DLQ
```

---

## Testing DLQ

### Test 1: Simulated Failure (TEST-FAIL)

Use the special `TEST-FAIL` order ID prefix:

```bash
# This will intentionally fail processing and land in DLQ
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "TEST-FAIL-001", "numItems": 2}'
```

**Expected Flow:**
1. CartService publishes event successfully (201 response)
2. OrderService consumer receives message
3. Processes → Fails (simulated error)
4. Retry 1 → Fails (wait 1s)
5. Retry 2 → Fails (wait 2s)
6. Retry 3 → Fails (wait 4s)
7. Sent to DLQ topic
8. Offset committed
9. Consumer continues with next message

### Test 2: Duplicate Order ID

Create the same order twice:

```bash
# Create order first time (succeeds)
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "DUP-001", "numItems": 2}'

# Create same order again (duplicate - goes to DLQ)
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "DUP-001", "numItems": 3}'
```

**Expected Flow:**
1. First request: 201 Created → Processes successfully
2. Second request: 201 Created (CartService doesn't check duplicates)
3. OrderService detects duplicate → Fails
4. Retries 3 times → Still fails (still duplicate)
5. Sent to DLQ with error: "Duplicate order ID: DUP-001 already exists"

### Test 3: Non-Existent Order Status Update

Try to update an order that doesn't exist:

```bash
# Update order that was never created
curl -X PUT http://localhost:8000/api/update-order \
  -H "Content-Type: application/json" \
  -d '{"orderId": "NEVER-CREATED", "status": "shipped"}'
```

**Expected Flow:**
1. Returns 202 Accepted (async processing)
2. OrderService processes → Order not found
3. Retries 3 times → Still not found
4. Sent to DLQ with error: "Order NEVER-CREATED not found"

Check DLQ contents:
```bash
curl http://localhost:8001/api/dlq/messages
```

---

## Configuration Summary

### Application-Level Retry Configuration
All error handling is configurable via environment variables in `docker-compose.yml`:

```yaml
# Message Processing
DLQ_MAX_RETRIES=3
DLQ_RETRY_BACKOFF_MS=1000
DLQ_MAX_BACKOFF_MS=30000

# Producer Retries
PRODUCER_MAX_RETRIES=3
PRODUCER_RETRY_BACKOFF_MS=1000
PRODUCER_FLUSH_TIMEOUT_SECONDS=10

# DLQ Producer Retries
DLQ_PRODUCER_MAX_RETRIES=3
DLQ_PRODUCER_RETRY_BACKOFF_MS=1000
DLQ_FLUSH_TIMEOUT_SECONDS=10

# Consumer Reliability
CONSUMER_COMMIT_MAX_RETRIES=3
CONSUMER_COMMIT_RETRY_BACKOFF_MS=500
CONSUMER_MAX_CONSECUTIVE_ERRORS=10
```

### Kafka Client-Level Configuration

**CartService Producer** (`CartService/config/settings.py`):
```python
KAFKA_PRODUCER_CONFIG = {
    'acks': 'all',                               # Wait for all replicas
    'retries': 3,                                # Kafka client-level retries
    'max.in.flight.requests.per.connection': 1,  # Ensure message ordering
    'enable.idempotence': True,                  # Prevent duplicates
}
```

**OrderService DLQ Producer** (`OrderService/config/settings.py`):
```python
KAFKA_PRODUCER_CONFIG = {
    'acks': 'all',                               # Wait for all replicas
    'retries': 3,                                # Kafka client-level retries
    'max.in.flight.requests.per.connection': 1,  # Ensure message ordering
    'enable.idempotence': True,                  # Prevent duplicate DLQ messages
    'compression.type': 'gzip',                  # Compress DLQ payloads
}
```

**Library Defaults** (when not explicitly set):
- `retry.backoff.ms`: `100` ms
- `request.timeout.ms`: `30000` ms (30 seconds)
- `delivery.timeout.ms`: `120000` ms (2 minutes)

---

## Architecture Decisions

### ✅ CartService: Pure Event Producer
- **No local storage** - publishes events only
- Allows duplicate events (event sourcing pattern)
- Status updates not supported (retrieve from OrderService instead)

### ✅ OrderService: Event Consumer + State Keeper
- Maintains order state in-memory
- Processes events with retry logic
- Sends failed messages to DLQ
- Manual offset management for reliability

### ✅ Event-Driven Success Semantics
- Producer success = "Event published to Kafka"
- Consumer success = "Event processed and persisted"
- Failures are handled asynchronously via DLQ

---

## Monitoring

### DLQ Information
```bash
GET http://localhost:8001/api/dlq/info
```

Returns configuration and consumer stats.

### DLQ Messages
```bash
GET http://localhost:8001/api/dlq/messages
```

Reads latest messages from DLQ topic for inspection.

---

## Not Yet Implemented

The following patterns were considered but not implemented (see explanations in conversation):

1. **Circuit Breaker** - Requires metrics/monitoring infrastructure
2. **Real Health Checks** - Best added during K8s deployment
3. **Distributed Tracing** - Requires observability stack (Jaeger/Zipkin)
4. **Rate Limiting** - Not needed for current scale

These can be added as the system scales to production.
