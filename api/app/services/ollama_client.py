"""Ollama API client with OpenAI format transformation"""

import httpx
from typing import Dict, Any
from app.config import settings


class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(self):
        self.base_url = settings.ollama_url
        self.client = httpx.AsyncClient(timeout=120.0)
    
    async def chat(self, model: str, messages: list[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Call Ollama API /api/chat (native format)
        
        Args:
            model: Model name (e.g., "llama3")
            messages: List of message dicts with role and content
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
        
        Returns:
            Raw Ollama response
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            **kwargs
        }
        
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    async def list_models(self) -> list[str]:
        """
        List available models via /api/tags
        
        Returns:
            List of model names
        """
        url = f"{self.base_url}/api/tags"
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        return [model["name"] for model in data.get("models", [])]
    
    def transform_to_openai_format(self, ollama_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """
        Transform Ollama response to OpenAI format
        
        Args:
            ollama_response: Raw response from Ollama
            model: Model name
        
        Returns:
            OpenAI-compatible response dict
        """
        message = ollama_response.get("message", {})
        created_at = ollama_response.get("created_at", "")
        
        # Generate ID from timestamp or use a default
        chat_id = f"chatcmpl-{str(created_at).replace('T', '').replace('Z', '').replace('-', '').replace(':', '')[:20]}"
        
        return {
            "id": chat_id,
            "object": "chat.completion",
            "created": int(ollama_response.get("created_at", 0)) if isinstance(ollama_response.get("created_at"), (int, float)) else 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": message.get("role", "assistant"),
                        "content": message.get("content", "")
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": ollama_response.get("prompt_eval_count", 0),
                "completion_tokens": ollama_response.get("eval_count", 0),
                "total_tokens": (
                    ollama_response.get("prompt_eval_count", 0) +
                    ollama_response.get("eval_count", 0)
                )
            }
        }
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Global client instance
ollama_client = OllamaClient()
