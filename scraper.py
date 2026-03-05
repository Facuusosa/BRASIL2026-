"""
✈️ BRASIL2026 — Flight Tracker Optimizado
Integra: Amadeus API + Flybondi scraping stealth + SQLite + Dashboard + Alertas

Basado en la arquitectura Odiseo (proyectos vuelos/ y FRAVEGA/)
"""

import os
import sys
import json
import sqlite3
import requests
import datetime
import webbrowser
import re
import random
import time
from dotenv import load_dotenv
from amadeus import Client, ResponseError

# ─── CONFIGURACIÓN ──────────────────────────────────────────────────────────

load_dotenv()
DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "brasil2026.db")
DASHBOARD_FILE = "dashboard.html"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Amadeus — por defecto usa TEST. Para producción: hostname='production'
amadeus = Client(
    client_id=os.getenv("AMADEUS_CLIENT_ID"),
    client_secret=os.getenv("AMADEUS_CLIENT_SECRET")
)

DESTINOS = {
    "FLN": "Florianópolis",
    "GIG": "Río de Janeiro",
    "SSA": "Salvador de Bahía",
    "BPS": "Porto Seguro",
    "NAT": "Natal",
    "MCZ": "Maceió",
    "REC": "Recife",
    "FOR": "Fortaleza",
}

ORIGENES = ["EZE", "AEP"]  # Multi-aeropuerto: Ezeiza + Aeroparque

# 4 combinaciones de fechas (siempre 7 noches)
FECHAS = [
    ("2026-04-06", "2026-04-13"),
    ("2026-04-07", "2026-04-14"),
    ("2026-04-08", "2026-04-15"),
    ("2026-04-09", "2026-04-16"),
]

ADULTOS = 2

# Nombres de días para mostrar en el dashboard
DIAS_ES = {0:'lun',1:'mar',2:'mié',3:'jue',4:'vie',5:'sáb',6:'dom'}
def fecha_bonita(fecha_str):
    """'2026-04-06' → 'lun 6 abr'"""
    from datetime import date
    MESES = {1:'ene',2:'feb',3:'mar',4:'abr',5:'may',6:'jun',7:'jul',8:'ago',9:'sep',10:'oct',11:'nov',12:'dic'}
    d = date.fromisoformat(fecha_str)
    return f"{DIAS_ES[d.weekday()]} {d.day} {MESES[d.month]}"


# ─── STEALTH UTILITIES ────────────────────────────────────────────────────────────

def pre_flight_check():
    """
    🛡️ Verificación pre-vuelo: muestra la IP actual y advierte si hay riesgo.
    Usa api.ipify.org para obtener la IP pública.
    """
    print("\n  🛡️ PRE-FLIGHT CHECK")
    print("  " + "─" * 45)
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        ip = r.json().get("ip", "desconocida")
        print(f"  🌐 IP pública actual: {ip}")
        
        # Verificar si es IP de datacenter conocido (heurística básica)
        dc_prefixes = ["34.", "35.", "104.", "142.", "172.217.", "20.", "52.", "54."]
        is_dc = any(ip.startswith(p) for p in dc_prefixes)
        if is_dc:
            print("  ⚠️  ADVERTENCIA: Tu IP parece de datacenter/VPN.")
            print("  ⚠️  Recomendación: Desconectá la VPN y usá tu IP residencial.")
        else:
            print("  ✅ IP residencial detectada — perfil bajo")
        
        return ip
    except Exception as e:
        print(f"  ⚠️ No se pudo verificar IP: {e}")
        return None


def human_delay(min_sec=2.0, max_sec=5.0):
    """
    👻 Delay humano entre búsquedas.
    Simula el tiempo que un usuario real tardaría entre una búsqueda y otra.
    """
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


# ─── BASE DE DATOS ──────────────────────────────────────────────────────────

