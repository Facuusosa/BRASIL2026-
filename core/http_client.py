"""
🌐 HTTP Client — Wrapper de curl_cffi con Impersonación + Retry + Circuit Breaker

Extraído de:
- curl_cffi docs: https://curl-cffi.readthedocs.io/en/latest/
- error-handling-patterns skill: https://skills.sh/wshobson/agents/error-handling-patterns
- async-python-patterns skill: https://skills.sh/wshobson/agents/async-python-patterns

USO BÁSICO:
    from core.http_client import HttpClient
    
    client = HttpClient()
    response = client.get("https://www.fravega.com/api/graphql")
    
    # Async
    async with AsyncHttpClient() as client:
        response = await client.get("https://www.fravega.com")

NUNCA usar `requests` directamente. SIEMPRE pasar por este módulo.
"""

from __future__ import annotations

import random
import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse

try:
    from curl_cffi import Session, AsyncSession, CurlHttpVersion
except ImportError:
    raise ImportError(
        "curl_cffi no está instalado. Ejecutar: pip install curl_cffi --upgrade"
    )

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURACIÓN DE BROWSERS PARA IMPERSONACIÓN
# ============================================================================

# Versiones de Chrome populares para rotación
# Ref: curl_cffi FAQ - usar versiones con market share alto
CHROME_VERSIONS = [
    "chrome",       # Siempre la última versión disponible
    "chrome119",
    "chrome120",
    "chrome124",
]

SAFARI_VERSIONS = [
    "safari",
    "safari_ios",
]

