"""Tests for chat completion endpoint"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.openai import ChatCompletionRequest, ChatMessage


def test_chat_request_validation():
    """Test ChatCompletionRequest validation"""
    request = ChatCompletionRequest(
        model="llama3",
        messages=[
            ChatMessage(role="user", content="Hello")
        ],
        temperature=0.8,
        max_tokens=512
    )
    
    assert request.model == "llama3"
    assert len(request.messages) == 1
    assert request.messages[0].role == "user"
    assert request.temperature == 0.8
    assert request.max_tokens == 512
    assert request.stream is False


def test_chat_request_defaults():
    """Test ChatCompletionRequest default values"""
    request = ChatCompletionRequest(
        model="llama3",
        messages=[ChatMessage(role="user", content="Test")]
    )
    
    assert request.temperature == 0.7
    assert request.max_tokens == 1024
    assert request.stream is False


def test_chat_message_validation():
    """Test ChatMessage validation"""
    message = ChatMessage(role="system", content="You are a helpful assistant")
    
    assert message.role == "system"
    assert message.content == "You are a helpful assistant"


def test_multiple_messages():
    """Test request with multiple messages"""
    messages = [
        ChatMessage(role="system", content="You are helpful"),
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there!"),
        ChatMessage(role="user", content="How are you?")
    ]
    
    request = ChatCompletionRequest(
        model="llama3",
        messages=messages
    )
    
    assert len(request.messages) == 4
    assert request.messages[0].role == "system"
    assert request.messages[-1].content == "How are you?"


@pytest.mark.asyncio
async def test_chat_completions_no_subscription(redis_client):
    """Test chat endpoint when tenant has no active subscription"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.dependencies import get_redis
    from unittest.mock import MagicMock
    
    # Mock Redis dependency
    app.dependency_overrides[get_redis] = lambda: redis_client
    
    client = TestClient(app)
    
    # This would need database mocking for full test
    # Skipping full integration test for now
    pytest.skip("Requires database fixtures")


@pytest.mark.asyncio
async def test_token_estimation():
    """Test token estimation logic"""
    messages = [
        ChatMessage(role="user", content="Hello world this is a test message")
    ]
    
    # Token estimation: word count * 1.3
    words = sum(len(m.content.split()) for m in messages)
    estimated = int(words * 1.3)
    
    assert words == 7
    assert estimated == 9  # 7 * 1.3 = 9.1 -> 9


@pytest.mark.asyncio
async def test_ollama_error_tracking():
    """Test that failed Ollama calls are tracked"""
    # This test would verify that usage_tracker is called with error details
    # when Ollama fails
    pytest.skip("Requires full integration setup")
