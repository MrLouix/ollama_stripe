"""Application configuration"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    database_url: str
    
    # Redis
    redis_url: str
    
    # Ollama
    ollama_url: str = "http://ollama:11434"
    
    # Stripe
    stripe_secret_key: str
    stripe_webhook_secret: str
    
    # Auth
    admin_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60
    
    # Domain
    domain: str
    
    class Config:
        env_file = ".env"


settings = Settings()
