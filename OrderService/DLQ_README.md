# Dead Letter Queue (DLQ) Implementation

## 📋 Overview

This OrderService implements a robust **Dead Letter Queue (DLQ)** pattern to handle message processing failures gracefully. When a message cannot be processed successfully after multiple retry attempts, it is sent to a DLQ topic for later analysis and reprocessing.

## 🎯 Why DLQ is Critical

### Problem Without DLQ
Without a DLQ, failed messages are either:
- **Lost forever** (if auto-commit is enabled)
- **Block the consumer** (if processing keeps failing)
- **Cause infinite retry loops** (wasting resources)

### Solution With DLQ
Our DLQ implementation ensures:
- ✅ **No data loss** - Failed messages are preserved
- ✅ **Automatic retries** - Exponential backoff before DLQ
- ✅ **Manual offset control** - Only commit after success
- ✅ **Full traceability** - Rich metadata for debugging
- ✅ **System resilience** - Failures don't block processing

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kafka Consumer Loop                       │
│                                                              │
│  1. Poll Message ──┐                                        │
│                    │                                         │
│  2. Process ───────┼──► Success? ──► Commit Offset          │
│                    │         │                               │
│                    │         └─► No                          │
│                    │              │                          │
│  3. Retry Logic ◄──┘              │                          │
│     - Track retry count           │                          │
│     - Exponential backoff         │                          │
│     - Max retries = 3             │                          │
│                                   │                          │
│  4. Max Retries Exceeded? ────────┘                          │
│                    │                                         │
│                    ▼                                         │
│  5. Send to DLQ Topic (order-events-dlq)                    │
│     - Original message content                               │
│     - Error details                                          │
│     - Retry metadata                                         │
│     - Timestamps                                             │
│                    │                                         │
│                    ▼                                         │
│  6. Commit Offset (message handled)                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## ⚙️ Configuration

### Environment Variables

```yaml
# DLQ Topic Name
KAFKA_DLQ_TOPIC: order-events-dlq

# Maximum retry attempts before sending to DLQ
DLQ_MAX_RETRIES: 3

# Initial retry backoff in milliseconds
DLQ_RETRY_BACKOFF_MS: 1000

# Maximum backoff delay in milliseconds
DLQ_MAX_BACKOFF_MS: 30000
```

### Retry Strategy

**Exponential Backoff Formula:**
```
backoff_delay = min(initial_backoff * (2 ^ retry_count), max_backoff)
```

**Example Timeline for a Failed Message:**
- Attempt 1: Immediate (0ms)
- Attempt 2: Wait 1s (1000ms)
- Attempt 3: Wait 2s (2000ms)
- Attempt 4: Wait 4s (4000ms)
- After 4 attempts: Send to DLQ

## 📊 DLQ Message Structure

Messages in the DLQ include rich metadata:

```json
{
  "originalMessage": "{...}",           // JSON string of original order
  "errorMessage": "Validation failed",   // Error description
  "errorType": "ValueError",             // Exception class name
  "retryCount": 3,                       // Number of retries attempted
  "failedAttempts": 4,                   // Total attempts (initial + retries)
  "firstFailureTimestamp": "2026-01-26T10:00:00Z",
  "lastFailureTimestamp": "2026-01-26T10:00:15Z",
  "originalTopic": "order-events",       // Source topic
  "originalPartition": 0,                // Source partition
  "originalOffset": 12345,               // Source offset
  "consumerGroup": "order-service-group" // Consumer group ID
}
```

## 🔧 Implementation Details

### Key Components

1. **`consumer.py`** - Enhanced consumer with:
   - Manual offset management (`enable.auto.commit: False`)
   - Retry tracking dictionary
   - Exponential backoff logic
   - DLQ integration

2. **`dlq_producer.py`** - Dedicated DLQ producer:
   - Avro serialization for DLQ messages
   - Schema Registry integration
   - Metadata enrichment
   - Delivery confirmation

3. **`settings.py`** - Configuration:
   - DLQ topic settings
   - Retry parameters
   - Producer configuration

### Critical Code Paths

#### Success Path
```python
msg = consumer.poll()
process_message(msg)  # Success
consumer.commit(msg)  # Only commit on success
```

#### Retry Path
```python
msg = consumer.poll()
try:
    process_message(msg)
except Exception as e:
    if retry_count < MAX_RETRIES:
        # Exponential backoff
        wait(backoff_time)
        # Don't commit - will reprocess
    else:
        send_to_dlq(msg, error=e)
        consumer.commit(msg)  # Handled via DLQ
```

## 📈 Monitoring & Observability

### API Endpoints

#### 1. Get DLQ Configuration
```bash
GET http://localhost:8001/api/dlq/info
```

**Response:**
```json
{
  "success": true,
  "dlqConfig": {
    "dlqTopic": "order-events-dlq",
    "maxRetries": 3,
    "initialBackoffMs": 1000,
    "maxBackoffMs": 30000
  },
  "consumerStats": {
    "isRunning": true,
    "messagesInRetry": 2,
    "retryTrackerDetails": [...]
  }
}
```

#### 2. Get DLQ Messages
```bash
GET http://localhost:8001/api/dlq/messages
```

**Response:**
```json
{
  "success": true,
  "dlqTopic": "order-events-dlq",
  "messageCount": 5,
  "messages": [...]
}
```

### Log Monitoring

**Key Log Patterns:**

