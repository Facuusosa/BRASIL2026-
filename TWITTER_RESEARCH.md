# TWITTER_RESEARCH.md - Análisis de Claude Cowork

Análisis del hilo/recurso compartido por @ecommartinez sobre las nuevas capacidades de Claude.

---

### 📝 Resumen del Recurso: Claude Cowork

El recurso detalla la funcionalidad de **Claude Cowork**, una evolución de los agentes de IA que permite una integración profunda con el sistema de archivos y ejecución de código en entornos aislados.

#### Conceptos Clave
- **Entorno de Ejecución (Sandbox)**: Cowork opera dentro de una VM Linux ligera (~2GB) descargada localmente. Esto permite que el agente ejecute scripts de Python, Node.js o Bash sin poner en riesgo el sistema principal del usuario.
- **Acceso a Archivos**: A diferencia de los chats tradicionales, Cowork tiene visibilidad completa sobre los archivos del proyecto (si se le otorga permiso). Puede leer, editar y organizar la estructura de carpetas de forma autónoma.
- **Flujos Multi-Agente**: Permite que Claude delegue tareas a subagentes especializados, facilitando tareas complejas como el scraping masivo o el procesamiento de grandes volúmenes de datos.

#### Capacidades Específicas
- **Manipulación de Documentos**: Generación y edición de archivos Office (Excel, Word, PowerPoint) de forma nativa.
- **Integración Enterprise**: Conectores para herramientas como Sabre (vuelos), Salesforce y Slack.
- **Scheduling**: Capacidad para programar tareas recurrentes.

---

### 🚀 Aplicación Práctica a BRASIL2026

1.  **Orquestación del Scraper**: Podemos usar Cowork para que sea el encargado de lanzar el script de `curl_cffi` cada X horas, verifique si hay nuevos datos y los guarde ordenadamente.
2.  **Reporte de Ahorro**: Cowork puede leer los JSON en `/data/`, compararlos con el presupuesto de **$1.500.000 ARS** y generar automáticamente una hoja de Excel con la evolución de precios.
3.  **Mantenimiento de Selectores**: Gracias a su capacidad de lectura de archivos, Cowork puede detectar si el scraper falla por un cambio en la UI de Despegar y proponer correcciones al código de forma proactiva.