# Headers adicionales para parecer argentino
ARGENTINA_HEADERS = {
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# ============================================================================
# STEALTH CONFIG — Parámetros anti-detección
# ============================================================================

# Delay aleatorio entre requests (segundos)
STEALTH_DELAY_MIN = 0.8
STEALTH_DELAY_MAX = 2.5

# Límite de requests por dominio por hora
DOMAIN_RATE_LIMIT_PER_HOUR = 300

# Cuánto esperar si recibimos 429 (segundos)
RATELIMIT_BACKOFF = 60


# ============================================================================
# CIRCUIT BREAKER — Previene bombardear APIs caídas
# Ref: error-handling-patterns skill
# ============================================================================

class CircuitState(Enum):
    """
    CLOSED  → Todo normal, requests pasan
    OPEN    → API caída detectada, requests se rechazan inmediatamente
    HALF_OPEN → Periodo de prueba, deja pasar 1 request para ver si se recuperó
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """
    Circuit Breaker Pattern.
    
    Después de `failure_threshold` fallos consecutivos, abre el circuito
    por `recovery_timeout` segundos. Luego deja pasar 1 request de prueba.
    Si funciona, cierra el circuito. Si falla, lo abre de nuevo.
    
    Ejemplo:
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        if cb.can_execute():
            try:
                response = make_request()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
    """
    failure_threshold: int = 5
    recovery_timeout: int = 60  # segundos
    success_threshold: int = 2  # éxitos necesarios en HALF_OPEN para cerrar
    
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    success_count: int = field(default=0, init=False)
    last_failure_time: Optional[datetime] = field(default=None, init=False)
    
    def can_execute(self) -> bool:
        """¿Se puede ejecutar un request?"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # ¿Pasó suficiente tiempo para probar?
            if self.last_failure_time and \
               datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info("⚡ Circuit Breaker → HALF_OPEN (probando...)")
                return True
            return False
        
        # HALF_OPEN: dejar pasar
        return True
    
    def record_success(self) -> None:
        """Registrar un request exitoso."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("✅ Circuit Breaker → CLOSED (recuperado)")
        else:
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Registrar un request fallido."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("🔴 Circuit Breaker → OPEN (falló en prueba)")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"🔴 Circuit Breaker → OPEN (tras {self.failure_count} fallos)"
            )
    
    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN


# ============================================================================
# HTTP CLIENT — Wrapper Sincrónico de curl_cffi
# ============================================================================

class HttpClient:
    """
    Cliente HTTP que usa curl_cffi con impersonación de Chrome.
    
    Features:
    - Impersonación TLS/JA3 de Chrome (bypass WAF)
    - Retry automático con exponential backoff
    - Circuit Breaker para APIs caídas
    - Rotación de versiones de Chrome
    - Cookies persistentes (simula navegación real)
    - HTTP/2 por defecto, HTTP/3 disponible
    - 🛡️ Stealth: delays aleatorios entre requests
    - 🛡️ Rate limiting por dominio (max requests/hora)
    - 🛡️ Manejo automático de 429 (Too Many Requests)
    - 🛡️ Session warming (visita homepage como humano)
    
    Ejemplo:
        client = HttpClient()
        
        # GET simple
        r = client.get("https://www.fravega.com")
        
        # POST con JSON (GraphQL)
        r = client.post("https://www.fravega.com/api/graphql", json=payload)
        
        # Con context manager (recomendado)
        with HttpClient() as client:
            r = client.get("https://www.fravega.com")
    """
    
    def __init__(
        self,
        impersonate: str = "chrome",
        retry_count: int = 3,
        retry_delay: float = 0.5,
        retry_backoff: str = "exponential",
        retry_jitter: float = 0.2,
        timeout: float = 30.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
        extra_headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        http_version: Optional[str] = None,
        rotate_browser: bool = False,
        stealth_mode: bool = True,
        delay_range: tuple[float, float] = (STEALTH_DELAY_MIN, STEALTH_DELAY_MAX),
        max_requests_per_hour: int = DOMAIN_RATE_LIMIT_PER_HOUR,
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.proxy = proxy
        self.http_version = http_version
        self.rotate_browser = rotate_browser
        
        # 🛡️ Stealth config
        self.stealth_mode = stealth_mode
        self.delay_range = delay_range
        self.max_requests_per_hour = max_requests_per_hour
        self._last_request_time: float = 0
        self._domain_request_counts: dict[str, list[float]] = defaultdict(list)
        self._warmed_domains: set[str] = set()
        
        # Retry config (manual, ya que RetryStrategy no existe en v0.14)
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.retry_jitter = retry_jitter
        
        # Headers base (argentinos + custom)
        self.headers = {**ARGENTINA_HEADERS}
        if extra_headers:
            self.headers.update(extra_headers)
        
        # Session con cookies persistentes
        self._session: Optional[Session] = None
    
    def _get_browser(self) -> str:
        """Obtener browser para impersonar (fijo o rotado)."""
        if self.rotate_browser:
            return random.choice(CHROME_VERSIONS)
        return self.impersonate
    
    def _ensure_session(self) -> Session:
        """Crear session si no existe."""
        if self._session is None:
            kwargs: dict[str, Any] = {
                "impersonate": self._get_browser(),
                "headers": self.headers,
                "timeout": self.timeout,
            }
            if self.proxy:
                kwargs["proxy"] = self.proxy
            self._session = Session(**kwargs)
        return self._session
    
    def _get_domain(self, url: str) -> str:
        """Extraer dominio de una URL."""
        return urlparse(url).netloc
    
    def _stealth_delay(self) -> None:
        """Esperar un tiempo aleatorio entre requests (anti-detección)."""
        if not self.stealth_mode:
            return
        
        # Calcular tiempo desde último request
        now = time.time()
        elapsed = now - self._last_request_time
        
        # Si pasó muy poco tiempo, esperar
        min_delay, max_delay = self.delay_range
        if elapsed < min_delay:
            wait = random.uniform(min_delay, max_delay) - elapsed
            if wait > 0:
                logger.debug(f"🛡️ Stealth delay: {wait:.1f}s")
                time.sleep(wait)
        
        self._last_request_time = time.time()
    
    def _check_rate_limit(self, url: str) -> None:
        """Verificar que no excedimos el rate limit por dominio."""
        if not self.stealth_mode:
            return
        
        domain = self._get_domain(url)
        now = time.time()
        one_hour_ago = now - 3600
        
        # Limpiar requests viejas (más de 1 hora)
        self._domain_request_counts[domain] = [
            t for t in self._domain_request_counts[domain] if t > one_hour_ago
        ]
        
        # Verificar límite
        count = len(self._domain_request_counts[domain])
        if count >= self.max_requests_per_hour:
            wait_time = 3600 - (now - self._domain_request_counts[domain][0])
            logger.warning(
                f"🛡️ Rate limit alcanzado para {domain} "
                f"({count}/{self.max_requests_per_hour} req/hora). "
                f"Esperando {wait_time:.0f}s..."
            )
            time.sleep(min(wait_time, 300))  # Max 5 min de espera
        
        # Registrar request
        self._domain_request_counts[domain].append(now)
    
    def warm_session(self, base_url: str) -> None:
        """
        🛡️ Calentar la sesión visitando la homepage primero.
        Un browser real no va directo a la API — visita la home, carga CSS/JS, etc.
        Esto establece cookies de sesión y parece comportamiento humano.
        
        Ejemplo:
            client.warm_session("https://www.oncity.com")
            # Ahora sí, usar la API
            r = client.get("https://www.oncity.com/api/...")
        """
        domain = self._get_domain(base_url)
        if domain in self._warmed_domains:
            return  # Ya calentada
        
        logger.info(f"🔥 Warming session para {domain}...")
        try:
            self.get(base_url)
            self._warmed_domains.add(domain)
            # Pausa extra después de warming (humano mirando la página)
            time.sleep(random.uniform(1.0, 3.0))
        except Exception as e:
            logger.warning(f"⚠️ Error warming {domain}: {e}")
    
    def reset_session(self) -> None:
        """🛡️ Rotar sesión: cerrar la actual y crear una nueva con otro browser."""
        self.close()
        self._warmed_domains.clear()
        if self.rotate_browser:
            logger.info(f"🔄 Sesión rotada, nuevo browser: {self._get_browser()}")
    
    def get(self, url: str, **kwargs) -> Any:
        """GET request con impersonación + retry + circuit breaker."""
        return self._request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> Any:
        """POST request con impersonación + retry + circuit breaker."""
        return self._request("POST", url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> Any:
        """Request interno con Stealth + Circuit Breaker + Retry manual."""
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit Breaker OPEN — API {url} está caída. "
                f"Reintentando en {self.circuit_breaker.recovery_timeout}s"
            )
        
        # 🛡️ Anti-detección: delay + rate limit check
        self._stealth_delay()
        self._check_rate_limit(url)
        
        session = self._ensure_session()
        
        # Agregar http_version si está configurado
        if self.http_version and "http_version" not in kwargs:
            kwargs["http_version"] = self.http_version
        
        last_exception = None
        for attempt in range(self.retry_count + 1):
            try:
                if method == "GET":
                    response = session.get(url, **kwargs)
                elif method == "POST":
                    response = session.post(url, **kwargs)
                else:
                    raise ValueError(f"Método HTTP no soportado: {method}")
                
                # Verificar status
                if response.status_code == 403:
                    self.circuit_breaker.record_failure()
                    raise WAFBlockedError(
                        f"403 Forbidden en {url} — WAF detectó la request. "
                        "Intentar: rotar browser, usar proxy, o esperar."
                    )
                
                if response.status_code == 429:
                    # 🛡️ Rate limited — esperar y reintentar
                    retry_after = int(response.headers.get("Retry-After", RATELIMIT_BACKOFF))
                    logger.warning(f"🛡️ 429 Rate Limited en {url}. Esperando {retry_after}s...")
                    time.sleep(retry_after)
                    raise RateLimitError(f"429 en {url} — Rate limited")
                
                if response.status_code >= 500:
                    self.circuit_breaker.record_failure()
                    raise ServerError(f"Error {response.status_code} en {url}")
                
                response.raise_for_status()
                self.circuit_breaker.record_success()
                return response
                
            except (WAFBlockedError,):
                raise  # No retry on WAF block
            except Exception as e:
                last_exception = e
                if attempt < self.retry_count:
                    delay = self.retry_delay * (2 ** attempt) + random.uniform(0, self.retry_jitter)
                    logger.warning(f"Retry {attempt+1}/{self.retry_count} para {url} en {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    self.circuit_breaker.record_failure()
                    raise NetworkError(f"Error de red en {url}: {e}") from e
    
    def get_json(self, url: str, **kwargs) -> dict:
        """GET y parsear JSON directamente."""
        return self.get(url, **kwargs).json()
    
    def post_json(self, url: str, **kwargs) -> dict:
        """POST y parsear JSON directamente."""
        return self.post(url, **kwargs).json()
    
    def graphql(self, url: str, query: str, variables: Optional[dict] = None) -> dict:
        """
        Ejecutar query GraphQL.
        
        Ejemplo:
            data = client.graphql(
                "https://www.fravega.com/api/graphql",
                query='{ search(term: "iphone") { products { name price } } }',
                variables={"page": 1}
            )
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        return self.post_json(url, json=payload)
    
    def verify_fingerprint(self) -> dict:
        """
        Verificar que la impersonación funciona.
        Compara el JA3 fingerprint contra el de un Chrome real.
        
        Ref: curl_cffi impersonation FAQ
        """
        r = self.get("https://tls.browserleaks.com/json")
        data = r.json()
        logger.info(f"🔍 JA3 Hash: {data.get('ja3n_hash', 'N/A')}")
        logger.info(f"🔍 User-Agent: {data.get('user_agent', 'N/A')}")
        return data
    
    def close(self) -> None:
        """Cerrar session y liberar recursos."""
        if self._session:
            self._session.close()
            self._session = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


# ============================================================================
# ASYNC HTTP CLIENT — Para Scraping Paralelo
# Ref: curl_cffi asyncio docs + async-python-patterns skill
# ============================================================================

class AsyncHttpClient:
    """
    Cliente HTTP Asincrónico con curl_cffi.
    
    Features adicionales sobre HttpClient:
    - Semaphore para rate limiting (max N requests paralelos)
    - asyncio.gather() para batch processing
    - Ideal para scrapear múltiples categorías/páginas en paralelo
    
    Ejemplo:
        async with AsyncHttpClient(max_concurrent=3) as client:
            urls = ["https://fravega.com/cat1", "https://fravega.com/cat2"]
            results = await client.gather_get(urls)
    """
    
    def __init__(
        self,
        impersonate: str = "chrome",
        max_concurrent: int = 3,
        timeout: float = 30.0,
        retry_count: int = 3,
        circuit_breaker: Optional[CircuitBreaker] = None,
        extra_headers: Optional[dict] = None,
        proxy: Optional[str] = None,
    ):
        self.impersonate = impersonate
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.proxy = proxy
        
        self.retry_count = retry_count
        
        self.headers = {**ARGENTINA_HEADERS}
        if extra_headers:
            self.headers.update(extra_headers)
        
        self._session: Optional[AsyncSession] = None
        self._semaphore: Optional[Any] = None  # Se crea en __aenter__
    
    async def __aenter__(self):
        import asyncio
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        
        kwargs: dict[str, Any] = {
            "impersonate": self.impersonate,
            "headers": self.headers,
            "timeout": self.timeout,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        self._session = AsyncSession(**kwargs)
        return self
    
    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
    
    async def get(self, url: str, **kwargs) -> Any:
        """GET con semaphore (rate limited)."""
        async with self._semaphore:
            if not self.circuit_breaker.can_execute():
                raise CircuitBreakerOpenError(f"Circuit Breaker OPEN para {url}")
            
            try:
                response = await self._session.get(url, **kwargs)
                
                if response.status_code == 403:
                    self.circuit_breaker.record_failure()
                    raise WAFBlockedError(f"403 en {url}")
                
                response.raise_for_status()
                self.circuit_breaker.record_success()
                return response
                
            except (WAFBlockedError,):
                raise
            except Exception as e:
                self.circuit_breaker.record_failure()
                raise NetworkError(f"Error en {url}: {e}") from e
    
    async def post(self, url: str, **kwargs) -> Any:
        """POST con semaphore (rate limited)."""
        async with self._semaphore:
            if not self.circuit_breaker.can_execute():
                raise CircuitBreakerOpenError(f"Circuit Breaker OPEN para {url}")
            
            try:
                response = await self._session.post(url, **kwargs)
                response.raise_for_status()
                self.circuit_breaker.record_success()
                return response
            except Exception as e:
                self.circuit_breaker.record_failure()
                raise NetworkError(f"Error en {url}: {e}") from e
    
    async def gather_get(
        self,
        urls: list[str],
        return_exceptions: bool = True,
        **kwargs,
    ) -> list[Any]:
        """
        GET múltiples URLs en paralelo (limitado por semaphore).
        
        Ref: async-python-patterns skill — batch processing con gather()
        
        Ejemplo:
            results = await client.gather_get([
                "https://fravega.com/celulares",
                "https://fravega.com/notebooks", 
                "https://fravega.com/tvs",
            ])
            for r in results:
                if not isinstance(r, Exception):
                    print(r.json())
        """
        import asyncio
        tasks = [self.get(url, **kwargs) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
    
    async def graphql_batch(
        self,
        url: str,
        queries: list[dict],
        return_exceptions: bool = True,
    ) -> list[Any]:
        """
        Ejecutar múltiples queries GraphQL en paralelo.
        
        Ejemplo:
            queries = [
                {"query": "...", "variables": {"cat": "celulares"}},
                {"query": "...", "variables": {"cat": "notebooks"}},
            ]
            results = await client.graphql_batch(fravega_url, queries)
        """
        import asyncio
        tasks = [self.post(url, json=q) for q in queries]
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)


# ============================================================================
# EXCEPCIONES CUSTOM — Jerarquía de Errores
# Ref: error-handling-patterns skill
# ============================================================================

class ScrapingError(Exception):
    """Error base de scraping. Todos los errores de scraping heredan de acá."""
    pass

class WAFBlockedError(ScrapingError):
    """403 Forbidden — WAF detectó la request como bot."""
    pass

class CircuitBreakerOpenError(ScrapingError):
    """Circuit Breaker está abierto — API está caída, no intentar."""
    pass

class NetworkError(ScrapingError):
    """Error de red genérico (timeout, DNS, conexión rechazada)."""
    pass

class ServerError(ScrapingError):
    """Error 5xx del servidor."""
    pass

class ParsingError(ScrapingError):
    """Error al parsear la respuesta (JSON inválido, estructura inesperada)."""
    pass

class RateLimitError(ScrapingError):
    """429 Too Many Requests — Rate limit excedido."""
    pass

class GlitchDetectedError(ScrapingError):
    """Precio anormalmente bajo detectado — posible glitch."""
    pass
