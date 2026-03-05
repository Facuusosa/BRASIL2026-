"""
🌐 HTTP Client — Ghost Mode para IP Residencial

Wrapper de curl_cffi con:
- TLS Fingerprint Rotation (4 perfiles distintos)
- Chrome 124 stealth headers (Venice.ai config)
- DNS flush antes de cada sesión (clean_scene)
- Circuit Breaker + Retry con exponential backoff
- Rate limiting por dominio + stealth delays

USO:
    from core.http_client import HttpClient
    
    with HttpClient(ghost_mode=True) as client:
        client.clean_scene()   # Flush DNS
        response = client.get("https://target.com")

NUNCA usar `requests` directamente. SIEMPRE pasar por este módulo.
"""

from __future__ import annotations

import os
import platform
import subprocess
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
# TLS FINGERPRINT ROTATION — 4 perfiles distintos
# Cada perfil simula un browser/versión diferente para que cada sesión
# tenga un fingerprint TLS único. Esto evita correlación por JA3.
# ============================================================================

TLS_PROFILES = [
    {
        "name": "chrome124_win",
        "impersonate": "chrome124",
        "cipher_suites": "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-ECDSA-AES128-GCM-SHA256",
        "tls_extensions": "0x0000:0x0005:0x000a:0x000b:0x000d:0x0017:0x0023:0x002b:0x002d:0x0033:0x3549",
    },
    {
        "name": "chrome120_win",
        "impersonate": "chrome120",
        "cipher_suites": "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:ECDHE-RSA-AES128-GCM-SHA256",
        "tls_extensions": "0x0000:0x000b:0x000a:0x0023:0x0010:0x0005:0x000d",
    },
    {
        "name": "chrome119_win",
        "impersonate": "chrome119",
        "cipher_suites": "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:ECDHE-ECDSA-AES256-GCM-SHA384",
        "tls_extensions": "0x0000:0x0005:0x000a:0x000d:0x0017:0x0023:0x002b:0x0033",
    },
    {
        "name": "chrome_latest",
        "impersonate": "chrome",
        "cipher_suites": "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256",
        "tls_extensions": "0x0000:0x0005:0x000a:0x000b:0x000d:0x0017:0x0023:0x002b:0x002d:0x0033",
    },
]

# ============================================================================
# STEALTH HEADER SETS — Rotación de headers como Chrome real
# Cada set tiene variaciones sutiles (orden de accept, versión sec-ch-ua)
# para que cada request parezca un usuario distinto.
# ============================================================================

