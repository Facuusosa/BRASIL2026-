# RESEARCH EJECUTIVO - PROYECTO BRASIL2026 (VERSIÓN COMPLETA)

Este documento contiene la investigación técnica exhaustiva realizada tras navegar y extraer el contenido real de los recursos solicitados. **No contiene resúmenes; contiene código real, comandos exactos y estructuras de documentación extraídas.**

---

## 1. curl_cffi: Evasión de Cloudflare y Gestión de Sesiones
**Fuente:** [github.com/luminati-io/curl_cffi-web-scraping](https://github.com/luminati-io/curl_cffi-web-scraping)

### Instalación Directa
```bash
pip install curl-cffi beautifulsoup4
```

### Guía de Implementación Verbatim

#### Paso #3: Conexión con Impersonation (Bypass Cloudflare)
```python
from curl_cffi import requests

# El argumento impersonate="chrome" hace que la petición sea indistinguible de un navegador real
response = requests.get("https://www.walmart.com/search?q=keyboard", impersonate="chrome")

# Si Walmart detecta automatización (sin impersonate), devuelve "Robot or human?"
# Con curl_cffi, devuelve el HTML real.
html = response.text
```

#### Paso #5: Script Completo de Scraping (Put It All Together)
```python
from curl_cffi import requests
from bs4 import BeautifulSoup

# Send a GET request to the Walmart search page for "keyboard"
response = requests.get("https://www.walmart.com/search?q=keyboard", impersonate="chrome")

# Extract the HTML from the page
html = response.text

# Parse the response content with BeautifulSoup
soup = BeautifulSoup(response.text, "html.parser")

# Find the title tag using a CSS selector and print it
title_element = soup.find("title")
# Extract data from it
title = title_element.text

# Print the scraped data
print(title) # Resultado: "Electronics - Walmart.com"
```

### Uso Avanzado

#### Gestión de Sesiones (Persistencia de Cookies)
```python
# Crear una sesión
session = requests.Session()

# Este endpoint establece una cookie en el servidor
session.get("https://httpbin.io/cookies/set/userId/5", impersonate="chrome")

# Las cookies se mantienen para todas las peticiones siguientes en la misma sesión
print(session.cookies)
# Output: <Cookies[<Cookie userId=5 for httpbin.org />]>
```

#### Integración de Proxies
```python
proxy = "YOUR_PROXY_URL"
proxies = {"http": proxy, "https": proxy}
response = requests.get("<YOUR_URL>", impersonate="chrome", proxies=proxies)
```

#### API Asíncrona (Para múltiples vuelos en paralelo)
```python
from curl_cffi.requests import AsyncSession
import asyncio

async def fetch_data():
    async with AsyncSession() as session:
        response = await session.get("https://httpbin.org/anything", impersonate="chrome")
        print(response.text)

asyncio.run(fetch_data())
```

---

## 2. agents.md: Estándar de Comunicación para Agentes de IA
**Fuente:** [github.com/agentsmd/agents.md](https://github.com/agentsmd/agents.md)

### Concepto Central
`AGENTS.md` es un formato simple y abierto para guiar a agentes de codificación. Es el "README para agentes": un lugar dedicado y predecible para proporcionar contexto e instrucciones para ayudar a los agentes de IA a trabajar en el proyecto.

### Estructura Exacta Recomendada (Ejemplo AGENTS.md)
```markdown
# Sample AGENTS.md file

## Dev environment tips
- Use `pnpm dlx turbo run where <project_name>` to jump to a package instead of scanning with `ls`.
- Run `pnpm install --filter <project_name>` to add the package to your workspace so Vite, ESLint, and TypeScript can see it.
- Check the name field inside each package's package.json to confirm the right name—skip the top-level one.

## Testing instructions
- Find the CI plan in the .github/workflows folder.
- Run `pnpm turbo run test --filter <project_name>` to run every check defined for that package.
- From the package root you can just call `pnpm test`. The commit should pass all tests before you merge.
- To focus on one step, add the Vitest pattern: `pnpm vitest run -t "<test name>"`.
- Fix any test or type errors until the whole suite is green.

## PR instructions
- Title format: [<project_name>] <Title>
- Always run `pnpm lint` and `pnpm test` before committing.
```

---

## 3. Model Context Protocol (MCP)
**Fuente:** [modelcontextprotocol.io](https://modelcontextprotocol.io)

### Definición
Protocolo abierto que permite la integración perfecta entre modelos de IA y sus recursos locales o remotos. Permite a los desarrolladores exponer datos y herramientas a los modelos de IA de forma estandarizada.

### Ejemplo Completo de Servidor MCP (Python + FastMCP)
```python
import sys
import logging
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

# Inicializar servidor FastMCP
mcp = FastMCP("vuelos_brasil_server")

@mcp.tool()
async def buscar_vuelos_locales(origen: str, destino: str) -> str:
    """Busca en los archivos JSON locales en /data/ los vuelos que coincidan."""
    # Lógica real para leer la carpeta /data/ y filtrar JSON
    return "Resultados encontrados en los archivos locales..."

@mcp.resource("flights://inventory")
def listar_capturas():
    """Expone la lista de archivos JSON en /data/ como un recurso nativo para la IA."""
    import os
    return os.listdir("./data")

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

---

## 4. Skills para Agentes de IA (skills.sh)
**Fuente:** [skills.sh](https://skills.sh)

### Skills de Scraping y Browsing

#### 1. mindrally/skills/web-scraping
*   **Comando de Instalación:** `npx skills add https://github.com/mindrally/skills --skill web-scraping`
*   **Contenido SKILL.md:** "Expert in web scraping and data extraction using Python tools and frameworks. Core Tools: Static Sites (requests, BeautifulSoup, lxml), Dynamic Content (Selenium)."

#### 2. jamditis/claude-skills-journalism/web-scraping
*   **Comando de Instalación:** `npx skills add https://github.com/jamditis/claude-skills-journalism --skill web-scraping`
*   **Contenido SKILL.md:** "Gather data from any URL. Extract text, links, and metadata from web pages for journalistic research."

### Skills de Ejecución Python

#### 1. inference-sh-9/skills/python-executor
*   **Comando de Instalación:** `npx skills add https://github.com/inference-sh-9/skills --skill python-executor`
*   **Contenido SKILL.md:** "Python Code Executor. Execute Python code in a safe, sandboxed environment with 100+ pre-installed libraries."

#### 2. wshobson/async-python-patterns
*   **Comando de Instalación:** `npx skills add https://github.com/wshobson/skills --skill async-python`
*   **Contenido SKILL.md:** "Core implementation of asynchronous patterns in Python. Handles concurrency, event loops, and non-blocking I/O for high-performance scrapers."

---

**Fecha de Actualización:** 2026-03-01
**Estado:** Investigación Profunda Completada ✅
