"""
Test script for Dead Letter Queue (DLQ) functionality

This script demonstrates how to test the DLQ implementation by:
1. Simulating message processing failures
2. Verifying retry logic
3. Checking DLQ message delivery
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from service.kafka.consumer import KafkaConsumerService
from service.kafka.dlq_producer import DLQProducer
from business.order import OrderProcessor
from config.settings import settings
import time


class TestDLQFunctionality:
    """Test cases for DLQ implementation"""
    
    def test_retry_backoff_calculation(self):
        """Test exponential backoff calculation"""
        consumer = KafkaConsumerService()
        
        # Test exponential backoff
        assert consumer._calculate_backoff(0) == 1.0  # 1000ms / 1000 = 1s
        assert consumer._calculate_backoff(1) == 2.0  # 2000ms / 1000 = 2s
        assert consumer._calculate_backoff(2) == 4.0  # 4000ms / 1000 = 4s
        assert consumer._calculate_backoff(3) == 8.0  # 8000ms / 1000 = 8s
        
        # Test max backoff limit
        assert consumer._calculate_backoff(10) == settings.DLQ_MAX_BACKOFF_MS / 1000
    
    @patch('service.kafka.consumer.KafkaConsumerService._get_dlq_producer')
    def test_message_sent_to_dlq_after_max_retries(self, mock_get_dlq):
        """Test that message is sent to DLQ after max retries"""
        # Setup
        consumer = KafkaConsumerService()
        mock_dlq = Mock()
        mock_dlq.send_to_dlq.return_value = True
        mock_get_dlq.return_value = mock_dlq
        
        # Create a mock message
        mock_msg = Mock()
        mock_msg.value.return_value = {
            'orderId': 'TEST-ORDER-001',
            'customerId': 'CUST-001',
            'orderDate': '2026-01-26T10:00:00Z',
            'items': [],
            'totalAmount': 100.0,
            'currency': 'USD',
            'status': 'pending'
        }
        mock_msg.topic.return_value = 'order-events'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 123
        
        # Setup message handler that always fails
        def failing_handler(order_data):
            raise ValueError("Simulated processing failure")
        
        consumer.message_handler = failing_handler
        
        # Simulate retry tracking (already at max retries)
        message_key = ('order-events', 0, 123)
        consumer.retry_tracker[message_key] = (settings.DLQ_MAX_RETRIES, '2026-01-26T10:00:00Z')
        
        # Process message - should go to DLQ
        with patch('time.sleep'):  # Skip actual sleep
            result = consumer._process_message_with_retry(mock_msg)
        
        # Verify DLQ was called
        assert result is True
        assert mock_dlq.send_to_dlq.called
        assert message_key not in consumer.retry_tracker
    
    def test_retry_tracker_increments(self):
        """Test that retry tracker increments correctly"""
        consumer = KafkaConsumerService()
        
        # Create a mock message
        mock_msg = Mock()
        mock_msg.value.return_value = {
            'orderId': 'TEST-ORDER-002',
            'customerId': 'CUST-002',
            'orderDate': '2026-01-26T10:00:00Z',
            'items': [],
            'totalAmount': 100.0,
            'currency': 'USD',
            'status': 'pending'
        }
        mock_msg.topic.return_value = 'order-events'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 124
        
        # Setup message handler that always fails
        def failing_handler(order_data):
            raise ValueError("Test failure")
        
        consumer.message_handler = failing_handler
        
        # Process message multiple times
        message_key = ('order-events', 0, 124)
        
        with patch('time.sleep'):  # Skip actual sleep
            # First attempt (retry_count = 0)
            consumer._process_message_with_retry(mock_msg)
            assert message_key in consumer.retry_tracker
            assert consumer.retry_tracker[message_key][0] == 1
            
            # Second attempt (retry_count = 1)
            consumer._process_message_with_retry(mock_msg)
            assert consumer.retry_tracker[message_key][0] == 2
            
            # Third attempt (retry_count = 2)
            consumer._process_message_with_retry(mock_msg)
            assert consumer.retry_tracker[message_key][0] == 3
    
    def test_successful_processing_clears_retry_tracker(self):
        """Test that successful processing removes entry from retry tracker"""
        consumer = KafkaConsumerService()
        
        # Create a mock message
        mock_msg = Mock()
        order_data = {
            'orderId': 'TEST-ORDER-003',
            'customerId': 'CUST-003',
            'orderDate': '2026-01-26T10:00:00Z',
            'items': [{'itemId': 'ITEM-001', 'quantity': 1, 'price': 100.0}],
            'totalAmount': 100.0,
            'currency': 'USD',
            'status': 'pending'
        }
        mock_msg.value.return_value = order_data
        mock_msg.topic.return_value = 'order-events'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 125
        
        # Setup message handler that succeeds
        def successful_handler(order_data):
            pass  # Success
        
        consumer.message_handler = successful_handler
        
        # Add to retry tracker (simulating previous failure)
        message_key = ('order-events', 0, 125)
        consumer.retry_tracker[message_key] = (1, '2026-01-26T10:00:00Z')
        
        # Process message - should succeed and clear tracker
        result = consumer._process_message_with_retry(mock_msg)
        
        assert result is True
        assert message_key not in consumer.retry_tracker
    
    def test_dlq_message_structure(self):
        """Test that DLQ messages contain all required metadata"""
        dlq_producer = DLQProducer()
        
        # Mock the producer
        with patch.object(dlq_producer, 'producer') as mock_producer:
            mock_producer.produce = Mock()
            mock_producer.flush = Mock()
            
            # Test data
            message_value = {'orderId': 'TEST-001'}
            error = ValueError("Test error")
            
            # Send to DLQ
            dlq_producer.send_to_dlq(
                message_value=message_value,
                message_key='TEST-001',
                error=error,
                retry_count=3,
                original_topic='order-events',
                original_partition=0,
                original_offset=100,
                first_failure_timestamp='2026-01-26T10:00:00Z'
            )
            
            # Verify produce was called
            assert mock_producer.produce.called
            
            # Get the call arguments
            call_args = mock_producer.produce.call_args
            dlq_message = call_args[1]['value']
            
            # Verify all required fields are present
            assert 'originalMessage' in dlq_message
            assert 'errorMessage' in dlq_message
            assert 'errorType' in dlq_message
            assert 'retryCount' in dlq_message
            assert 'failedAttempts' in dlq_message
            assert 'firstFailureTimestamp' in dlq_message
            assert 'lastFailureTimestamp' in dlq_message
            assert 'originalTopic' in dlq_message
            assert 'originalPartition' in dlq_message
            assert 'originalOffset' in dlq_message
            assert 'consumerGroup' in dlq_message
            
            # Verify values
            assert dlq_message['errorType'] == 'ValueError'
            assert dlq_message['retryCount'] == 3
            assert dlq_message['failedAttempts'] == 4
            assert dlq_message['originalTopic'] == 'order-events'


class TestDLQIntegration:
    """Integration tests for DLQ with real processing logic"""
    
    @pytest.mark.integration
    def test_order_processor_validation_failure_goes_to_dlq(self):
        """Test that validation failures are sent to DLQ after retries"""
        consumer = KafkaConsumerService()
        processor = OrderProcessor()
        
        # Set the processor as the message handler
        consumer.message_handler = processor.process_order_event
        
        # Create a mock message with invalid data (missing required fields)
        mock_msg = Mock()
        mock_msg.value.return_value = {
            'orderId': 'TEST-INVALID',
            # Missing required fields - will fail validation
        }
        mock_msg.topic.return_value = 'order-events'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 200
        
        # Mock DLQ producer
        with patch('service.kafka.consumer.KafkaConsumerService._get_dlq_producer') as mock_get_dlq:
            mock_dlq = Mock()
            mock_dlq.send_to_dlq.return_value = True
            mock_get_dlq.return_value = mock_dlq
            
            # Set to max retries
            message_key = ('order-events', 0, 200)
            consumer.retry_tracker[message_key] = (settings.DLQ_MAX_RETRIES, '2026-01-26T10:00:00Z')
            
            with patch('time.sleep'):
                result = consumer._process_message_with_retry(mock_msg)
            
            # Should be sent to DLQ
            assert result is True
            assert mock_dlq.send_to_dlq.called


# Manual test scenarios for local testing
if __name__ == "__main__":
    print("🧪 DLQ Test Scenarios")
    print("=" * 60)
    
    print("\n1. Test Backoff Calculation:")
    consumer = KafkaConsumerService()
    for i in range(6):
        backoff = consumer._calculate_backoff(i)
        print(f"   Retry {i}: {backoff:.1f} seconds")
    
    print("\n2. DLQ Configuration:")
    print(f"   DLQ Topic: {settings.KAFKA_DLQ_TOPIC}")
    print(f"   Max Retries: {settings.DLQ_MAX_RETRIES}")
    print(f"   Initial Backoff: {settings.DLQ_RETRY_BACKOFF_MS}ms")
    print(f"   Max Backoff: {settings.DLQ_MAX_BACKOFF_MS}ms")
    
    print("\n3. To run pytest tests:")
    print("   pytest tests/test_dlq.py -v")
    
    print("\n4. To test with real Kafka:")
    print("   - Start the services: docker-compose up -d")
    print("   - Send a test order with invalid data")
    print("   - Check DLQ: curl http://localhost:8001/api/dlq/messages")
    
    print("\n✅ DLQ implementation ready for testing!")
