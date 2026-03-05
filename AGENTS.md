# BRASIL2026 - Flight Tracker

## IMPORTANTE: Leer STATUS.md primero
Antes de hacer cualquier cosa, leé el archivo `STATUS.md` en la raíz del proyecto.
Tiene el resumen ejecutivo completo: arquitectura, datos, resultados, limitaciones, y próximos pasos.

## Objetivo
Encontrar el vuelo más barato Buenos Aires → Brasil para 2 adultos.
Fechas: 6-13 abril 2026 (~7 noches). Presupuesto total vuelo+airbnb: máximo $1.500.000 ARS.

## Destinos objetivo
FLN (Florianópolis), GIG (Río de Janeiro), SSA (Salvador), BPS (Porto Seguro), NAT (Natal), MCZ (Maceió), REC (Recife), FOR (Fortaleza)

## Cómo ejecutar
```bash
pip install amadeus requests python-dotenv curl_cffi
python scraper.py
```

## Archivos clave
- `scraper.py` — Script principal (903 líneas). Busca vuelos, guarda en SQLite, genera dashboard
- `STATUS.md` — Resumen ejecutivo ultra-detallado de todo el proyecto (LEER PRIMERO)
- `vuelos_brasil.py` — Buscador manual, abre links en Google Flights/Kayak/Despegar
- `dashboard.html` — Dashboard autogenerado con Chart.js
- `.env` — Credenciales Amadeus API
- `core/` — Módulos compartidos (HttpClient stealth, BaseSniffer, Database SQLite)
- `data/brasil2026.db` — Base de datos SQLite con vuelos, historial y alertas
- `APIS_RESEARCH.md` — Investigación de APIs disponibles
- `RESEARCH.md` — Research de curl_cffi, MCP, scraping stealth

## Stack técnico
- Python 3.13
- Amadeus SDK (fuente principal de vuelos — ENTORNO TEST, no producción)
- curl_cffi con impersonación Chrome (para scraping stealth de Flybondi)
- SQLite (base de datos local)
- AwesomeAPI (tipo de cambio USD→ARS)
- Chart.js (gráficos en dashboard)

## Estado actual
- Última búsqueda: 2026-03-04 — 63 vuelos encontrados, 7 directos (todos a GIG)
- Mejor precio: GIG (Río) directo USD 728 con Aerolíneas desde AEP
- Flybondi integrado pero sin resultados confirmados del endpoint
- JetSmart no integrado todavía

## Reglas para el agente
- Nunca usar requests vanilla para scraping, siempre curl_cffi con impersonación
- Guardar resultados en la base de datos SQLite (`data/brasil2026.db`)
- No modificar STATUS.md manualmente (se regenera)
- Credenciales van en .env, nunca hardcodeadas
