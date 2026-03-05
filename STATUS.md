# BRASIL2026 — Resumen Ejecutivo Ultra-Detallado

> **Fecha de este documento:** 2026-03-04 11:48
> **Última ejecución del scraper:** 2026-03-04 00:55
> **Ruta del proyecto:** `c:\Users\Facun\OneDrive\Escritorio\PROYECTOS PERSONALES\BRASIL2026`
> **Objetivo del viaje:** 2 adultos, Buenos Aires → Brasil, 6–13 abril 2026, presupuesto total vuelo+airbnb ARS $1,500,000

---

## 1. Estructura completa del proyecto

```
BRASIL2026/
│
├── scraper.py                  # Script principal (903 líneas, 40KB)
│                                 Busca vuelos Amadeus + Flybondi, guarda en SQLite,
│                                 genera dashboard, detecta alertas de precio
│
├── vuelos_brasil.py            # Buscador manual interactivo (187 líneas, 7.4KB)
│                                 Abre links de Google Flights, Kayak, Despegar, Airbnb
│
├── dashboard.html              # Dashboard autogenerado (57KB)
│                                 HTML estático con Chart.js, tabla filtrable, alertas
│
├── .env                        # Credenciales Amadeus API (92 bytes)
│                                 AMADEUS_CLIENT_ID=uSvZIh8BGXEwdGy9Rgy8f4A6LTFiHdfl
│                                 AMADEUS_CLIENT_SECRET=bmzaZb76LH1jL0Me
│
├── AGENTS.md                   # Instrucciones para AI agents (34 líneas)
├── APIS_RESEARCH.md            # Investigación de APIs de vuelos (57 líneas)
├── RESEARCH.md                 # Research de curl_cffi, MCP, skills (183 líneas)
├── TWITTER_RESEARCH.md         # Research de Twitter API (pendiente)
├── skills-lock.json            # Lock file de skills instaladas
│
├── core/                       # Módulos compartidos (origen: proyecto vuelos/Odiseo)
│   ├── __init__.py             # Re-exports de todas las clases (72 líneas)
│   ├── http_client.py          # Cliente HTTP stealth curl_cffi (658 líneas, 24KB)
│   ├── base_sniffer.py         # Clase abstracta para scrapers (333 líneas, 13KB)
│   └── database.py             # SQLite wrapper con batch ops (303 líneas, 12KB)
│
└── data/                       # Base de datos y archivos de respaldo
    ├── brasil2026.db           # SQLite database (57KB) — 3 tablas con índices
    ├── vuelos_2026-03-04_00-55.json  # Última búsqueda (63 vuelos, 38KB)
    ├── vuelos_2026-03-04_00-00.json  # Búsqueda anterior (36 vuelos, 18KB)
    ├── vuelos_2026-03-02_01-34.json  # Primera búsqueda (15KB)
    ├── vuelos.json             # Latest formato viejo (ya no se actualiza)
    └── historico.json          # Histórico formato viejo (ya no se actualiza)
```

---

## 2. Fuentes de datos — Detalle completo

### 2.1 Amadeus Flight Offers Search API (fuente principal)

| Campo | Valor |
|-------|-------|
| **SDK Python** | `amadeus` (pip install amadeus) |
| **Versión API** | v2 (`/v2/shopping/flight-offers`) |
| **Autenticación** | OAuth2 — client_id + client_secret → bearer token automático |
| **Entorno actual** | ⚠️ **TEST** (`test.api.amadeus.com`) — NO producción |
| **Cómo cambiar a producción** | `amadeus = Client(..., hostname='production')` + nueva key |
| **Límite free tier test** | ~2,000 requests/mes gratis |
| **Límite free tier producción** | Se obtiene pidiendo aprobación a Amadeus |
| **Qué consulta** | GDS (Global Distribution System) — sistema compartido entre aerolíneas |
| **Moneda solicitada** | USD (convertido a ARS localmente) |
| **Max resultados** | 10 por combinación origen/destino |
| **Búsquedas por ejecución** | 16 (2 orígenes × 8 destinos) |

**Aerolíneas que aparecen en resultados (distribuyen por GDS):**
- GOL (G3) ←— la más frecuente y barata en los resultados
- Aerolíneas Argentinas (AR) ←— única con vuelos directos a GIG
- LATAM (LA) ←— vía Santiago de Chile (SCL)
- Emirates (EK) ←— opera EZE→GIG directo (codeshare)
- Turkish Airlines (TK) ←— vía GRU
- Ethiopian Airlines (ET) ←— vía GRU

**Aerolíneas que NO aparecen (no distribuyen por GDS):**
- ❌ Flybondi (FO) — vende solo por su web
- ❌ JetSmart (JA) — vende solo por su web