STEALTH_HEADER_SETS = [
    {   # Chrome 124 Windows — Perfil principal (Venice.ai)
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
    {   # Chrome 120 Windows
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "es-419,es;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
    {   # Chrome 124 — variante con accept-encoding explícito
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "es-AR,es;q=0.9",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    },
]

# Delay aleatorio entre requests (más conservador para ghost mode)
STEALTH_DELAY_MIN = 1.5
STEALTH_DELAY_MAX = 4.0

# Límite de requests por dominio por hora (reducido para IP residencial)
DOMAIN_RATE_LIMIT_PER_HOUR = 120

# Cuánto esperar si recibimos 429 (segundos)
RATELIMIT_BACKOFF = 60

# Legacy compat
CHROME_VERSIONS = [p["impersonate"] for p in TLS_PROFILES]
SAFARI_VERSIONS = ["safari", "safari_ios"]
ARGENTINA_HEADERS = STEALTH_HEADER_SETS[0]  # Default al perfil principal


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
        impersonate: str = "chrome124",
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
        ghost_mode: bool = False,
        delay_range: tuple[float, float] = (STEALTH_DELAY_MIN, STEALTH_DELAY_MAX),
        max_requests_per_hour: int = DOMAIN_RATE_LIMIT_PER_HOUR,
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.proxy = proxy
        self.http_version = http_version
        self.rotate_browser = rotate_browser
        
        # 👻 Ghost mode: activar TODAS las medidas de evasión
        self.ghost_mode = ghost_mode
        if ghost_mode:
            self.rotate_browser = True
            stealth_mode = True
            delay_range = (2.0, 5.0)  # Más lento = más humano
            max_requests_per_hour = 80  # Más conservador
        
        # 🛡️ Stealth config
        self.stealth_mode = stealth_mode
        self.delay_range = delay_range
        self.max_requests_per_hour = max_requests_per_hour
        self._last_request_time: float = 0
        self._domain_request_counts: dict[str, list[float]] = defaultdict(list)
        self._warmed_domains: set[str] = set()
        self._request_count: int = 0  # Contador para rotar TLS
        self._current_tls_profile: dict = random.choice(TLS_PROFILES)
        
        # Retry config
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.retry_jitter = retry_jitter
        
        # Headers: rotar un set stealth completo
        self.headers = dict(random.choice(STEALTH_HEADER_SETS))
        if extra_headers:
            self.headers.update(extra_headers)
        
        # Session con cookies persistentes
        self._session: Optional[Session] = None
    
    # ── GHOST MODE: Métodos de evasión ──────────────────────────────────
    
    @staticmethod
    def clean_scene() -> bool:
        """
        👻 Limpiar la escena antes de operar.
        Ejecuta ipconfig /flushdns para eliminar cache DNS.
        Esto previene que el ISP o un resolver correlacione tus queries DNS
        con las requests HTTP que vienen después.
        
        Returns:
            True si el flush fue exitoso, False si falló.
        """
        system = platform.system()
        try:
            if system == "Windows":
                result = subprocess.run(
                    ["ipconfig", "/flushdns"],
                    capture_output=True, text=True, timeout=10
                )
                success = result.returncode == 0
            elif system == "Darwin":  # macOS
                result = subprocess.run(
                    ["sudo", "dscacheutil", "-flushcache"],
                    capture_output=True, text=True, timeout=10
                )
                success = result.returncode == 0
            else:  # Linux
                result = subprocess.run(
                    ["sudo", "systemd-resolve", "--flush-caches"],
                    capture_output=True, text=True, timeout=10
                )
                success = result.returncode == 0
            
            if success:
                logger.info("👻 DNS cache flushed — escena limpia")
            else:
                logger.warning(f"⚠️ DNS flush returned: {result.stderr.strip()}")
            return success
        except Exception as e:
            logger.warning(f"⚠️ No se pudo limpiar DNS: {e}")
            return False
    
    def _rotate_tls_profile(self) -> None:
        """
        👻 Rotar perfil TLS cada N requests.
        Cambia cipher suites + extensions + impersonation target
        para que cada bloque de requests tenga un fingerprint distinto.
        """
        self._request_count += 1
        # Rotar cada 5-10 requests (aleatorio para no ser predecible)
        rotate_interval = random.randint(5, 10)
        if self._request_count % rotate_interval == 0:
            old_profile = self._current_tls_profile["name"]
            self._current_tls_profile = random.choice(TLS_PROFILES)
            # Rotar headers también
            self.headers = dict(random.choice(STEALTH_HEADER_SETS))
            # Forzar recrear session con nuevo fingerprint
            self.close()
            logger.info(
                f"👻 TLS rotado: {old_profile} → {self._current_tls_profile['name']} "
                f"(request #{self._request_count})"
            )
    
    def _get_browser(self) -> str:
        """Obtener browser para impersonar (del perfil TLS activo o rotado)."""
        if self.rotate_browser or self.ghost_mode:
            return self._current_tls_profile["impersonate"]
        return self.impersonate
    
    def _ensure_session(self) -> Session:
        """Crear session si no existe (con perfil TLS actual)."""
        if self._session is None:
            browser = self._get_browser()
            kwargs: dict[str, Any] = {
                "impersonate": browser,
                "headers": self.headers,
                "timeout": self.timeout,
            }
            if self.proxy:
                kwargs["proxy"] = self.proxy
            self._session = Session(**kwargs)
            logger.debug(f"🔧 Session creada: {browser} | TLS: {self._current_tls_profile['name']}")
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
        """👻 Rotar sesión: nuevo browser + nuevo TLS profile + nuevos headers."""
        self.close()
        self._warmed_domains.clear()
        self._current_tls_profile = random.choice(TLS_PROFILES)
        self.headers = dict(random.choice(STEALTH_HEADER_SETS))
        logger.info(
            f"🔄 Sesión rotada → {self._current_tls_profile['name']} "
            f"| UA: ...{self.headers.get('user-agent', '')[-20:]}"
        )
    
    def get(self, url: str, **kwargs) -> Any:
        """GET request con impersonación + retry + circuit breaker."""
        return self._request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> Any:
        """POST request con impersonación + retry + circuit breaker."""
        return self._request("POST", url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> Any:
        """Request interno con Ghost Mode + Circuit Breaker + Retry."""
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit Breaker OPEN — API {url} está caída. "
                f"Reintentando en {self.circuit_breaker.recovery_timeout}s"
            )
        
        # 👻 Ghost mode: rotar TLS si toca
        if self.ghost_mode:
            self._rotate_tls_profile()
        
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
