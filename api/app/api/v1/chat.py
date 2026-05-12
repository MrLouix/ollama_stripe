"""Chat completion endpoint (OpenAI-compatible)"""

import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from redis import Redis
from app.models.openai import ChatCompletionRequest, ChatCompletionResponse
from app.dependencies import get_db, get_redis, get_current_api_key
from app.db.models import ApiKey, Subscription
from app.services.ollama_client import ollama_client
from app.services.rate_limit import check_rate_limit, increment_usage
from app.services.quota import check_quota
from app.services.usage_tracker import track_usage

router = APIRouter()


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    """
    OpenAI-compatible chat completion endpoint.
    
    Handles authentication, rate limiting, quota checking, and usage tracking.
    Proxies requests to Ollama and transforms responses to OpenAI format.
    
    Args:
        request: Chat completion request (OpenAI format)
        api_key: Authenticated API key (from Bearer token)
        db: Database session
        redis: Redis client
    
    Returns:
        ChatCompletionResponse in OpenAI format
    
    Raises:
        HTTPException 503: If subscription is inactive
        HTTPException 429: If rate limit or quota exceeded
        HTTPException 502: If Ollama upstream error
    """
    
    # 1. Retrieve tenant and plan
    tenant = api_key.tenant
    subscription = db.query(Subscription).filter(
        Subscription.tenant_id == tenant.id,
        Subscription.status == "active"
    ).first()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No active subscription found"
        )
    
    plan = subscription.plan
    
    # 2. Check rate limit (RPM)
    allowed, retry_after = check_rate_limit(redis, str(api_key.id), plan.rpm_limit)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )
    
    # 3. Estimate tokens (rough approximation: word count * 1.3)
    estimated_tokens = sum(len(m.content.split()) for m in request.messages) * 1.3
    
    # 4. Check quotas (daily and monthly)
    quota_ok, quota_msg = check_quota(redis, str(tenant.id), plan, int(estimated_tokens))
    if not quota_ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=quota_msg
        )
    
    # 5. Call Ollama API
    start_time = time.time()
    try:
        ollama_response = await ollama_client.chat(
            model=request.model,
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
            temperature=request.temperature,
            num_predict=request.max_tokens  # Ollama uses num_predict instead of max_tokens
        )
    except Exception as e:
        # Track failed request
        await track_usage(
            db=db,
            tenant_id=tenant.id,
            api_key_id=api_key.id,
            model=request.model,
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.time() - start_time) * 1000),
            status_code=502,
            error_message=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama upstream error: {str(e)}"
        )
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    # 6. Transform to OpenAI format
    openai_response = ollama_client.transform_to_openai_format(ollama_response, request.model)
    
    # 7. Track actual usage
    actual_tokens = openai_response["usage"]["total_tokens"]
    increment_usage(redis, str(tenant.id), actual_tokens)
    
    await track_usage(
        db=db,
        tenant_id=tenant.id,
        api_key_id=api_key.id,
        model=request.model,
        input_tokens=openai_response["usage"]["prompt_tokens"],
        output_tokens=openai_response["usage"]["completion_tokens"],
        latency_ms=latency_ms,
        status_code=200
    )
    
    return openai_response