**¿Los precios son reales?**
- Los precios vienen del GDS y representan tarifas publicadas reales
- PERO en entorno TEST pueden estar cacheados o no 100% actualizados
- PERO la API puede dar precios más altos que la web directa de la aerolínea (no incluye tarifas negociadas ni promos web-only)
- El precio total incluye impuestos y tasas (`offer['price']['total']`)
- El precio es para los 2 pasajeros combinados (no por persona)

**Lo que extrae de cada resultado Amadeus:**

```python
# De cada offer en response.data:
precio_usd = float(offer['price']['total'])           # Precio total para todos los pasajeros
aerolinea = offer['validatingAirlineCodes'][0]         # Código IATA de la aerolínea
itinerarios = offer['itineraries']                     # [ida, vuelta]
  ida['duration']                                      # "PT2H55M" → se formatea a "2h 55m"
  ida['segments']                                      # Lista de segmentos (tramos)
    segment['departure']['iataCode']                   # Aeropuerto de salida
    segment['departure']['at']                         # Hora de salida ISO
    segment['arrival']['iataCode']                     # Aeropuerto de llegada
    segment['arrival']['at']                           # Hora de llegada ISO
    segment['carrierCode']                             # Aerolínea operadora
    segment['number']                                  # Número de vuelo
    segment['duration']                                # Duración del segmento
# Escalas = len(segments) - 1
# es_directo = (escalas_ida == 0 AND escalas_vuelta == 0)
```

### 2.2 AwesomeAPI (tipo de cambio)

| Campo | Valor |
|-------|-------|
| **URL** | `https://economia.awesomeapi.com.br/json/last/USD-ARS` |
| **Auth** | Ninguna — API pública brasileña |
| **Rate limit** | Sin límite conocido |
| **Dato usado** | Campo `USDARS.bid` (precio de compra) |
| **Última cotización** | 1 USD = 1,414.98 ARS |
| **Fallback** | Si falla → usa 1,400.00 ARS hardcodeado |
| **Timeout** | 10 segundos |

### 2.3 Flybondi stealth scraping (integrado, no probado exitosamente)

| Campo | Valor |
|-------|-------|
| **Módulo** | `core/http_client.py` → clase `HttpClient` |
| **Librería** | `curl_cffi` con impersonación Chrome |
| **Endpoint** | `https://api-prod.flybondi.com/fb/travel/prices` |
| **Método** | GET con params |
| **Destinos configurados** | Solo FLN (Florianópolis) por ahora |
| **Moneda solicitada** | ARS (directo, sin conversión) |
| **Estado** | ⚠️ El código está integrado en `buscar_flybondi()` (línea 380-469 de scraper.py), pero la API puede estar caída, haber cambiado de endpoint, o requerir otros headers |
| **Técnica** | Primero hace "warm session" visitando flybondi.com, luego consulta la API con headers de Chrome real |

---

## 3. Parámetros de búsqueda

```python
# En scraper.py líneas 35-49:
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

ORIGENES = ["EZE", "AEP"]  # Ezeiza + Aeroparque
FECHA_IDA = "2026-04-06"
FECHA_VUELTA = "2026-04-13"   # 7 noches
ADULTOS = 2
```

**Nota:** Todos estos valores están hardcodeados en el script. Para cambiar fechas o destinos hay que editar el código.

---

## 4. Resultado completo de la última búsqueda (2026-03-04 00:55)

### 4.1 Resumen

| Métrica | Valor |
|---------|-------|
| Total vuelos encontrados | **63** (deduplicados) |
| Vuelos directos | **7** (todos a GIG desde AEP o EZE) |
| Desde EZE | 26 vuelos |
| Desde AEP | 37 vuelos |
| Fuente Amadeus | 63 vuelos |
| Fuente Flybondi | 0 vuelos (endpoint no respondió) |
| Tipo de cambio | 1 USD = 1,414.98 ARS |
| Registros en historial | 8 (uno por destino) |

### 4.2 Mejor precio por destino

| # | Destino | Ciudad | USD (x2 pax) | ARS (x2 pax) | USD/persona | Aerolínea | Tipo | Duración ida | Desde |
|---|---------|--------|-------------|-------------|------------|-----------|------|-------------|-------|
| 1 | FLN | Florianópolis | 716 | 1,012,570 | 358 | GOL | 2 escalas | 29h 10m | EZE |
| 2 | **GIG** | **Río de Janeiro** | **728** | **1,029,833** | **364** | **Aerolíneas** | **✈ DIRECTO** | **2h 55m** | **AEP** |
| 3 | SSA | Salvador de Bahía | 746 | 1,055,020 | 373 | GOL | 2 escalas | 23h 50m | EZE |
| 4 | FOR | Fortaleza | 795 | 1,125,487 | 398 | GOL | 2 escalas | 21h 5m | EZE |
| 5 | BPS | Porto Seguro | 898 | 1,270,666 | 449 | GOL | 1 escala | 9h 55m | AEP |
| 6 | MCZ | Maceió | 1,007 | 1,425,183 | 504 | GOL | 2 escalas | 28h 50m | AEP |
| 7 | REC | Recife | 1,210 | 1,712,427 | 605 | Aerolíneas | 1 escala | 8h 45m | AEP |
| 8 | NAT | Natal | 1,321 | 1,869,208 | 661 | Aerolíneas | 1 escala | 8h 55m | AEP |

