"""
🏗️ Base Sniffer — Clase Abstracta para Todos los Scrapers

Extraído de:
- architecture-patterns skill (Clean Architecture + interfaces)
- systematic-debugging skill (Multi-Layer Diagnostic)
- verification-before-completion skill (evidencia de funcionamiento)

TODO scraper de e-commerce (Frávega, Garbarino, MeLi) DEBE heredar de esta clase.

Ejemplo:
    class FravegaSniffer(BaseSniffer):
        TARGET_NAME = "fravega"
        BASE_URL = "https://www.fravega.com"
        API_URL = "https://www.fravega.com/api/graphql"
        
        def fetch_products(self, category: str) -> list[dict]:
            ...
        
        def parse_product(self, raw: dict) -> Product:
            ...
        
        def detect_glitch(self, product: Product) -> Optional[Glitch]:
            ...
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS — Estructuras de datos del dominio
# Ref: architecture-patterns skill (DDD: Value Objects + Entities)
# ============================================================================

@dataclass
class Product:
    """
    Producto normalizado. Misma estructura sin importar el target.
    Esto permite comparar un iPhone de Frávega vs uno de Garbarino.
    """
    id: str                          # ID interno del target
    name: str                        # Nombre del producto
    brand: str = ""                  # Marca
    current_price: float = 0.0       # Precio actual (oferta si hay)
    list_price: float = 0.0          # Precio de lista (sin oferta)
    discount_pct: float = 0.0        # % de descuento
    url: str = ""                    # URL del producto
    image_url: str = ""              # URL de la imagen principal
    category: str = ""               # Categoría (e.g., "celulares")
    source: str = ""                 # Target de origen (e.g., "fravega")
    in_stock: bool = True            # Disponibilidad
    scraped_at: datetime = field(default_factory=datetime.now)
    raw_data: dict = field(default_factory=dict)  # Data original sin procesar
    
    @property
    def has_discount(self) -> bool:
        return self.discount_pct > 0 or (
            self.list_price > 0 and self.current_price < self.list_price
        )
    
    @property
    def calculated_discount(self) -> float:
        """Calcular % descuento real basado en precios."""
        if self.list_price > 0 and self.current_price > 0:
            return round((1 - self.current_price / self.list_price) * 100, 1)
        return self.discount_pct
    
    @property
    def margin_potential(self) -> float:
        """Potencial de margen si el precio de lista es el precio de mercado."""
        if self.list_price > 0 and self.current_price > 0:
            return round(self.list_price - self.current_price, 2)
        return 0.0


@dataclass
class Glitch:
    """
    Glitch de precio detectado.
    Un glitch es una anomalía: precio inusualmente bajo que puede ser
    un error del vendedor (oportunidad de compra).
    """
    product: Product
    reason: str                      # Por qué se considera glitch
    severity: str = "medium"         # low, medium, high, critical
    previous_price: float = 0.0      # Precio anterior (si se conoce)
    drop_pct: float = 0.0            # % de caída
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class ScrapeResult:
    """Resultado de un ciclo de scraping."""
    target_name: str
    category: str
    products_found: int = 0
    glitches_found: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)
    products: list[Product] = field(default_factory=list)
    glitches: list[Glitch] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.products_found > 0


# ============================================================================
# BASE SNIFFER — Clase Abstracta
# ============================================================================

class BaseSniffer(ABC):
    """
    Clase base para todos los scrapers de e-commerce.
    
    Implementa el patrón Template Method:
    1. fetch_products()    → Obtener datos crudos del target
    2. parse_product()     → Normalizar un producto crudo → Product
    3. detect_glitch()     → Verificar si un producto tiene precio anómalo
    4. on_glitch_found()   → Hook para acciones al encontrar un glitch
    5. save_products()     → Persistir productos en DB
    
    El método run_cycle() orquesta todo el flujo.
    """
    
    # Subclases DEBEN definir estos
    TARGET_NAME: str = ""
    BASE_URL: str = ""
    API_URL: str = ""
    
    # Umbrales de detección de glitches
    GLITCH_THRESHOLD_PCT: float = 40.0   # >40% descuento = sospechoso
    GLITCH_ABS_MIN: float = 1000.0       # Precio < $1000 ARS = sospechoso
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or f"{self.TARGET_NAME}_monitor.db"
        self.logger = logging.getLogger(f"sniffer.{self.TARGET_NAME}")
    
    # --- Métodos abstractos (DEBEN ser implementados) ---
    
    @abstractmethod
    def fetch_products(self, category: str, **kwargs) -> list[dict]:
        """
        Obtener productos crudos del target.
        Retorna lista de dicts con la data raw del API/HTML.
        """
        ...
    
    @abstractmethod
    def parse_product(self, raw: dict) -> Product:
        """
        Convertir un producto raw (del API) a nuestro formato Product.
        DEBE manejar campos faltantes sin explotar.
        """
        ...
    
    # --- Métodos con implementación default (pueden sobreescribirse) ---
    
    def detect_glitch(self, product: Product, previous_price: float = 0.0) -> Optional[Glitch]:
        """
        Detectar si un producto tiene un precio anómalo (glitch).
        
        Heurísticas:
        1. Descuento > GLITCH_THRESHOLD_PCT → probable glitch
        2. Precio < GLITCH_ABS_MIN → demasiado barato
        3. Caída > 50% vs precio anterior → cambio brusco
        """
        # Heurística 1: Descuento excesivo vs precio de lista
        if product.list_price > 0:
            discount = product.calculated_discount
            if discount >= self.GLITCH_THRESHOLD_PCT:
                return Glitch(
                    product=product,
                    reason=f"Descuento extremo: {discount}% off (lista: ${product.list_price:,.0f})",
                    severity="high" if discount >= 60 else "medium",
                    drop_pct=discount,
                )
        
        # Heurística 2: Precio absurdamente bajo
        if 0 < product.current_price < self.GLITCH_ABS_MIN:
            return Glitch(
                product=product,
                reason=f"Precio sospechosamente bajo: ${product.current_price:,.0f}",
                severity="critical",
            )
        
        # Heurística 3: Caída brusca vs precio anterior
        if previous_price > 0 and product.current_price > 0:
            drop = (1 - product.current_price / previous_price) * 100
            if drop >= 50:
                return Glitch(
                    product=product,
                    reason=f"Caída del {drop:.0f}% vs precio anterior (${previous_price:,.0f})",
                    severity="high",
                    previous_price=previous_price,
                    drop_pct=drop,
                )
        
        return None
    
    def on_glitch_found(self, glitch: Glitch) -> None:
        """
        Hook: se llama cuando se detecta un glitch.
        Override para enviar notificaciones (Telegram, Discord, etc.)
        """
        self.logger.warning(
            f"🚨 GLITCH [{glitch.severity.upper()}] en {self.TARGET_NAME}: "
            f"{glitch.product.name} — ${glitch.product.current_price:,.0f} "
            f"({glitch.reason})"
        )
    
    def save_products(self, products: list[Product]) -> None:
        """
        Persistir productos en la base de datos.
        Override para implementar.
        """
        self.logger.info(
            f"💾 {len(products)} productos para guardar (DB: {self.db_path})"
        )
    
    # --- Orquestación ---
    
    def run_cycle(self, categories: list[str], **kwargs) -> list[ScrapeResult]:
        """
        Ejecutar un ciclo completo de scraping.
        
        Ref: systematic-debugging — Multi-Layer Diagnostic
        Logs en cada frontera: fetch → parse → detect → save
        
        Ejemplo:
            sniffer = FravegaSniffer()
            results = sniffer.run_cycle(["celulares", "notebooks", "tvs"])
            for r in results:
                print(f"{r.category}: {r.products_found} productos, {r.glitches_found} glitches")
        """
        results = []
        
        for category in categories:
            start = time.time()
            result = ScrapeResult(
                target_name=self.TARGET_NAME,
                category=category,
            )
            
            try:
                # PASO 1: Fetch
                self.logger.info(f"📡 Fetching {self.TARGET_NAME}/{category}...")
                raw_products = self.fetch_products(category, **kwargs)
                self.logger.info(f"   → {len(raw_products)} productos raw")
                
                # PASO 2: Parse
                products = []
                for raw in raw_products:
                    try:
                        product = self.parse_product(raw)
                        product.source = self.TARGET_NAME
                        product.category = category
                        products.append(product)
                    except Exception as e:
                        self.logger.error(f"   ❌ Error parseando producto: {e}")
                        result.errors.append(f"Parse error: {e}")
                
                result.products = products
                result.products_found = len(products)
                self.logger.info(f"   → {len(products)} productos parseados")
                
                # PASO 3: Detect glitches
                for product in products:
                    glitch = self.detect_glitch(product)
                    if glitch:
                        result.glitches.append(glitch)
                        self.on_glitch_found(glitch)
                
                result.glitches_found = len(result.glitches)
                
                # PASO 4: Save
                if products:
                    self.save_products(products)
                
            except Exception as e:
                self.logger.error(f"💥 Error en ciclo {category}: {e}")
                result.errors.append(str(e))
            
            result.duration_seconds = round(time.time() - start, 2)
            results.append(result)
            
            self.logger.info(
                f"   ✅ {category}: {result.products_found} productos, "
                f"{result.glitches_found} glitches, {result.duration_seconds}s"
            )
        
        return results
    
    def run_forever(self, categories: list[str], interval: int = 60, **kwargs) -> None:
        """
        Ejecutar ciclos de scraping indefinidamente.
        
        Args:
            categories: Lista de categorías a scrapear
            interval: Segundos entre ciclos
        """
        cycle = 0
        while True:
            cycle += 1
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"🔄 Ciclo #{cycle} — {datetime.now().strftime('%H:%M:%S')}")
            self.logger.info(f"{'='*60}")
            
            results = self.run_cycle(categories, **kwargs)
            
            total_products = sum(r.products_found for r in results)
            total_glitches = sum(r.glitches_found for r in results)
            total_errors = sum(len(r.errors) for r in results)
            
            self.logger.info(
                f"\n📊 Resumen ciclo #{cycle}: "
                f"{total_products} productos, {total_glitches} glitches, "
                f"{total_errors} errores"
            )
            
            self.logger.info(f"⏳ Esperando {interval}s...")
            time.sleep(interval)