def init_db():
    """Inicializa la base de datos SQLite."""
    conn = sqlite3.connect(DB_FILE)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vuelos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destino TEXT NOT NULL,
            destino_nombre TEXT DEFAULT '',
            origen TEXT DEFAULT 'EZE',
            aerolinea TEXT NOT NULL,
            aerolinea_nombre TEXT DEFAULT '',
            precio_usd REAL NOT NULL,
            precio_ars REAL NOT NULL,
            duracion_ida TEXT DEFAULT '',
            duracion_vuelta TEXT DEFAULT '',
            escalas_ida INTEGER DEFAULT 0,
            escalas_vuelta INTEGER DEFAULT 0,
            es_directo INTEGER DEFAULT 0,
            segmentos_ida TEXT DEFAULT '',
            segmentos_vuelta TEXT DEFAULT '',
            hora_salida TEXT DEFAULT '',
            hora_llegada TEXT DEFAULT '',
            fecha_ida TEXT DEFAULT '',
            fecha_vuelta TEXT DEFAULT '',
            fuente TEXT DEFAULT 'amadeus',
            timestamp TEXT NOT NULL,
            UNIQUE(destino, origen, aerolinea, precio_usd, duracion_ida, fecha_ida, timestamp)
        );

        CREATE TABLE IF NOT EXISTS historial_precio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destino TEXT NOT NULL,
            precio_min_usd REAL NOT NULL,
            precio_min_ars REAL NOT NULL,
            aerolinea TEXT DEFAULT '',
            tipo_cambio REAL DEFAULT 0,
            timestamp TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destino TEXT NOT NULL,
            precio_anterior_usd REAL,
            precio_nuevo_usd REAL,
            variacion_pct REAL,
            mensaje TEXT,
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_vuelos_destino ON vuelos(destino);
        CREATE INDEX IF NOT EXISTS idx_vuelos_precio ON vuelos(precio_usd);
        CREATE INDEX IF NOT EXISTS idx_vuelos_timestamp ON vuelos(timestamp);
        CREATE INDEX IF NOT EXISTS idx_historial_destino ON historial_precio(destino);
    """)
    # Migración: agregar columnas fecha_ida/fecha_vuelta si no existen (DB vieja)
    try:
        conn.execute("SELECT fecha_ida FROM vuelos LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE vuelos ADD COLUMN fecha_ida TEXT DEFAULT ''")
        conn.execute("ALTER TABLE vuelos ADD COLUMN fecha_vuelta TEXT DEFAULT ''")
        conn.commit()
    conn.close()


def get_previous_best_prices():
    """Obtiene los mejores precios anteriores por destino."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT destino, MIN(precio_min_usd) as mejor_precio
        FROM historial_precio
        GROUP BY destino
    """).fetchall()
    conn.close()
    return {row['destino']: row['mejor_precio'] for row in rows}


def get_last_prices():
    """Obtiene los precios de la última búsqueda por destino."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT destino, precio_min_usd
        FROM historial_precio
        WHERE timestamp = (SELECT MAX(timestamp) FROM historial_precio)
    """).fetchall()
    conn.close()
    return {row['destino']: row['precio_min_usd'] for row in rows}


def save_vuelos(vuelos, timestamp):
    """Guarda vuelos en la base de datos (batch insert con dedup)."""
    conn = sqlite3.connect(DB_FILE)
    for v in vuelos:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO vuelos 
                (destino, destino_nombre, origen, aerolinea, aerolinea_nombre,
                 precio_usd, precio_ars, duracion_ida, duracion_vuelta,
                 escalas_ida, escalas_vuelta, es_directo,
                 segmentos_ida, segmentos_vuelta,
                 hora_salida, hora_llegada, fecha_ida, fecha_vuelta, fuente, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                v['destino'], v['destino_nombre'], v['origen'],
                v['aerolinea'], v.get('aerolinea_nombre', ''),
                v['precio_usd'], v['precio_ars'],
                v.get('duracion_ida', ''), v.get('duracion_vuelta', ''),
                v.get('escalas_ida', 0), v.get('escalas_vuelta', 0),
                v.get('es_directo', 0),
                v.get('segmentos_ida', ''), v.get('segmentos_vuelta', ''),
                v.get('hora_salida', ''), v.get('hora_llegada', ''),
                v.get('fecha_ida', ''), v.get('fecha_vuelta', ''),
                v.get('fuente', 'amadeus'), timestamp
            ))
        except Exception as e:
            pass  # Duplicados se ignoran
    conn.commit()
    conn.close()


def save_historial(precios_por_destino, tipo_cambio, timestamp):
    """Guarda el precio mínimo por destino en el historial."""
    conn = sqlite3.connect(DB_FILE)
    for destino, data in precios_por_destino.items():
        conn.execute("""
            INSERT INTO historial_precio 
            (destino, precio_min_usd, precio_min_ars, aerolinea, tipo_cambio, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (destino, data['precio_usd'], data['precio_ars'],
              data['aerolinea'], tipo_cambio, timestamp))
    conn.commit()
    conn.close()