### 4.3 Los 7 vuelos directos (todos a GIG — Río de Janeiro)

| Aerolínea | Vuelo | USD x2 | Dur. ida | Dur. vuelta | Horario ida | Desde |
|-----------|-------|--------|---------|------------|------------|-------|
| Aerolíneas | AR1270/AR1271 | 728 | 2h 55m | 3h 25m | 23:20→02:15 | AEP |
| Aerolíneas | AR1270/AR1271 | 788 | 2h 55m | 3h 25m | 23:20→02:15 | AEP |
| Aerolíneas | AR1260/AR1271 | 828 | 2h 55m | 3h 25m | 06:00→08:55 | AEP |
| Aerolíneas | AR1260/AR1269 | 888 | 2h 55m | 3h 25m | 06:00→08:55 | AEP |
| Emirates | EK248/EK247 | 914 | 2h 45m | 3h 25m | 22:40→01:25 | EZE |
| Aerolíneas | AR7740/AR7745 | 1,306 | 2h 55m | 3h 30m | 14:00→16:55 | EZE |
| Aerolíneas | AR7740/AR7741 | 1,333 | 2h 55m | 3h 20m | 14:00→16:55 | EZE |

> **Hallazgo clave:** Solo existe vuelo directo a Río de Janeiro (GIG). Todos los demás destinos brasileños requieren mínimo 1 escala, generalmente en GRU/CGH (São Paulo). El vuelo más barato directo es AEP→GIG con Aerolíneas por USD 728 (USD 364/persona).

### 4.4 Top 20 vuelos más baratos (datos completos)

```
 1. FLN (Florianópolis)  USD  716 | GOL              | 2 esc | 29h 10m | EZE | EZE→BSB→GRU→FLN
 2. GIG (Río de Janeiro) USD  728 | Aerolíneas       | DIR.  | 2h 55m  | AEP | AEP→GIG
 3. SSA (Salvador)       USD  746 | GOL              | 2 esc | 23h 50m | EZE | EZE→GIG→VCP→SSA
 4. SSA (Salvador)       USD  752 | GOL              | 2 esc | 23h 50m | EZE | EZE→GIG→VCP→SSA
 5. SSA (Salvador)       USD  752 | GOL              | 2 esc | 27h 20m | AEP | AEP→GIG→VCP→SSA
 6. SSA (Salvador)       USD  754 | GOL              | 2 esc | 27h 20m | AEP | AEP→GIG→VCP→SSA
 7. SSA (Salvador)       USD  760 | GOL              | 2 esc | 21h 15m | AEP | AEP→FLN→GRU→SSA
 8. GIG (Río de Janeiro) USD  788 | Aerolíneas       | DIR.  | 2h 55m  | AEP | AEP→GIG
 9. FOR (Fortaleza)      USD  795 | GOL              | 2 esc | 21h 5m  | EZE | EZE→FLN→GRU→FOR
10. FOR (Fortaleza)      USD  801 | GOL              | 2 esc | 22h 25m | AEP | AEP→GIG→CGH→FOR
11. GIG (Río de Janeiro) USD  828 | Aerolíneas       | DIR.  | 2h 55m  | AEP | AEP→GIG
12. GIG (Río de Janeiro) USD  849 | LATAM            | 1 esc | 10h 30m | AEP | AEP→SCL→GIG
13. GIG (Río de Janeiro) USD  864 | LATAM            | 1 esc | 10h 30m | AEP | AEP→SCL→GIG
14. GIG (Río de Janeiro) USD  888 | Aerolíneas       | DIR.  | 2h 55m  | AEP | AEP→GIG
15. BPS (Porto Seguro)   USD  898 | GOL              | 1 esc | 9h 55m  | AEP | AEP→GRU→BPS
16. BPS (Porto Seguro)   USD  902 | GOL              | 2 esc | 40h 35m | EZE | EZE→GIG→CGH→BPS
17. BPS (Porto Seguro)   USD  908 | GOL              | 1 esc | 9h 55m  | AEP | AEP→GRU→BPS
18. GIG (Río de Janeiro) USD  914 | Emirates         | DIR.  | 2h 45m  | EZE | EZE→GIG
19. BPS (Porto Seguro)   USD  918 | GOL              | 2 esc | 22h     | AEP | AEP→FLN→GRU→BPS
20. GIG (Río de Janeiro) USD  989 | Aerolíneas       | 1 esc | 6h 30m  | AEP | AEP→GRU→GIG
```

