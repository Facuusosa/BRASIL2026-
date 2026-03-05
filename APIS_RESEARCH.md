# APIS_RESEARCH.md - Proyecto BRASIL2026

Este archivo contiene el relevamiento exhaustivo de APIs públicas para vuelos, viajes, transporte y conversión de moneda, analizadas desde el repositorio `public-apis/public-apis`.

---

### ✈️ Vuelos y Aviación

| Nombre | Documentación | Auth | Precio / Límites |
| :--- | :--- | :--- | :--- |
| **Amadeus for Developers** | [developers.amadeus.com](https://developers.amadeus.com/self-service) | OAuth | Gratis (Uso limitado en Self-Service) |
| **Aviationstack** | [aviationstack.com](https://aviationstack.com/) | OAuth | Free tier (10k req/mes) |
| **Compare Flight Prices** | [rapidapi.com](https://rapidapi.com/obryan-software-obryan-software-default/api/compare-flight-prices/) | apiKey | Depende del plan de RapidAPI |
| **Sabre for Developers** | [developer.sabre.com](https://developer.sabre.com) | apiKey | Uso limitado gratuito |
| **OpenSky Network** | [opensky-network.org](https://opensky-network.org/apidoc/index.html) | No | Gratis (Datos ADS-B en tiempo real) |
| **AviationAPI** | [docs.aviationapi.com](https://docs.aviationapi.com) | No | Gratis (FAA Charts y Airport Info) |
| **AviationWeather** | [aviationweather.gov](https://www.aviationweather.gov/) | No | Gratis (Pronósticos NOAA) |
| **AirportsAPI** | [airport-web.appspot.com](https://airport-web.appspot.com/api/docs/) | No | Gratis (Búsqueda por IATA/ICAO) |

### 🚗 Transporte y Viajes

| Nombre | Documentación | Auth | Descripción |
| :--- | :--- | :--- | :--- |
| **Tripadvisor** | [RapidAPI](https://rapidapi.com/tripadvisor/api/tripadvisor1) | apiKey | Ratings de hoteles, restaurantes y atracciones |
| **Impala Hotel Bookings** | [docs.impala.travel](https://docs.impala.travel/docs/booking-api/) | apiKey | Inventario de hoteles y tarifas reales |
| **Uber** | [developer.uber.com](https://developer.uber.com/) | OAuth | Estimación de precios y pedidos de viajes |
| **Grab** | [developer.grab.com](https://developer.grab.com/docs/) | OAuth | Tarifas y tracking de entregas/viajes |
| **GraphHopper** | [docs.graphhopper.com](https://docs.graphhopper.com/) | apiKey | Ruteo A-to-B con instrucciones giro a giro |
| **Navitia** | [doc.navitia.io](https://doc.navitia.io/) | apiKey | Datos de transporte público y ruteo |
| **TransitLand** | [transit.land](https://www.transit.land/documentation/datastore/api-endpoints.html) | No | Agregador de datos de tránsito global |

### 💵 Conversión de Moneda (ARS/USD/BRL)

Crucial para calcular el presupuesto de **$1.500.000 ARS** frente a gastos en Reales o Dólares.

| Nombre | Documentación | Auth | Ventaja para ARS |
| :--- | :--- | :--- | :--- |
| **AwesomeAPI** | [docs.awesomeapi.com.br](https://docs.awesomeapi.com.br/api-de-moedas) | **No** | **Ideal**: API brasileña, soporta ARS, sin límites |
| **Currency-api** | [fawazahmed0/currency-api](https://github.com/fawazahmed0/currency-api) | **No** | 150+ monedas, totalmente gratis, sin límites |
| **Exchangerate.host** | [exchangerate.host](https://exchangerate.host) | No | Muy sencillo de usar para conversiones rápidas |
| **Frankfurter** | [frankfurter.app/docs](https://www.frankfurter.app/docs) | No | Open source y confiable |

---

### 🏆 MEJOR COMBINACIÓN PARA BRASIL2026

Para optimizar el scraper y cumplir con el presupuesto, la mejor combinación es:

1.  **Vuelos: Amadeus for Developers**
    -   Permite buscar por "precio más bajo" de forma nativa.
    -   **Registro**: [developers.amadeus.com/register](https://developers.amadeus.com/register)
2.  **Moneda: AwesomeAPI (Economia.Awesome)**
    -   Al ser brasileña, tiene el feed más rápido de BRL/ARS.
    -   **Endpoint**: `https://economia.awesomeapi.com.br/json/last/ARS-USD,BRL-USD`
3.  **Aeropuertos: AirportsAPI**
    -   Para validación de códigos IATA (EZE, FLN, GIG, etc.) sin latencia.