def save_alerta(destino, precio_ant, precio_nuevo, timestamp):
    """Guarda una alerta de cambio de precio."""
    variacion = ((precio_nuevo - precio_ant) / precio_ant) * 100
    if abs(variacion) < 1:
        return  # No alertar por cambios menores al 1%
    
    direccion = "📉 BAJÓ" if variacion < 0 else "📈 Subió"
    mensaje = f"{direccion} {abs(variacion):.1f}% | {DESTINOS.get(destino, destino)}: USD {precio_ant:.0f} → USD {precio_nuevo:.0f}"
    
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO alertas (destino, precio_anterior_usd, precio_nuevo_usd, variacion_pct, mensaje, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (destino, precio_ant, precio_nuevo, variacion, mensaje, timestamp))
    conn.commit()
    conn.close()
    
    print(f"  🔔 ALERTA: {mensaje}")


def get_historial_completo():
    """Obtiene todo el historial para el gráfico."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT destino, precio_min_usd, precio_min_ars, timestamp 
        FROM historial_precio 
        ORDER BY timestamp ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alertas_recientes(limit=20):
    """Obtiene las alertas más recientes."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM alertas ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── UTILIDADES ─────────────────────────────────────────────────────────────

AEROLINEAS = {
    "AR": "Aerolíneas Argentinas", "G3": "GOL", "JA": "JetSmart",
    "FO": "Flybondi", "LA": "LATAM", "CM": "Copa Airlines",
    "AV": "Avianca", "EK": "Emirates", "ET": "Ethiopian Airlines",
    "TK": "Turkish Airlines", "AA": "American Airlines",
    "UA": "United Airlines", "DL": "Delta", "IB": "Iberia",
    "AF": "Air France", "KL": "KLM", "LH": "Lufthansa",
    "AZ": "ITA Airways", "TP": "TAP Portugal",
}


def get_exchange_rate():
    """Obtiene el tipo de cambio USD → ARS desde AwesomeAPI."""
    try:
        r = requests.get("https://economia.awesomeapi.com.br/json/last/USD-ARS", timeout=10)
        return float(r.json()["USDARS"]["bid"])
    except Exception as e:
        print(f"  ⚠️ Error tipo de cambio: {e} — usando fallback 1400")
        return 1400.0


def formatear_duracion(duracion_iso):
    """PT3H45M → '3h 45m'"""
    if not duracion_iso:
        return ""
    duracion = duracion_iso.replace("PT", "")
    horas, minutos = 0, 0
    if "H" in duracion:
        partes = duracion.split("H")
        horas = int(partes[0])
        duracion = partes[1] if len(partes) > 1 else ""
    if "M" in duracion:
        minutos = int(duracion.replace("M", ""))
    if horas > 0 and minutos > 0:
        return f"{horas}h {minutos}m"
    elif horas > 0:
        return f"{horas}h"
    return f"{minutos}m"


def formatear_hora(fecha_iso):
    """2026-04-06T21:30:00 → '21:30'"""
    if not fecha_iso:
        return ""
    try:
        return fecha_iso.split("T")[1][:5]
    except:
        return ""


def extraer_detalles_vuelo(offer):
    """Extrae info detallada de un offer de Amadeus."""
    itinerarios = offer.get('itineraries', [])
    if len(itinerarios) < 2:
        return {}
    
    ida = itinerarios[0]
    vuelta = itinerarios[1]
    
    # Segmentos ida
    seg_ida = ida.get('segments', [])
    seg_vuelta = vuelta.get('segments', [])
    
    escalas_ida = len(seg_ida) - 1
    escalas_vuelta = len(seg_vuelta) - 1
    es_directo = (escalas_ida == 0 and escalas_vuelta == 0)
    
    # Formatear segmentos como texto legible
    def fmt_segmentos(segs):
        parts = []
        for s in segs:
            dep = s['departure']['iataCode']
            arr = s['arrival']['iataCode']
            carrier = s.get('carrierCode', '??')
            num = s.get('number', '')
            dur = formatear_duracion(s.get('duration', ''))
            parts.append(f"{dep}→{arr} ({carrier}{num}, {dur})")
        return " | ".join(parts)
    
    hora_salida = formatear_hora(seg_ida[0]['departure'].get('at', '')) if seg_ida else ''
    hora_llegada = formatear_hora(seg_ida[-1]['arrival'].get('at', '')) if seg_ida else ''
    
    return {
        'duracion_ida': formatear_duracion(ida.get('duration', '')),
        'duracion_vuelta': formatear_duracion(vuelta.get('duration', '')),
        'escalas_ida': escalas_ida,
        'escalas_vuelta': escalas_vuelta,
        'es_directo': 1 if es_directo else 0,
        'segmentos_ida': fmt_segmentos(seg_ida),
        'segmentos_vuelta': fmt_segmentos(seg_vuelta),
        'hora_salida': hora_salida,
        'hora_llegada': hora_llegada,
    }