---

## 5. Arquitectura del código — scraper.py (903 líneas)

### 5.1 Secciones del archivo

| Sección | Líneas | Qué hace |
|---------|--------|----------|
| Imports y configuración | 1-49 | Carga .env, inicializa Amadeus, define destinos/fechas |
| Base de datos | 52-220 | 8 funciones para CRUD en SQLite |
| Utilidades | 223-317 | Diccionario aerolíneas, tipo de cambio, formateo |
| Búsqueda Amadeus | 320-375 | Loop por origen/destino, extracción de detalles, dedup |
| Búsqueda Flybondi | 378-469 | Scraping stealth con HttpClient |
| Dashboard HTML | 472-815 | Genera HTML con CSS + JS embebido |
| Main (buscar_vuelos) | 818-903 | Flujo principal que orquesta todo |

### 5.2 Todas las funciones documentadas

**Base de datos (8 funciones):**

| Función | Línea | Qué hace |
|---------|-------|----------|
| `init_db()` | 54 | Crea las 3 tablas + 4 índices si no existen |
| `get_previous_best_prices()` | 109 | `SELECT destino, MIN(precio_min_usd) ... GROUP BY destino` — para alertas |
| `get_last_prices()` | 122 | Precios de la última búsqueda — para tendencias en dashboard |
| `save_vuelos(vuelos, timestamp)` | 135 | INSERT OR IGNORE de cada vuelo (dedup por UNIQUE constraint) |
| `save_historial(precios_por_destino, tc, ts)` | 165 | INSERT del precio mínimo por destino en cada ejecución |
| `save_alerta(destino, precio_ant, precio_nuevo, ts)` | 179 | Genera alerta si cambio >1%, guarda en tabla alertas |
| `get_historial_completo()` | 199 | SELECT todo el historial ordenado por timestamp — para gráfico Chart.js |
| `get_alertas_recientes(limit=20)` | 212 | Últimas 20 alertas — para panel de alertas del dashboard |

**Utilidades (4 funciones):**

| Función | Línea | Qué hace |
|---------|-------|----------|
| `get_exchange_rate()` | 236 | GET a AwesomeAPI, retorna float, fallback 1400.0 |
| `formatear_duracion(duracion_iso)` | 246 | "PT3H45M" → "3h 45m" |
| `formatear_hora(fecha_iso)` | 265 | "2026-04-06T21:30:00" → "21:30" |
| `extraer_detalles_vuelo(offer)` | 275 | Parsea itinerarios de Amadeus: duración, escalas, segmentos, horarios |

**Búsqueda (2 funciones):**

| Función | Línea | Qué hace |
|---------|-------|----------|
| `buscar_amadeus(usd_to_ars, timestamp)` | 322 | Loop 2 orígenes × 8 destinos, max 10 por búsqueda, dedup con set() |
| `buscar_flybondi(usd_to_ars, timestamp)` | 380 | HttpClient stealth → warm_session → GET API → parsear vuelos |

**Dashboard (1 función):**

| Función | Línea | Qué hace |
|---------|-------|----------|
| `generar_dashboard(vuelos, historial, tc, alertas, ts)` | 474 | Genera HTML completo con CSS+JS embebido, Chart.js, tabla filtrable |

**Main (1 función):**

| Función | Línea | Qué hace |
|---------|-------|----------|
| `buscar_vuelos()` | 818 | Flujo completo de 12 pasos (ver sección 5.3) |

### 5.3 Flujo de ejecución (buscar_vuelos)

```
Paso  1 → init_db()                          Crea tablas SQLite si no existen
Paso  2 → get_exchange_rate()                GET AwesomeAPI → 1 USD = X ARS
Paso  3 → get_previous_best_prices()         Lee historial para comparar alertas
Paso  4 → buscar_amadeus()                   16 búsquedas (2 orígenes × 8 destinos)
          ├─ Para cada combinación:
          │  ├─ amadeus.shopping.flight_offers_search.get()
          │  ├─ extraer_detalles_vuelo() por cada offer
          │  ├─ Dedup con set: key = destino-aerolinea-precio-duracion
          │  └─ Append a lista
          └─ Return lista deduplicada
Paso  5 → buscar_flybondi()                  Intenta scraping stealth (puede fallar)
          ├─ import HttpClient
          ├─ warm_session("https://flybondi.com")
          ├─ GET api-prod.flybondi.com/fb/travel/prices
          └─ Parsear respuesta JSON
Paso  6 → Combinar y ordenar               amadeus + flybondi, sort by precio_usd
Paso  7 → save_vuelos()                     INSERT OR IGNORE en tabla vuelos
Paso  8 → Calcular mínimos por destino      Dict {destino: {precio, aerolínea}}
          → save_historial()                 INSERT en tabla historial_precio
Paso  9 → Para cada destino con historial:
          → save_alerta()                    Si cambió >1%, guarda alerta
Paso 10 → get_historial_completo()          Lee todo el historial
          → get_alertas_recientes()          Lee últimas alertas
          → generar_dashboard()              Genera dashboard.html (57KB)
Paso 11 → json.dump() a archivo timestamped  Backup JSON en data/
Paso 12 → Imprime resumen en consola
          → webbrowser.open(dashboard.html)  Abre en el navegador
```

