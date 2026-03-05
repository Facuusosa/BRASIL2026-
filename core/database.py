"""
🗄️ Database — SQLite Wrapper Compartido

Extraído de:
- python-performance-optimization skill (batch DB operations con executemany)
- python-testing-patterns skill (fixtures con SQLite in-memory)
- systematic-debugging skill (logging en cada frontera)

Uso:
    from core.database import Database
    
    db = Database("monitor.db")
    db.save_products(products)
    cheapest = db.get_cheapest_by_category("celulares", limit=10)
"""

from __future__ import annotations

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Database:
    """
    SQLite wrapper con operaciones batch optimizadas.
    
    Features:
    - executemany para inserts masivos (hasta 100x más rápido que individual)
    - Context manager para transacciones seguras
    - Queries pre-armadas para operaciones comunes de precio
    - Compatible con in-memory DB para testing
    """
    
    def __init__(self, db_path: str = "monitor.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Crear tablas si no existen."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    brand TEXT DEFAULT '',
                    current_price REAL NOT NULL,
                    list_price REAL DEFAULT 0,
                    discount_pct REAL DEFAULT 0,
                    url TEXT DEFAULT '',
                    image_url TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    source TEXT NOT NULL,
                    in_stock INTEGER DEFAULT 1,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(product_id, source, scraped_at)
                );
                
                CREATE TABLE IF NOT EXISTS glitches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    current_price REAL NOT NULL,
                    list_price REAL DEFAULT 0,
                    previous_price REAL DEFAULT 0,
                    drop_pct REAL DEFAULT 0,
                    reason TEXT DEFAULT '',
                    severity TEXT DEFAULT 'medium',
                    source TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    price REAL NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_products_source 
                    ON products(source);
                CREATE INDEX IF NOT EXISTS idx_products_category 
                    ON products(category);
                CREATE INDEX IF NOT EXISTS idx_products_price 
                    ON products(current_price);
                CREATE INDEX IF NOT EXISTS idx_price_history_product 
                    ON price_history(product_id, source);
                CREATE INDEX IF NOT EXISTS idx_glitches_severity 
                    ON glitches(severity);
            """)
            logger.info(f"✅ Database inicializada: {self.db_path}")
    
    @contextmanager
    def _connect(self):
        """Context manager para conexiones seguras."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ========================================================================
    # WRITE OPERATIONS
    # Ref: python-performance-optimization — executemany para batch inserts
    # ========================================================================
    
    def save_products(self, products: list[Any]) -> int:
        """
        Guardar productos en batch (hasta 100x más rápido que individual).
        
        Args:
            products: Lista de Product dataclasses
            
        Returns:
            Cantidad de productos guardados
        """
        if not products:
            return 0
        
        data = [
            (
                p.id, p.name, p.brand, p.current_price, p.list_price,
                p.discount_pct, p.url, p.image_url, p.category, p.source,
                p.in_stock, p.scraped_at.isoformat() if hasattr(p.scraped_at, 'isoformat') 
                else str(p.scraped_at)
            )
            for p in products
        ]
        
        with self._connect() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO products 
                (product_id, name, brand, current_price, list_price,
                 discount_pct, url, image_url, category, source,
                 in_stock, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            
            # También guardar en historial de precios
            price_data = [
                (p.id, p.source, p.current_price,
                 p.scraped_at.isoformat() if hasattr(p.scraped_at, 'isoformat')
                 else str(p.scraped_at))
                for p in products
            ]
            conn.executemany("""
                INSERT INTO price_history (product_id, source, price, recorded_at)
                VALUES (?, ?, ?, ?)
            """, price_data)
        
        logger.info(f"💾 {len(data)} productos guardados en {self.db_path}")
        return len(data)
    
    def save_glitch(self, glitch: Any) -> None:
        """Guardar un glitch detectado."""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO glitches 
                (product_id, product_name, current_price, list_price,
                 previous_price, drop_pct, reason, severity, source, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                glitch.product.id, glitch.product.name,
                glitch.product.current_price, glitch.product.list_price,
                glitch.previous_price, glitch.drop_pct,
                glitch.reason, glitch.severity,
                glitch.product.source, glitch.product.category,
            ))
    
    # ========================================================================
    # READ OPERATIONS — Queries para análisis de precios
    # ========================================================================
    
    def get_cheapest_by_category(
        self, category: str, source: Optional[str] = None, limit: int = 10
    ) -> list[dict]:
        """Los N productos más baratos de una categoría."""
        query = """
            SELECT product_id, name, brand, current_price, list_price,
                   discount_pct, url, source, scraped_at
            FROM products
            WHERE category = ? AND current_price > 0
        """
        params: list[Any] = [category]
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY current_price ASC LIMIT ?"
        params.append(limit)
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def get_biggest_discounts(
        self, min_discount: float = 20.0, limit: int = 20
    ) -> list[dict]:
        """Productos con mayor descuento (oportunidades de reventa)."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT product_id, name, brand, current_price, list_price,
                       ROUND((1 - current_price / list_price) * 100, 1) as real_discount,
                       ROUND(list_price - current_price, 0) as savings,
                       url, source, category
                FROM products
                WHERE list_price > 0 AND current_price > 0 
                      AND current_price < list_price
                      AND ((1 - current_price / list_price) * 100) >= ?
                ORDER BY real_discount DESC
                LIMIT ?
            """, (min_discount, limit)).fetchall()
            return [dict(row) for row in rows]
    
    def compare_prices_across_sources(self, product_name_like: str) -> list[dict]:
        """
        Comparar precios del mismo producto en diferentes tiendas.
        
        Ejemplo:
            results = db.compare_prices_across_sources("%iPhone 15%")
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT name, source, MIN(current_price) as best_price,
                       MAX(current_price) as worst_price,
                       COUNT(*) as times_seen
                FROM products
                WHERE name LIKE ? AND current_price > 0
                GROUP BY name, source
                ORDER BY name, best_price ASC
            """, (product_name_like,)).fetchall()
            return [dict(row) for row in rows]
    
    def get_price_history(self, product_id: str, source: str) -> list[dict]:
        """Historial de precios de un producto específico."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT price, recorded_at
                FROM price_history
                WHERE product_id = ? AND source = ?
                ORDER BY recorded_at DESC
                LIMIT 100
            """, (product_id, source)).fetchall()
            return [dict(row) for row in rows]
    
    def get_previous_price(self, product_id: str, source: str) -> Optional[float]:
        """Obtener el precio anterior de un producto (para detectar caídas)."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT price FROM price_history
                WHERE product_id = ? AND source = ?
                ORDER BY recorded_at DESC
                LIMIT 1 OFFSET 1
            """, (product_id, source)).fetchone()
            return row["price"] if row else None
    
    def get_recent_glitches(self, hours: int = 24, limit: int = 50) -> list[dict]:
        """Glitches detectados en las últimas N horas."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM glitches
                WHERE detected_at >= datetime('now', ?)
                ORDER BY detected_at DESC
                LIMIT ?
            """, (f"-{hours} hours", limit)).fetchall()
            return [dict(row) for row in rows]
    
    def get_stats(self) -> dict:
        """Estadísticas generales de la base de datos."""
        with self._connect() as conn:
            stats = {}
            stats["total_products"] = conn.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0]
            stats["total_glitches"] = conn.execute(
                "SELECT COUNT(*) FROM glitches"
            ).fetchone()[0]
            stats["total_price_records"] = conn.execute(
                "SELECT COUNT(*) FROM price_history"
            ).fetchone()[0]
            stats["sources"] = [
                row[0] for row in 
                conn.execute("SELECT DISTINCT source FROM products").fetchall()
            ]
            stats["categories"] = [
                row[0] for row in 
                conn.execute("SELECT DISTINCT category FROM products").fetchall()
            ]
            return stats