# ─── BÚSQUEDA AMADEUS ──────────────────────────────────────────────────────

def buscar_amadeus(usd_to_ars, timestamp):
    """Busca vuelos en Amadeus para todos los orígenes, destinos y fechas."""
    vuelos = []
    total_combos = len(ORIGENES) * len(DESTINOS) * len(FECHAS)
    combo_n = 0
    
    for fecha_ida, fecha_vuelta in FECHAS:
        print(f"\n  📅 Fechas: {fecha_ida} → {fecha_vuelta}")
        for origen in ORIGENES:
            for code, nombre in DESTINOS.items():
                combo_n += 1
                print(f"  🔍 [{combo_n}/{total_combos}] {origen} → {code} ({nombre})...", end=" ", flush=True)
                try:
                    response = amadeus.shopping.flight_offers_search.get(
                        originLocationCode=origen,
                        destinationLocationCode=code,
                        departureDate=fecha_ida,
                        returnDate=fecha_vuelta,
                        adults=ADULTOS,
                        currencyCode='USD',
                        max=10
                    )
                    
                    seen = set()  # Deduplicar
                    count = 0
                    
                    for offer in response.data:
                        precio_usd = float(offer['price']['total'])
                        aerolinea = offer['validatingAirlineCodes'][0]
                        detalles = extraer_detalles_vuelo(offer)
                        
                        # Key de dedup: destino + aerolinea + precio + duración + fechas
                        dedup_key = f"{code}-{aerolinea}-{precio_usd}-{detalles.get('duracion_ida','')}-{fecha_ida}"
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)
                        
                        vuelo = {
                            'destino': code,
                            'destino_nombre': nombre,
                            'origen': origen,
                            'aerolinea': aerolinea,
                            'aerolinea_nombre': AEROLINEAS.get(aerolinea, aerolinea),
                            'precio_usd': precio_usd,
                            'precio_ars': round(precio_usd * usd_to_ars, 2),
                            'fecha_ida': fecha_ida,
                            'fecha_vuelta': fecha_vuelta,
                            'fecha_ida_bonita': fecha_bonita(fecha_ida),
                            'fecha_vuelta_bonita': fecha_bonita(fecha_vuelta),
                            'fuente': 'amadeus',
                            **detalles
                        }
                        vuelos.append(vuelo)
                        count += 1
                    
                    print(f"✅ {count} vuelos")
                    
                except ResponseError as e:
                    print(f"❌ {e}")
                except Exception as e:
                    print(f"❌ {e}")
                
                # 👻 Delay humano entre búsquedas a Amadeus
                human_delay(1.0, 3.0)
    
    return vuelos


# ─── BÚSQUEDA FLYBONDI (Stealth) ───────────────────────────────────────────