```
# Successful processing
INFO: Order ORDER-001 processed successfully

# Retry attempt
WARNING: Will retry order ORDER-001 in 2.0 seconds (retry 1/3)

# DLQ send
ERROR: Max retries (3) exceeded for order ORDER-001. Sending to DLQ...
ERROR: Message sent to DLQ | OrderID: ORDER-001 | Error: ValueError | Retry Count: 3

# Critical failure
CRITICAL: Failed to send order ORDER-001 to DLQ. Message will be retried.
```

## 🧪 Testing the DLQ

### Scenario 1: Simulate a Processing Failure

Create a temporary failure in `order_processor.py`:

```python
def process_order_event(self, order_data: Dict[str, Any]) -> None:
    order_id = order_data.get('orderId', 'Unknown')
    
    # Simulate failure for testing
    if order_id == "ORDER-TEST-FAIL":
        raise ValueError("Simulated processing failure")
    
    # Normal processing continues...
```

### Scenario 2: Send Test Order

```bash
# Create an order that will fail
curl -X POST http://localhost:8000/api/create-order \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ORDER-TEST-FAIL",
    "numItems": 2
  }'
```

### Scenario 3: Verify DLQ

```bash
# Check DLQ info
curl http://localhost:8001/api/dlq/info

# Check DLQ messages
curl http://localhost:8001/api/dlq/messages
```

### Expected Behavior

1. Message is received from `order-events` topic
2. Processing fails with ValueError
3. Consumer retries 3 times with exponential backoff:
   - Retry 1: Wait 1s
   - Retry 2: Wait 2s
   - Retry 3: Wait 4s
4. After 3 retries, message is sent to `order-events-dlq`
5. Offset is committed (message handled)
6. Consumer continues processing other messages

## 🔄 Reprocessing DLQ Messages

### Manual Reprocessing

To reprocess messages from the DLQ:

1. **Fix the underlying issue** (bug, validation rule, etc.)
2. **Create a reprocessing consumer** that reads from DLQ topic
3. **Parse the `originalMessage` field** and reprocess
4. **Delete from DLQ** after successful reprocessing

### Example Reprocessing Script

```python
from service.kafka import KafkaConsumerService
from business.order import OrderProcessor
import json

consumer = KafkaConsumerService()
processor = OrderProcessor()

# Read DLQ messages
dlq_messages = consumer.get_all_messages_from_topic("order-events-dlq")

for dlq_msg in dlq_messages:
    try:
        # Parse original message
        original_msg = json.loads(dlq_msg['originalMessage'])
        
        # Attempt reprocessing
        processor.process_order_event(original_msg)
        print(f"✅ Reprocessed: {original_msg['orderId']}")
        
    except Exception as e:
        print(f"❌ Still failing: {original_msg['orderId']}: {e}")
```

## 🚨 Troubleshooting

### Issue: Messages Going to DLQ Immediately

**Possible Causes:**
- `DLQ_MAX_RETRIES` set to 0
- Processing logic has a bug
- Validation too strict

**Solution:**
- Check DLQ configuration
- Review error messages in DLQ
- Adjust retry count if needed

### Issue: Consumer Not Committing Offsets

**Possible Causes:**
- All messages are failing
- DLQ producer is down
- Network issues

**Solution:**
- Check DLQ producer connectivity
- Monitor retry tracker size
- Review consumer logs

### Issue: DLQ Topic Not Created

**Possible Causes:**
- Auto-create topics disabled in Kafka
- DLQ producer not initialized

**Solution:**
```bash
# Manually create DLQ topic
docker exec -it kafka bash
kafka-topics --create \
  --bootstrap-server localhost:9092 \
  --topic order-events-dlq \
  --partitions 3 \
  --replication-factor 1
```

## 📊 Performance Considerations

### Retry Impact
- **Backoff delays** slow down processing for failed messages
- **Other messages** continue processing normally
- **Partition blocking**: A failing message blocks its partition temporarily

### Recommendations
1. **Monitor DLQ size** - High volume indicates systemic issues
2. **Set appropriate retry counts** - Balance between recovery and latency
3. **Alert on DLQ growth** - Set up monitoring alerts
4. **Regular DLQ review** - Analyze patterns in failures

## 🔐 Best Practices

### Do's ✅
- ✅ Monitor DLQ topic size regularly
- ✅ Set up alerts for DLQ messages
- ✅ Review DLQ messages for patterns
- ✅ Fix root causes, not symptoms
- ✅ Keep retry counts reasonable (3-5)
- ✅ Use exponential backoff
- ✅ Log all DLQ operations

### Don'ts ❌
- ❌ Ignore messages in DLQ
- ❌ Set infinite retries
- ❌ Auto-reprocess without fixing issues
- ❌ Delete DLQ messages without analysis
- ❌ Disable DLQ in production
- ❌ Use fixed retry delays (causes thundering herd)

## 📚 Related Documentation

- [Kafka Consumer Documentation](../README.md)
- [Order Processing Logic](../business/order/order_processor.py)
- [Configuration Guide](../config/settings.py)
- [API Documentation](http://localhost:8001/docs)

## 🎓 Additional Resources

- **Confluent Kafka DLQ Patterns**: https://www.confluent.io/blog/error-handling-patterns-in-kafka/
- **Retry Strategies**: https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- **Offset Management**: https://docs.confluent.io/platform/current/clients/consumer.html#offset-management
