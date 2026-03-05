#!/usr/bin/env python3
"""
Script para buscar vuelos BUE → Brasil en Google Flights
Viaje: 2 personas, ~6-7 días, segunda semana de abril 2026
Abre el navegador con los links ya armados para cada destino
"""

import webbrowser
import time
from urllib.parse import urlencode

# ─── CONFIGURACIÓN DEL VIAJE ────────────────────────────────────────────────

ORIGEN = "EZE"          # Ezeiza (podés cambiar a AEP para vuelos de cabotaje)
FECHA_IDA = "2026-04-06"
FECHA_VUELTA = "2026-04-13"  # 7 días
PASAJEROS = 2

# Destinos Brasil con vuelo directo desde BUE
DESTINOS = {
    "Florianópolis":  "FLN",
    "Río de Janeiro": "GIG",   # Galeão (internacionales)
    "Salvador Bahía": "SSA",
    "Porto Seguro":   "BPS",
    "Natal":          "NAT",
    "Maceió":         "MCZ",
    "Recife":         "REC",
    "Fortaleza":      "FOR",
}

# ─── FUNCIONES ───────────────────────────────────────────────────────────────

def google_flights_url(origen, destino, fecha_ida, fecha_vuelta, pasajeros):
    """Genera URL de Google Flights para ida y vuelta"""
    base = "https://www.google.com/travel/flights/search"
    params = {
        "tfs": f"CBwQAhoeEgoyMDI2LTA0LTA2agcIARIDe3tvcmlnZW59fXIHCAESA3t7ZGVzdH19GhgSCjIwMjYtMDQtMTNqBwgBEgN7e2Rlc3R9fXIHCAESA3t7b3JpZ2VufX0",
    }
    # URL directa más simple y funcional
    url = (
        f"https://www.google.com/travel/flights?"
        f"q=vuelos+{origen}+a+{destino}"
        f"+{fecha_ida}+vuelta+{fecha_vuelta}"
        f"+{pasajeros}+pasajeros"
    )
    return url

def google_flights_url_real(origen, destino, fecha_ida, fecha_vuelta, pasajeros):
    """
    URL real de Google Flights con parámetros correctos
    Formato: /travel/flights/search#flt=EZE.FLN.2026-04-06*FLN.EZE.2026-04-13;c:ARS;e:1;px:2;sd:1;t:f
    """
    flt_param = f"{origen}.{destino}.{fecha_ida}*{destino}.{origen}.{fecha_vuelta}"
    url = (
        f"https://www.google.com/travel/flights/search"
        f"#flt={flt_param}"
        f";c:ARS"        # moneda: pesos argentinos
        f";e:1"          # vuelos directos preferidos
        f";px:{pasajeros}"  # cantidad de pasajeros
        f";sd:1"         # ordenar por precio
        f";t:f"          # tipo: vuelo
    )
    return url

def kayak_url(origen, destino, fecha_ida, fecha_vuelta, pasajeros):
    """URL de Kayak para comparar"""
    fecha_ida_fmt = fecha_ida.replace("-", "")    # 20260406
    fecha_vuelta_fmt = fecha_vuelta.replace("-", "")
    url = (
        f"https://www.kayak.com.ar/flights/"
        f"{origen}-{destino}/{fecha_ida}/{fecha_vuelta_fmt}"
        f"/{pasajeros}adults"
    )
    return url