def buscar_flybondi(usd_to_ars, timestamp):
    """
    Busca vuelos en Flybondi usando scraping stealth (Ghost Mode).
    Estrategia de extracción en cascada:
      1. window.__INITIAL_STATE__ (script tags) — más estable
      2. Regex de precios (US$ / $ + números)
      3. Detección de secciones ida/vuelta
      4. Failsafe: dump de <body> para debug
    """
    vuelos = []
    
    try:
        from core.http_client import HttpClient
    except ImportError:
        print("  ⚠️ curl_cffi no disponible — omitiendo Flybondi")
        return vuelos
    
    import re
    import json as json_mod
    import uuid
    
    client = HttpClient(
        ghost_mode=True,
        retry_count=2,
        extra_headers={
            "Origin": "https://flybondi.com",
            "Referer": "https://flybondi.com/",
        }
    )
    
    flybondi_destinos = ["FLN"]
    total_encontrados = 0
    errores_red = 0
    
    # ── Funciones auxiliares de extracción ──

    def _extraer_precios_initial_state(html):
        """Estrategia 1: Buscar window.__INITIAL_STATE__ en script tags."""
        found = []
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>',
            r'window\.__INITIAL_STATE__\s*=\s*JSON\.parse\([\'"](.+?)[\'"]\)',
            r'"flights"\s*:\s*(\[.*?\])\s*[,}]',
            r'"outbound"\s*:\s*(\[.*?\])\s*[,}]',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for m in matches:
                try:
                    data = json_mod.loads(m)
                    if isinstance(data, dict):
                        for key in ['flights', 'outbound', 'results', 'journeys', 'fares']:
                            if key in data and isinstance(data[key], list):
                                found.extend(data[key])
                        if 'search' in data and isinstance(data['search'], dict):
                            sr = data['search']
                            for key in ['results', 'flights', 'journeys']:
                                if key in sr and isinstance(sr[key], list):
                                    found.extend(sr[key])
                    elif isinstance(data, list):
                        found.extend(data)
                except (json_mod.JSONDecodeError, TypeError):
                    continue
        return found

    def _extraer_precios_regex(html):
        """Estrategia 2: Buscar patrones de precio US$/$ + números."""
        precios = []
        patterns = [
            r'US\$\s*([0-9.,]+)',
            r'USD\s*([0-9.,]+)',
            r'\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                cleaned = m.replace('.', '').replace(',', '.')
                try:
                    val = float(cleaned)
                    if 5 < val < 500000:
                        precios.append(val)
                except ValueError:
                    continue
        return sorted(set(precios))

    def _detectar_seccion_ida_vuelta(html):
        """Estrategia 3: Separar precios de ida y vuelta por contexto."""
        ida_section = ''
        vuelta_section = ''
        ida_markers = ['Elegí tu vuelo de ida', 'vuelo de ida', 'Outbound', 'IDA']
        vuelta_markers = ['Elegí tu vuelo de vuelta', 'vuelo de vuelta', 'Return', 'VUELTA']
        for marker in ida_markers:
            idx = html.find(marker)
            if idx >= 0:
                for vm in vuelta_markers:
                    vidx = html.find(vm, idx)
                    if vidx >= 0:
                        ida_section = html[idx:vidx]
                        vuelta_section = html[vidx:vidx + len(ida_section)]
                        break
                if not ida_section:
                    ida_section = html[idx:idx + 5000]
                break
        result = {'ida': [], 'vuelta': []}
        if ida_section:
            result['ida'] = _extraer_precios_regex(ida_section)
        if vuelta_section:
            result['vuelta'] = _extraer_precios_regex(vuelta_section)
        return result

    # ── Loop principal ──

    for fecha_ida, fecha_vuelta in FECHAS:
        for dest in flybondi_destinos:
            print(f"  🔍 Flybondi BUE → {dest} ({fecha_ida})...", end=" ", flush=True)
            try:
                client.warm_session("https://flybondi.com")
                
                search_url = (
                    f"https://flybondi.com/ar/search/results"
                    f"?adults={ADULTOS}&children=0&infants=0"
                    f"&currency=USD"
                    f"&departureDate={fecha_ida}&returnDate={fecha_vuelta}"
                    f"&fromCityCode=BUE&toCityCode={dest}"
                    f"&utm_origin=search_bar"
                )
                
                session_id = f"SFO-{uuid.uuid4()}"
                r = client.get(
                    search_url, timeout=20,
                    cookies={"FBSessionX-ar-ibe": session_id}
                )
                
                if r.status_code == 200:
                    html_text = r.text
                    html_len = len(html_text)
                    has_title = 'Elegí tu vuelo' in html_text
                    
                    if html_len < 5000:
                        print(f"⚠️ Respuesta corta ({html_len} bytes) — posible bloqueo")
                        errores_red += 1
                        continue
                    
                    if not has_title and html_len < 50000:
                        print(f"⚠️ HTML inesperado ({html_len//1024} KB)")
                        errores_red += 1
                        continue
                    
                    print(f"✅ SPA OK ({html_len//1024} KB)", end="")
                    
                    # ── ESTRATEGIA 1: __INITIAL_STATE__ ──
                    state_flights = _extraer_precios_initial_state(html_text)
                    if state_flights:
                        print(f" — {len(state_flights)} vuelos vía __INITIAL_STATE__")
                        for flight in state_flights:
                            if not isinstance(flight, dict):
                                continue
                            precio_raw = None
                            for pk in ['price', 'fare', 'amount', 'total', 'lowestFare', 'basePrice']:
                                val = flight.get(pk)
                                if val is not None:
                                    try:
                                        precio_raw = float(val)
                                        break
                                    except (ValueError, TypeError):
                                        if isinstance(val, dict):
                                            precio_raw = float(val.get('amount', val.get('value', 0)))
                                            break
                            if not precio_raw or precio_raw <= 0:
                                continue
                            currency = flight.get('currency', flight.get('currencyCode', 'USD'))
                            precio_usd = precio_raw if currency == 'USD' else round(precio_raw / usd_to_ars, 2)
                            precio_ars = round(precio_raw * usd_to_ars, 2) if currency == 'USD' else precio_raw
                            vuelos.append({
                                'destino': dest, 'destino_nombre': DESTINOS.get(dest, dest),
                                'origen': 'BUE', 'aerolinea': 'FO', 'aerolinea_nombre': 'Flybondi',
                                'precio_usd': precio_usd, 'precio_ars': precio_ars,
                                'duracion_ida': flight.get('duration', ''), 'duracion_vuelta': '',
                                'escalas_ida': flight.get('stops', 0), 'escalas_vuelta': 0,
                                'es_directo': 1 if flight.get('stops', 0) == 0 else 0,
                                'segmentos_ida': f"BUE→{dest} (FO)", 'segmentos_vuelta': '',
                                'hora_salida': flight.get('departureTime', flight.get('departure', '')),
                                'hora_llegada': flight.get('arrivalTime', flight.get('arrival', '')),
                                'fuente': 'flybondi_initial_state',
                                'nota': f"Original: {currency} {precio_raw}",
                            })
                        total_encontrados += len([v for v in vuelos if v.get('fuente') == 'flybondi_initial_state'])
                        continue
                    
                    # ── ESTRATEGIA 2+3: Regex + secciones ida/vuelta ──
                    secciones = _detectar_seccion_ida_vuelta(html_text)
                    if secciones['ida']:
                        print(f" — Precios ida: {secciones['ida'][:5]}")
                        for precio_usd in secciones['ida'][:10]:
                            precio_ars = round(precio_usd * usd_to_ars, 2)
                            vuelos.append({
                                'destino': dest, 'destino_nombre': DESTINOS.get(dest, dest),
                                'origen': 'BUE', 'aerolinea': 'FO', 'aerolinea_nombre': 'Flybondi',
                                'precio_usd': round(precio_usd, 2), 'precio_ars': precio_ars,
                                'duracion_ida': '', 'duracion_vuelta': '',
                                'escalas_ida': 0, 'escalas_vuelta': 0, 'es_directo': 1,
                                'segmentos_ida': f"BUE→{dest} (FO, directo)", 'segmentos_vuelta': '',
                                'hora_salida': fecha_ida, 'hora_llegada': '',
                                'fuente': 'flybondi_html_regex',
                                'nota': f"Original: USD {precio_usd}",
                            })
                        total_encontrados += len(secciones['ida'][:10])
                        continue
                    
                    # Regex global (sin secciones detectadas)
                    all_prices = _extraer_precios_regex(html_text)
                    if all_prices:
                        print(f" — {len(all_prices)} precios globales: {all_prices[:5]}")
                        for precio_usd in all_prices[:10]:
                            precio_ars = round(precio_usd * usd_to_ars, 2)
                            vuelos.append({
                                'destino': dest, 'destino_nombre': DESTINOS.get(dest, dest),
                                'origen': 'BUE', 'aerolinea': 'FO', 'aerolinea_nombre': 'Flybondi',
                                'precio_usd': round(precio_usd, 2), 'precio_ars': precio_ars,
                                'duracion_ida': '', 'duracion_vuelta': '',
                                'escalas_ida': 0, 'escalas_vuelta': 0, 'es_directo': 1,
                                'segmentos_ida': f"BUE→{dest} (FO)", 'segmentos_vuelta': '',
                                'hora_salida': fecha_ida, 'hora_llegada': '',
                                'fuente': 'flybondi_regex_global',
                                'nota': f"Original: USD {precio_usd}",
                            })
                        total_encontrados += len(all_prices[:10])
                        continue
                    
                    # ── FAILSAFE: Debug dump ──
                    print(f" — 0 precios extraídos")
                    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_text, re.DOTALL)
                    if body_match:
                        body_clean = re.sub(r'<[^>]+>', ' ', body_match.group(1))
                        body_clean = re.sub(r'\s+', ' ', body_clean).strip()
                        print(f"  🔍 DEBUG body (primeros 1000 chars):")
                        print(f"  {body_clean[:1000]}")
                    else:
                        print(f"  🔍 DEBUG HTML (primeros 1000 chars):")
                        print(f"  {html_text[:1000]}")
                    
                elif r.status_code == 403:
                    print(f"🚫 403 Forbidden — WAF bloqueó la request")
                    errores_red += 1
                elif r.status_code == 429:
                    print(f"🚫 429 Rate Limited — demasiadas requests")
                    errores_red += 1
                else:
                    print(f"⚠️ HTTP {r.status_code}")
                    errores_red += 1
                    
            except Exception as e:
                error_str = str(e).lower()
                if any(kw in error_str for kw in ['timeout', 'connection', 'refused', 'reset', 'ssl', '403', 'waf']):
                    print(f"🚫 [!] Flybondi: Bloqueo de IP o cambio de estructura — {type(e).__name__}")
                else:
                    print(f"❌ Error de código: {e}")
                errores_red += 1
            
            human_delay(2.0, 4.0)
    
    # Resumen final
    if total_encontrados > 0:
        print(f"  ✅ Flybondi: {total_encontrados} vuelos extraídos")
    elif errores_red > 0:
        print(f"  ⚠️ [!] Flybondi: {errores_red} errores — posible bloqueo de IP")
    else:
        print(f"  ⚠️ Flybondi: 0 vuelos — SPA carga OK pero precios solo vía JS (requiere Playwright)")
    
    try:
        client.close()
    except:
        pass
    
    return vuelos


