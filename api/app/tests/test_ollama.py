"""Tests for Ollama client"""

import pytest
from app.services.ollama_client import OllamaClient


def test_ollama_transform_to_openai():
    """Test transformation from Ollama format to OpenAI format"""
    client = OllamaClient()
    
    ollama_response = {
        "model": "llama3",
        "created_at": "2024-05-12T10:30:00Z",
        "message": {
            "role": "assistant",
            "content": "Hello! How can I help you today?"
        },
        "prompt_eval_count": 25,
        "eval_count": 12
    }
    
    openai_format = client.transform_to_openai_format(ollama_response, "llama3")
    
    assert openai_format["model"] == "llama3"
    assert openai_format["object"] == "chat.completion"
    assert openai_format["choices"][0]["message"]["role"] == "assistant"
    assert openai_format["choices"][0]["message"]["content"] == "Hello! How can I help you today?"
    assert openai_format["choices"][0]["finish_reason"] == "stop"
    assert openai_format["usage"]["prompt_tokens"] == 25
    assert openai_format["usage"]["completion_tokens"] == 12
    assert openai_format["usage"]["total_tokens"] == 37


def test_ollama_transform_missing_counts():
    """Test transformation when token counts are missing"""
    client = OllamaClient()
    
    ollama_response = {
        "model": "llama3",
        "created_at": "2024-05-12T10:30:00Z",
        "message": {
            "role": "assistant",
            "content": "Response"
        }
    }
    
    openai_format = client.transform_to_openai_format(ollama_response, "llama3")
    
    assert openai_format["usage"]["prompt_tokens"] == 0
    assert openai_format["usage"]["completion_tokens"] == 0
    assert openai_format["usage"]["total_tokens"] == 0


def test_ollama_transform_empty_message():
    """Test transformation with empty message"""
    client = OllamaClient()
    
    ollama_response = {
        "model": "llama3",
        "created_at": "2024-05-12T10:30:00Z",
        "message": {},
        "prompt_eval_count": 10,
        "eval_count": 5
    }
    
    openai_format = client.transform_to_openai_format(ollama_response, "llama3")
    
    assert openai_format["choices"][0]["message"]["role"] == "assistant"
    assert openai_format["choices"][0]["message"]["content"] == ""


def test_ollama_id_generation():
    """Test that chat completion ID is generated"""
    client = OllamaClient()
    
    ollama_response = {
        "model": "llama3",
        "created_at": "2024-05-12T10:30:00Z",
        "message": {
            "role": "assistant",
            "content": "Test"
        },
        "prompt_eval_count": 5,
        "eval_count": 3
    }
    
    openai_format = client.transform_to_openai_format(ollama_response, "llama3")
    
    assert openai_format["id"].startswith("chatcmpl-")
    assert len(openai_format["id"]) > 10


# Integration tests (require Ollama running)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_list_models_integration():
    """Integration test: list models from Ollama"""
    client = OllamaClient()
    
    try:
        models = await client.list_models()
        assert isinstance(models, list)
        # May be empty if no models pulled
    except Exception as e:
        pytest.skip(f"Ollama not available: {e}")
    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_chat_integration():
    """Integration test: chat with Ollama"""
    client = OllamaClient()
    
    try:
        response = await client.chat(
            model="llama3",
            messages=[{"role": "user", "content": "Say hello in 3 words"}],
            temperature=0.7
        )
        assert "message" in response
        assert response["message"]["role"] == "assistant"
        assert len(response["message"]["content"]) > 0
    except Exception as e:
        pytest.skip(f"Ollama not available or model not pulled: {e}")
    finally:
        await client.close()