### 5.4 Deduplicación

Doble capa:
1. **En memoria (set):** Key = `{destino}-{aerolinea}-{precio_usd}-{duracion_ida}` — evita duplicados dentro de la misma búsqueda
2. **En DB (UNIQUE constraint):** `UNIQUE(destino, origen, aerolinea, precio_usd, duracion_ida, timestamp)` con `INSERT OR IGNORE`

---

## 6. Base de datos SQLite — Schema completo

**Archivo:** `data/brasil2026.db` (57KB)

### Tabla `vuelos`
```sql
CREATE TABLE vuelos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destino TEXT NOT NULL,              -- "FLN", "GIG", etc.
    destino_nombre TEXT DEFAULT '',     -- "Florianópolis", "Río de Janeiro"
    origen TEXT DEFAULT 'EZE',          -- "EZE" o "AEP"
    aerolinea TEXT NOT NULL,            -- "G3", "AR", "EK", etc.
    aerolinea_nombre TEXT DEFAULT '',   -- "GOL", "Aerolíneas Argentinas"
    precio_usd REAL NOT NULL,          -- Total para 2 pasajeros
    precio_ars REAL NOT NULL,          -- Convertido con tipo de cambio del momento
    duracion_ida TEXT DEFAULT '',       -- "2h 55m"
    duracion_vuelta TEXT DEFAULT '',    -- "3h 25m"
    escalas_ida INTEGER DEFAULT 0,     -- 0 = directo
    escalas_vuelta INTEGER DEFAULT 0,
    es_directo INTEGER DEFAULT 0,      -- 1 si ida Y vuelta son directos
    segmentos_ida TEXT DEFAULT '',      -- "AEP→GIG (AR1270, 2h 55m)"
    segmentos_vuelta TEXT DEFAULT '',   -- "GIG→AEP (AR1271, 3h 25m)"
    hora_salida TEXT DEFAULT '',        -- "23:20"
    hora_llegada TEXT DEFAULT '',       -- "02:15"
    fuente TEXT DEFAULT 'amadeus',      -- "amadeus" o "flybondi_direct"
    timestamp TEXT NOT NULL,            -- "2026-03-04 00:55"
    UNIQUE(destino, origen, aerolinea, precio_usd, duracion_ida, timestamp)
);
-- Índices: idx_vuelos_destino, idx_vuelos_precio, idx_vuelos_timestamp
```

### Tabla `historial_precio`
```sql
CREATE TABLE historial_precio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destino TEXT NOT NULL,              -- "FLN"
    precio_min_usd REAL NOT NULL,      -- Mejor precio del día para ese destino
    precio_min_ars REAL NOT NULL,
    aerolinea TEXT DEFAULT '',          -- Aerolínea del mejor precio
    tipo_cambio REAL DEFAULT 0,        -- TC usado en esa búsqueda
    timestamp TEXT NOT NULL
);
-- Índice: idx_historial_destino
```

### Tabla `alertas`
```sql
CREATE TABLE alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destino TEXT NOT NULL,
    precio_anterior_usd REAL,
    precio_nuevo_usd REAL,
    variacion_pct REAL,                -- Negativo = bajó, positivo = subió
    mensaje TEXT,                       -- "📉 BAJÓ 5.2% | Florianópolis: USD 750 → USD 711"
    timestamp TEXT NOT NULL
);
```

**Lógica de alertas:** Solo se genera alerta si `abs(variacion) >= 1%`. Compara contra el mejor precio HISTÓRICO (no solo la última búsqueda).

---

## 7. Módulos core/ — Referencia completa de API

Estos módulos se copiaron del proyecto `vuelos/Odiseo` (que a su vez viene de `FRAVEGA`). El `scraper.py` de Brasil2026 usa directamente el `HttpClient` para Flybondi y no los otros módulos, pero están disponibles para uso futuro.

### 7.1 `core/http_client.py` (658 líneas)

**Clase `HttpClient` (líneas 177-472) — Cliente HTTP sincrónico stealth:**