# ─── DASHBOARD ──────────────────────────────────────────────────────────────

TEMPLATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")

def generar_dashboard(vuelos_actuales, historial, usd_to_ars, alertas, timestamp):
    """Genera dashboard.html inyectando datos en el template HTML."""
    
    # Leer template
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    
    # Cantidad de búsquedas históricas
    total_historico = len(set(h['timestamp'][:16] for h in historial))
    
    # Reemplazar placeholders con datos reales
    html = html.replace("__VUELOS_JSON__", json.dumps(vuelos_actuales, ensure_ascii=False))
    html = html.replace("__HISTORIAL_JSON__", json.dumps(historial, ensure_ascii=False))
    html = html.replace("__USD_TO_ARS__", str(round(usd_to_ars, 2)))
    html = html.replace("__TIMESTAMP__", timestamp)
    html = html.replace("__TOTAL_HISTORICO__", str(total_historico))
    
    # Escribir dashboard final
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ─── MAIN ───────────────────────────────────────────────────────────────────

def buscar_vuelos():
    """Flujo principal de búsqueda."""
    print("=" * 60)
    print("  ✈️  BRASIL2026 — Flight Tracker v3")
    print("=" * 60)
    print(f"  📅 {len(FECHAS)} combinaciones de fechas:")
    for fi, fv in FECHAS:
        print(f"     {fi} → {fv} (7 noches)")
    print(f"  👥 {ADULTOS} pasajeros")
    print(f"  🛫 Orígenes: {', '.join(ORIGENES)}")
    print(f"  🎯 Destinos: {', '.join(DESTINOS.keys())}")
    print(f"  📢 Total búsquedas: {len(ORIGENES) * len(DESTINOS) * len(FECHAS)}")
    print("=" * 60)
    
    # 0. Pre-flight check (IP + stealth)
    pre_flight_check()
    
    # 0.5 Clean DNS cache
    try:
        from core.http_client import HttpClient
        HttpClient.clean_scene()
    except Exception:
        pass
    
    # 1. Init
    init_db()
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    
    # 2. Tipo de cambio
    usd_to_ars = get_exchange_rate()
    print(f"\n  💱 Tipo de cambio: 1 USD = {usd_to_ars:,.2f} ARS\n")
    
    # 3. Precios anteriores (para alertas)
    prev_best = get_previous_best_prices()
    
    # 4. Buscar en Amadeus
    print("── AMADEUS API ──────────────────────────────────")
    vuelos_amadeus = buscar_amadeus(usd_to_ars, timestamp)
    print(f"  Total Amadeus: {len(vuelos_amadeus)} vuelos únicos\n")
    
    # 5. Buscar en Flybondi (stealth)
    print("── FLYBONDI (Stealth) ───────────────────────────")
    vuelos_flybondi = buscar_flybondi(usd_to_ars, timestamp)
    print(f"  Total Flybondi: {len(vuelos_flybondi)} vuelos\n")
    
    # 6. Combinar resultados
    todos_vuelos = vuelos_amadeus + vuelos_flybondi
    todos_vuelos.sort(key=lambda x: x['precio_usd'])
    
    print(f"── TOTAL: {len(todos_vuelos)} vuelos encontrados ──────────────")
    
    # 7. Guardar en DB
    save_vuelos(todos_vuelos, timestamp)
    
    # 8. Calcular precio mínimo por destino y guardar historial
    precios_por_destino = {}
    for v in todos_vuelos:
        d = v['destino']
        if d not in precios_por_destino or v['precio_usd'] < precios_por_destino[d]['precio_usd']:
            precios_por_destino[d] = {
                'precio_usd': v['precio_usd'],
                'precio_ars': v['precio_ars'],
                'aerolinea': v['aerolinea'],
            }
    
    save_historial(precios_por_destino, usd_to_ars, timestamp)
    
    # 9. Generar alertas
    print("\n── ALERTAS ──────────────────────────────────────")
    alertas_generadas = 0
    for dest, data in precios_por_destino.items():
        if dest in prev_best:
            save_alerta(dest, prev_best[dest], data['precio_usd'], timestamp)
            alertas_generadas += 1
    if alertas_generadas == 0:
        print("  Sin alertas (primera búsqueda o sin cambios significativos)")
    
    # 10. Generar dashboard
    print("\n── DASHBOARD ────────────────────────────────────")
    historial = get_historial_completo()
    alertas = get_alertas_recientes()
    generar_dashboard(todos_vuelos, historial, usd_to_ars, alertas, timestamp)
    print(f"  ✅ Dashboard generado: {DASHBOARD_FILE}")
    
    # 11. Guardar JSON de respaldo
    json_file = os.path.join(DATA_DIR, f"vuelos_{now.strftime('%Y-%m-%d_%H-%M')}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(todos_vuelos, f, indent=2, ensure_ascii=False)
    
    # 12. Resumen final
    print("\n" + "=" * 60)
    print("  📊 RESUMEN")
    print("=" * 60)
    
    directos = [v for v in todos_vuelos if v.get('es_directo')]
    print(f"  Vuelos totales:  {len(todos_vuelos)}")
    print(f"  Vuelos directos: {len(directos)}")
    print(f"  Fuentes:         Amadeus ({len(vuelos_amadeus)}) + Flybondi ({len(vuelos_flybondi)})")
    
    print(f"\n  🏆 TOP 5 MÁS BARATOS:")
    for i, v in enumerate(todos_vuelos[:5], 1):
        directo_tag = "✈ directo" if v.get('es_directo') else f"🔄 {v.get('escalas_ida', '?')} esc."
        print(f"  {i}. {v['destino']} ({v['destino_nombre']}) — USD {v['precio_usd']:.0f} / ARS {v['precio_ars']:,.0f}")
        print(f"     {v['aerolinea_nombre']} · {directo_tag} · {v.get('duracion_ida', '?')} · {v['origen']}")
    
    print(f"\n  💡 Dashboard: {os.path.realpath(DASHBOARD_FILE)}")
    print(f"  💾 Base de datos: {os.path.realpath(DB_FILE)}")
    print("=" * 60)
    
    # Abrir dashboard
    webbrowser.open('file://' + os.path.realpath(DASHBOARD_FILE))


if __name__ == "__main__":
    buscar_vuelos()
