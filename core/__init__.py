"""
🧱 Core Module — Código Compartido entre Todos los Targets

Componentes:
- http_client.py  → Cliente HTTP con curl_cffi + Circuit Breaker + Retry + Async
- base_sniffer.py → Clase abstracta BaseSniffer (fetch, parse, detect, save)
- database.py     → SQLite wrapper con batch operations + queries de precios

Imports rápidos:
    from core import HttpClient, AsyncHttpClient, BaseSniffer, Database
    from core import Product, Glitch, ScrapeResult
    from core import (
        ScrapingError, WAFBlockedError, CircuitBreakerOpenError,
        NetworkError, ServerError, ParsingError, GlitchDetectedError,
    )
"""

# HTTP Client
from core.http_client import (
    HttpClient,
    AsyncHttpClient,
    CircuitBreaker,
    CircuitState,
)

# Excepciones
from core.http_client import (
    ScrapingError,
    WAFBlockedError,
    CircuitBreakerOpenError,
    NetworkError,
    ServerError,
    ParsingError,
    RateLimitError,
    GlitchDetectedError,
)

# Base Sniffer + Data Models
from core.base_sniffer import (
    BaseSniffer,
    Product,
    Glitch,
    ScrapeResult,
)

# Database
from core.database import Database

__all__ = [
    # HTTP
    "HttpClient",
    "AsyncHttpClient", 
    "CircuitBreaker",
    "CircuitState",
    # Errors
    "ScrapingError",
    "WAFBlockedError",
    "CircuitBreakerOpenError",
    "NetworkError",
    "ServerError",
    "ParsingError",
    "RateLimitError",
    "GlitchDetectedError",
    # Sniffer
    "BaseSniffer",
    "Product",
    "Glitch",
    "ScrapeResult",
    # DB
    "Database",
]