| Método | Qué hace |
|--------|----------|
| `__init__(impersonate, retry_count, retry_delay, retry_backoff, retry_jitter, timeout, extra_headers, proxy, rotate_browser, stealth_mode, delay_range, max_requests_per_hour)` | Constructor con 12 parámetros configurables |
| `get(url, **kwargs)` | GET con impersonación + retry + circuit breaker |
| `post(url, **kwargs)` | POST con impersonación + retry + circuit breaker |
| `get_json(url, **kwargs)` | GET + .json() automático |
| `post_json(url, **kwargs)` | POST + .json() automático |
| `graphql(url, query, variables)` | Ejecuta query GraphQL |
| `warm_session(base_url)` | Visita homepage para establecer cookies (simula humano) |
| `reset_session()` | Cierra session actual, crea nueva con otro browser |
| `verify_fingerprint()` | Verifica que el JA3 fingerprint coincide con Chrome real |
| `close()` | Libera recursos |

**Mecanismos de protección internos:**
- `_stealth_delay()` → delay aleatorio entre 0.8-2.5 segundos entre requests
- `_check_rate_limit(url)` → máximo 300 requests/hora por dominio
- `_get_browser()` → elige browser de lista: chrome, chrome119, chrome120, chrome124
- `_request(method, url)` → wrapper interno con Circuit Breaker + retry manual

**Clase `AsyncHttpClient` (líneas 480-619) — Cliente HTTP asíncrono:**

| Método | Qué hace |
|--------|----------|
| `get(url)` | GET async con semaphore |
| `post(url)` | POST async con semaphore |
| `gather_get(urls)` | GET múltiples URLs en paralelo (limitado por semaphore) |
| `graphql_batch(url, queries)` | Múltiples queries GraphQL en paralelo |

**Clase `CircuitBreaker` (líneas 98-170):**
- CLOSED → Todo normal
- OPEN → Después de 5 fallos consecutivos, rechaza requests por 60 segundos
- HALF_OPEN → Deja pasar 1 request de prueba para ver si se recuperó

**8 excepciones custom (líneas 627-657):**
`ScrapingError` → `WAFBlockedError` | `CircuitBreakerOpenError` | `NetworkError` | `ServerError` | `ParsingError` | `RateLimitError` | `GlitchDetectedError`

### 7.2 `core/base_sniffer.py` (333 líneas)

**Dataclasses:**
- `Product(id, name, brand, current_price, list_price, category, url, image_url, source, stock, discount_pct, raw_data)`
- `Glitch(product, reason, severity, previous_price, drop_pct, detected_at)`
- `ScrapeResult(target_name, category, products_found, glitches_found, errors, duration_seconds, products, glitches)`

**Clase `BaseSniffer` (abstracta, Template Method):**

| Método | Tipo | Qué hace |
|--------|------|----------|
| `fetch_products(category)` | Abstracto | Obtener datos crudos del target |
| `parse_product(raw)` | Abstracto | Convertir raw dict → Product |
| `save_products(products)` | Abstracto | Persistir en DB |
| `detect_glitch(product, previous_price)` | Concreto | Detecta precios anómalos: descuento >40%, precio <$1000, caída >50% |
| `on_glitch_found(glitch)` | Hook | Override para notificaciones (Telegram, etc.) |
| `run_cycle(categories)` | Concreto | Ejecuta: fetch → parse → detect → save para cada categoría |
| `run_forever(categories, interval)` | Concreto | Loop infinito con sleep de `interval` segundos |

### 7.3 `core/database.py` (303 líneas)

**Clase `Database`:**

| Método | Qué hace |
|--------|----------|
| `save_products(products)` | Batch INSERT con executemany (100x más rápido) |
| `save_glitch(glitch)` | Guarda glitch detectado |
| `get_cheapest_by_category(category, source, limit)` | Los N más baratos de una categoría |
| `get_biggest_discounts(min_discount, limit)` | Mayor descuento (oportunidades) |
| `compare_prices_across_sources(product_name_like)` | Comparar precios entre tiendas |
| `get_price_history(product_id, source)` | Historial de precios de un producto |
| `get_previous_price(product_id, source)` | Precio anterior (para detectar caídas) |
| `get_recent_glitches(hours, limit)` | Glitches de las últimas N horas |
| `get_stats()` | Estadísticas generales de la DB |

> **Nota:** El scraper.py de Brasil2026 tiene sus PROPIAS funciones de DB (no usa `core/database.py` directamente) porque el schema de vuelos es diferente al de productos de e-commerce. El core/database.py queda disponible para uso futuro si se refactoriza.

### 7.4 `core/__init__.py` — Re-exports

```python
from core import HttpClient, AsyncHttpClient, BaseSniffer, Database
from core import Product, Glitch, ScrapeResult
from core import ScrapingError, WAFBlockedError, CircuitBreakerOpenError, ...
```

---