def despegar_url(origen, destino, fecha_ida, fecha_vuelta, pasajeros):
    """URL de Despegar"""
    url = (
        f"https://www.despegar.com.ar/vuelos/oferta/{origen}/{destino}/"
        f"{fecha_ida.replace('-','')}/{fecha_vuelta.replace('-','')}/"
        f"{pasajeros}-0-0/1/sin-equipaje"
    )
    return url

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  BUSCADOR DE VUELOS BUE → BRASIL - ABRIL 2026")
    print("=" * 60)
    print(f"  Fecha ida:    {FECHA_IDA}")
    print(f"  Fecha vuelta: {FECHA_VUELTA}")
    print(f"  Pasajeros:    {PASAJEROS}")
    print("=" * 60)
    print()

    print("Destinos disponibles:")
    destinos_lista = list(DESTINOS.items())
    for i, (nombre, codigo) in enumerate(destinos_lista, 1):
        print(f"  {i}. {nombre} ({codigo})")

    print()
    print("Opciones:")
    print("  a) Abrir TODOS en Google Flights (abre varias pestañas)")
    print("  b) Elegir un destino específico")
    print("  c) Abrir un destino en los 3 comparadores (GFlights + Kayak + Despegar)")
    print()

    opcion = input("¿Qué hacemos? (a/b/c): ").strip().lower()

    if opcion == "a":
        print("\nAbriendo Google Flights para todos los destinos...")
        print("(Se abren de a una para no saturar el navegador)\n")
        for nombre, codigo in destinos_lista:
            url = google_flights_url_real(ORIGEN, codigo, FECHA_IDA, FECHA_VUELTA, PASAJEROS)
            print(f"  → {nombre}: {url}")
            webbrowser.open(url)
            time.sleep(1.5)

    elif opcion == "b":
        print()
        num = int(input("Ingresá el número del destino: "))
        nombre, codigo = destinos_lista[num - 1]
        url = google_flights_url_real(ORIGEN, codigo, FECHA_IDA, FECHA_VUELTA, PASAJEROS)
        print(f"\nAbriendo {nombre} en Google Flights...")
        print(f"URL: {url}")
        webbrowser.open(url)

    elif opcion == "c":
        print()
        num = int(input("Ingresá el número del destino: "))
        nombre, codigo = destinos_lista[num - 1]

        urls = {
            "Google Flights": google_flights_url_real(ORIGEN, codigo, FECHA_IDA, FECHA_VUELTA, PASAJEROS),
            "Kayak":          kayak_url(ORIGEN, codigo, FECHA_IDA, FECHA_VUELTA, PASAJEROS),
            "Despegar":       despegar_url(ORIGEN, codigo, FECHA_IDA, FECHA_VUELTA, PASAJEROS),
        }

        print(f"\nAbriendo {nombre} en los 3 comparadores...")
        for sitio, url in urls.items():
            print(f"\n  {sitio}:")
            print(f"  {url}")
            webbrowser.open(url)
            time.sleep(1.5)

    print("\n✓ Listo! Fijate en las pestañas del navegador.")
    print("\nTip: En Google Flights activá 'Solo vuelos directos' y")
    print("cambiá la moneda a ARS para ver precios en pesos.\n")

    # ── Links de Airbnb para los destinos ──────────────────────────────────
    print("─" * 60)
    print("AIRBNB - Links por destino (para buscar alojamiento):")
    print("─" * 60)

    airbnb_ciudades = {
        "Florianópolis":  "florianopolis--santa-catarina--brasil",
        "Río de Janeiro": "rio-de-janeiro--rio-de-janeiro--brasil",
        "Salvador Bahía": "salvador--bahia--brasil",
        "Porto Seguro":   "porto-seguro--bahia--brasil",
        "Natal":          "natal--rio-grande-do-norte--brasil",
        "Maceió":         "maceio--alagoas--brasil",
        "Recife":         "recife--pernambuco--brasil",
        "Fortaleza":      "fortaleza--ceara--brasil",
    }

    checkin = FECHA_IDA
    checkout = FECHA_VUELTA
    adultos = PASAJEROS

    for nombre, slug in airbnb_ciudades.items():
        url_airbnb = (
            f"https://www.airbnb.com.ar/s/{slug}/homes"
            f"?checkin={checkin}&checkout={checkout}"
            f"&adults={adultos}"
            f"&price_max=150"  # hasta ~150 USD la noche, ajustable
        )
        print(f"\n  {nombre}:")
        print(f"  {url_airbnb}")

    print()
    print("Tip Airbnb: filtrá por 'Departamento entero', precio máximo")
    print("y calificación +4.8 para encontrar lo mejor.\n")


if __name__ == "__main__":
    main()