## 8. Dashboard (dashboard.html)

**Tamaño:** 57KB de HTML+CSS+JS generado por `generar_dashboard()` (343 líneas de código generador).

**Diseño:**
- Dark mode (#08080c fondo, #111118 superficies)
- Fonts: Inter (body) + JetBrains Mono (datos numéricos)
- Responsive (mobile breakpoint 900px)
- Chart.js 4.x para gráficos

**Componentes:**

| Sección | Qué muestra |
|---------|-------------|
| **Header** | "Brasil2026", fechas del viaje, nro pasajeros, última actualización, tipo de cambio |
| **4 KPI cards** | Total vuelos, directos, destinos, aeropuertos origen |
| **Cards mejores precios** | Top 4 destinos más baratos, con nombre aerolínea, directo/escalas, duración, hora salida, precio ARS+USD, tendencia vs anterior |
| **Gráfico Chart.js** | Líneas de evolución de precio mínimo por destino (ARS), tooltip con formato argentino, legend abajo |
| **Panel alertas** | Últimas 10 alertas de cambio de precio |
| **Tabla completa** | 9 columnas: Destino, Origen, Aerolínea, Tipo (✈/🔄), Duración, Salida, USD, ARS, Tendencia |
| **Filtros** | Input texto destino, input texto aerolínea, select directo/escalas/todos, select orden precio |
| **Footer** | Cantidad de búsquedas históricas |

**JavaScript interactivo:**
- `filterTable()` — filtra rows por destino + aerolínea + tipo (directo/escalas)
- `sortTable()` — ordena por precio ascendente o descendente

---

## 9. vuelos_brasil.py — Buscador manual (187 líneas)

Script interactivo separado que genera links para búsqueda manual:

**Opciones:**
- `a)` Abrir TODOS los destinos en Google Flights (8 tabs)
- `b)` Elegir un destino → abrir en Google Flights
- `c)` Elegir un destino → abrir en 3 comparadores simultáneos

**Comparadores soportados:**
- Google Flights: `google.com/travel/flights/search#flt=EZE.FLN.2026-04-06*FLN.EZE.2026-04-13;c:ARS;px:2`
- Kayak: `kayak.com.ar/flights/EZE-FLN/2026-04-06/20260413/2adults`
- Despegar: `despegar.com.ar/vuelos/oferta/EZE/FLN/20260406/20260413/2-0-0/1/sin-equipaje`

**Airbnb links:** También genera URLs de Airbnb con checkin/checkout, 2 adultos y precio máximo $150 USD/noche para cada ciudad brasileña.

---

## 10. Dependencias Python

```
amadeus          # SDK oficial Amadeus — pip install amadeus
requests         # HTTP para AwesomeAPI — pip install requests
python-dotenv    # Cargar .env — pip install python-dotenv
curl_cffi        # HTTP stealth con impersonación Chrome — pip install curl_cffi
```

**No usadas actualmente pero disponibles en core/:**
- `pandas` (mencionado en AGENTS.md pero no importado)
- `asyncio` (para AsyncHttpClient)

---

## 11. Credenciales y seguridad

```
# .env (92 bytes)
AMADEUS_CLIENT_ID=uSvZIh8BGXEwdGy9Rgy8f4A6LTFiHdfl
AMADEUS_CLIENT_SECRET=bmzaZb76LH1jL0Me
```

- ⚠️ **Entorno TEST de Amadeus** — El constructor `Client()` en línea 30-33 NO pasa `hostname='production'`, así que usa `test.api.amadeus.com` por defecto
- El `.env` NO está en `.gitignore` (no hay `.gitignore` en el proyecto)
- No hay otras credenciales (AwesomeAPI es pública, Flybondi no requiere auth)

---

## 12. Problemas conocidos y limitaciones

| # | Problema | Impacto | Línea(s) | Fix sugerido |
|---|----------|---------|----------|--------------|
| 1 | **Entorno TEST** de Amadeus | Precios pueden estar cacheados | 30-33 | Agregar `hostname='production'` y obtener key prod |
| 2 | **Flybondi no devuelve datos** | Perdés la aerolínea más barata para FLN | 380-469 | Verificar endpoint actual, capturar con DevTools |
| 3 | **JetSmart no integrado** | Otra low-cost no buscada | N/A | Crear función `buscar_jetsmart()` similar a flybondi |
| 4 | **Fechas hardcodeadas** | No podés comparar semanas alternativas | 47-48 | Aceptar como args de CLI o buscar rango de fechas |
| 5 | **Sin scheduler** | Hay que ejecutar manualmente | 901-902 | Agregar cron o `run_forever()` del BaseSniffer |
| 6 | **Sin notificaciones push** | No te avisa si baja un precio | N/A | Integrar TelegramNotifier de FRAVEGA/core/ |
| 7 | **Dashboard estático** | Se regenera completo, no es live | 474-815 | Mover a server HTTP como en vuelos/core/dashboard/ |
| 8 | **Sin .gitignore** | Credenciales expuestas si se sube a git | N/A | Crear .gitignore con .env, data/, __pycache__/ |
| 9 | **FLN aparece como "más barato" pero tiene 29h** | Engañoso — el directo GIG USD 728 es mejor opción | N/A | Mostrar precio ajustado por conveniencia (bonus directo) |
| 10 | **No valida si Amadeus devuelve datos test** | No hay forma de saber si los precios son live o cached | N/A | Comparar con Google Flights manualmente |

---

## 13. Documentación existente

### AGENTS.md (34 líneas)
Define: objetivo (vuelo más barato EZE→Brasil, 2 adultos), destinos, presupuesto ($1.5M ARS), stack técnico (Python 3.13, curl_cffi, AsyncSession, BS4), intentos fallidos (Playwright bloqueado por Cloudflare), estrategia actual, reglas para agentes.

### APIS_RESEARCH.md (57 líneas)
Tabla de APIs investigadas:
- **Vuelos:** Amadeus (elegida), Aviationstack, Compare Flight Prices (RapidAPI), Sabre, OpenSky, AviationAPI, AviationWeather, AirportsAPI
- **Transporte:** Tripadvisor, Impala Hotel, Uber, Grab, GraphHopper, Navitia, TransitLand
- **Moneda:** AwesomeAPI (elegida), Currency-api, Exchangerate.host, Frankfurter
- **Conclusión:** Amadeus + AwesomeAPI + AirportsAPI

### RESEARCH.md (183 líneas)
Research técnico de:
1. curl_cffi — bypass Cloudflare con impersonación, sesiones, proxies, async
2. agents.md — estándar de comunicación para AI agents
3. MCP (Model Context Protocol) — ejemplo de servidor FastMCP para vuelos
4. Skills — web-scraping, python-executor, async-python de skills.sh

---

## 14. Proyectos relacionados con código reutilizable

| Proyecto | Ruta | Qué tiene útil | Integrado en Brasil2026 |
|----------|------|----------------|------------------------|
| `vuelos/` (Odiseo) | `PROYECTOS PERSONALES/vuelos/` | HttpClient, BaseSniffer, Database, FlybondiSniffer, Dashboard server con API REST | ✅ core/ copiado |
| `FRAVEGA/` | `PROYECTOS PERSONALES/FRAVEGA/` | TelegramNotifier (81 líneas), AsyncHttpClient, Deploy Railway (Dockerfile), 6 targets e-commerce (fravega, cetrogar, megatone, oncity, casadelaudio, newsan) | ❌ No integrado |
| `Buscador-vuelos/` | `PROYECTOS PERSONALES/Buscador-vuelos/` | buscar_vuelos.py con Amadeus raw requests (sin SDK), filtrar_vuelos(), formatear_duracion() | ✅ Lógica integrada |
| `PRECIOS/` | `PROYECTOS PERSONALES/PRECIOS/` | engine_precios.py con pandas, fuzzy matching con rapidfuzz, generador HTML premium | ❌ No integrado |

---

## 15. Cómo ejecutar

```bash
cd "c:\Users\Facun\OneDrive\Escritorio\PROYECTOS PERSONALES\BRASIL2026"

# Instalar dependencias
pip install amadeus requests python-dotenv curl_cffi

# Ejecutar búsqueda completa (tarda ~2-3 minutos)
python scraper.py

# Ejecutar buscador manual (abre tabs en el navegador)
python vuelos_brasil.py
```

---

## 16. Próximos pasos sugeridos (priorizado)

| Prioridad | Acción | Esfuerzo | Impacto |
|-----------|--------|----------|---------|
| 🔴 1 | Confirmar si los precios Amadeus TEST son confiables (comparar con Google Flights) | 10 min | Alto — determina si todo el sistema es útil |
| 🔴 2 | Investigar endpoint actual de Flybondi con DevTools del navegador | 30 min | Alto — low-cost suele ser más barata |
| 🟡 3 | Agregar JetSmart como fuente (scraping stealth similar a Flybondi) | 2h | Medio — otra low-cost relevante |
| 🟡 4 | Integrar TelegramNotifier de FRAVEGA para alertas al celular | 30 min | Medio — te avisa cuando baja |
| 🟡 5 | Hacer fechas parametrizables (CLI args o buscar semana más barata) | 1h | Medio — puede encontrar precios mejores |
| 🟢 6 | Agregar scheduler (cron o BaseSniffer.run_forever) | 30 min | Medio — búsquedas automáticas |
| 🟢 7 | Crear .gitignore para proteger credenciales | 2 min | Bajo pero importante si se sube a git |
