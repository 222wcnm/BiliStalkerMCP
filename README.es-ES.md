# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![PyPI version](https://badge.fury.io/py/bili-stalker-mcp.svg)](https://pypi.org/project/bili-stalker-mcp/)

## Servidor MCP de Bilibili para Análisis de Usuarios Específicos

BiliStalkerMCP es un servidor MCP de Bilibili construido sobre el [Model Context Protocol (MCP)](https://modelcontextprotocol.io), diseñado para agentes de IA que necesiten analizar a un usuario o creador específico de Bilibili.

Está optimizado para flujos de trabajo que comienzan con un uid o nombre de usuario objetivo, y luego recuperan el perfil, videos, dinámicas, artículos, subtítulos y seguidos de dicho usuario mediante herramientas estructuradas.

Si estás buscando un servidor MCP de Bilibili, un servidor del Model Context Protocol de Bilibili, o un servidor MCP para rastrear y analizar a un usuario específico de Bilibili, este repositorio está diseñado para ese caso de uso.

**English | [中文说明](README_zh.md)**

### Instalación

```bash
uvx bili-stalker-mcp
# o
pip install bili-stalker-mcp
```

### Configuración (Claude Desktop, Recomendado)

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/BiliStalkerMCP", "bili-stalker-mcp"],
      "env": {
        "SESSDATA": "required_sessdata",
        "BILI_JCT": "optional_jct",
        "BUVID3": "optional_buvid3"
      }
    }
  }
}
```

> Se prefiere `uv run --directory ...` para actualizaciones locales más rápidas cuando la propagación de la versión de PyPI se retrasa.
> Aún puedes usar `uvx bili-stalker-mcp` para un uso rápido y puntual.

> **Autenticación**: Proporciona `SESSDATA` directamente, o colócalo en `BILI_COOKIE_FILE`. Obtenlo desde las Herramientas de Desarrollador del Navegador (F12) > Application > Cookies > `.bilibili.com`.

### Variables de Entorno

| Clave | Req | Descripción |
|-----|:---:|-------------|
| `SESSDATA` | Condicional | Token de sesión de Bilibili; requerido a menos que `BILI_COOKIE_FILE` lo proporcione. |
| `BILI_JCT` | No | Token de protección CSRF. |
| `BUVID3` | No | Huella digital del hardware (reduce el riesgo de limitación de tasa/rate-limiting). |
| `BILI_COOKIE_FILE` | No | Ruta a un archivo de Cookie plano. |
| `BILI_REFRESH_TOKEN_FILE` | No | Ruta al archivo separado de refresh-token; nunca establezcas el token a través de una variable de entorno. |
| `BILI_ENABLE_COOKIE_REFRESH` | No | `true` habilita la actualización automática segura; predeterminado: `false`. |
| `BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS` | No | Intervalo de verificación de actualización; predeterminado: `21600`, mínimo: `60`. |
| `BILI_LOG_LEVEL` | No | `DEBUG`, `INFO` (Predeterminado), `WARNING`. |
| `BILI_TIMEZONE` | No | Zona horaria de salida para marcas de tiempo formateadas (predeterminado: `Asia/Shanghai`). |

### Actualización Segura de Cookies Opcional

La actualización automática está desactivada por defecto. Habilítala solo cuando el archivo de Cookie y el archivo de refresh-token sean archivos regulares existentes, legibles y escribibles. El archivo de Cookie puede contener solo valores de Cookie ordinarios (`SESSDATA`, `bili_jct`, `buvid3`, `buvid4`, y `DedeUserID`); el refresh token debe pertenecer únicamente a su propio archivo.

```json
{
  "BILI_COOKIE_FILE": "/secure/bilibili-cookie.txt",
  "BILI_REFRESH_TOKEN_FILE": "/secure/bilibili-refresh-token.txt",
  "BILI_ENABLE_COOKIE_REFRESH": "true",
  "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS": "21600"
}
```

Cuando la actualización está habilitada, no establezcas `SESSDATA`, `BILI_JCT` o `DEDEUSERID` en el entorno: esos valores rotativos deben provenir del archivo de Cookie para que un reinicio no recargue credenciales obsoletas. `BUVID3` y `BUVID4` aún pueden proporcionarse a través del entorno. Las verificaciones de actualización tienen un límite de tasa, y las llamadas concurrentes a MCP o procesos del servidor que compartan estos archivos utilizan un solo bloqueo de actualización. La confirmación pendiente se recupera antes de otra actualización. El archivo adjunto `.bili-cookie-refresh.lock` puede permanecer en el disco entre ejecuciones.

Para una configuración inicial más rápida, copia el valor completo del encabezado Cookie de una solicitud del navegador de Bilibili y el `ac_time_value` del Local Storage, luego ejecuta:

```powershell
uv run bili-stalker-cookie-setup --directory D:\BiliStalkerSecrets
```

Para una invocación solo mediante PyPI sin clonar este repositorio:

```powershell
uvx --from bili-stalker-mcp bili-stalker-cookie-setup --directory D:\BiliStalkerSecrets
```

El script oculta ambos valores pegados, rechaza directorios dentro del repositorio y archivos de credenciales existentes, e imprime solo un bloque `env` de MCP no secreto. No pegues un comando cURL completo: pega solo el valor después de su encabezado `cookie:`.

### Verificación Local

Todos los comandos de verificación utilizan mocks y no requieren credenciales de Bilibili:

```powershell
uv run pytest -q tests/test_credentials.py tests/test_cookie_refresh.py tests/test_tool_contract.py
uv run pytest -q
uv run black --check bili_stalker_mcp tests scripts
uv run isort --check-only bili_stalker_mcp tests scripts
uv run flake8 bili_stalker_mcp tests scripts
uv run mypy bili_stalker_mcp
```

## Herramientas Disponibles

| Herramienta | Capacidad | Parámetros |
|------|------------|------------|
| `get_user_info` | Perfil y estadísticas principales | `user_id_or_username` |
| `get_user_videos` | Lista de videos ligera | `user_id_or_username`, `page`, `limit` |
| `search_user_videos` | Búsqueda por palabra clave en la lista de videos de un usuario | `user_id_or_username`, `keyword`, `page`, `limit` |
| `get_video_detail` | Detalle completo del video + subtítulos opcionales | `bvid`, `fetch_subtitles` (predeterminado: `false`), `subtitle_mode` (`smart`/`full`/`minimal`), `subtitle_lang` (predeterminado: `auto`), `subtitle_max_chars` |
| `get_user_dynamics` | Dinámicas estructuradas con metadatos de imagen y paginación por cursor | `user_id_or_username`, `cursor`, `limit`, `dynamic_type` |
| `get_user_articles` | Lista de artículos ligera | `user_id_or_username`, `page`, `limit` |
| `get_article_content` | Contenido completo del artículo en markdown | `article_id` |
| `get_user_followings` | Análisis de la lista de suscripciones | `user_id_or_username`, `page`, `limit` |
| `get_content_comments` | Comentarios de un video, artículo o dinámica (incluyendo imágenes y metadatos de notas) | `content_type`, `content_id`, `cursor`, `limit`, `sort` |
| `get_content_comment_replies` | Sub-respuestas completas para un comentario de video, artículo o dinámica | `content_type`, `content_id`, `root_rpid`, `page`, `limit` |

Las `pictures` de los comentarios contienen las URLs originales de las imágenes. Los comentarios largos regulares conservan el texto completo devuelto por Bilibili. Los comentarios estilo nota pueden contener solo una vista previa; usa el `note.cvid` devuelto con `get_article_content` para recuperar la nota completa. Para comentarios de video, pasa `content_type="video"` y un BVID, número AV o URL de video como `content_id`. Usa el `rpid` de un comentario de nivel superior como `root_rpid` al obtener el hilo completo de respuestas.

### Filtrado de Dinámicas (`dynamic_type`)

- `ALL` (predeterminado): Texto, Dibujo y Reposts.
- `ALL_RAW`: Sin filtrar (incluye Videos y Artículos).
- `VIDEO`, `ARTICLE`, `DRAW`, `TEXT`: Filtrado por categoría específica.
- `REVIEW`: Solo tarjetas de calificación de cinco ranuras reconocidas. Cada resultado expone `review.rating` (estrellas llenas, 0-5), `review.title`, `review.text`, URLs de portada y de salto, además de la descripción de la puntuación de origen cuando esté disponible. Este filtro no clasifica independientemente si el título calificado es un anime.

Cada elemento dinámico incluye una lista de `images`. Cada imagen contiene `url`, `width` y `height`; las URLs inválidas se omiten y las dimensiones no disponibles son `null`. `image_count` siempre equivale al número de imágenes devueltas. Los Reposts exponen los mismos campos bajo `origin.images` y `origin.image_count`. Las dinámicas que no son imágenes devuelven una lista de `images` vacía.

**Paginación**: Las respuestas incluyen `next_cursor`. Pásalo a las solicitudes posteriores para un desplazamiento fluido.

### Modos de Subtítulos (`get_video_detail`)

- `smart` (predeterminado cuando `fetch_subtitles=true`): obtiene metadatos de todas las páginas, descarga solo el texto de la pista de subtítulos que mejor coincida.
- `full`: descarga el texto de todas las pistas de subtítulos (mayor costo).
- `minimal`: omite la obtención de metadatos y texto de subtítulos.

`subtitle_lang` puede forzar un idioma (por ejemplo, `en-US`); `auto` utiliza un sistema de prioridad interno.  
`subtitle_max_chars` limita el tamaño del texto de subtítulos devuelto para evitar la explosión de tokens.

## Habilidad Incluida

El repositorio incluye una habilidad para agentes de IA lista para usar en `skills/bili-content-analysis/`:

```
skills/bili-content-analysis/
├── SKILL.md                        # Flujo de trabajo y contrato de salida
└── references/
    └── analysis-style.md           # Reglas detalladas de estilo de escritura
```

### Qué hace

Guía a los agentes de IA compatibles (Gemini, Claude, etc.) a través de un flujo de trabajo estructurado de 6 pasos para un análisis profundo de contenido de Bilibili:

1. **Clarificar** el objetivo y el alcance (uid / bvid / palabra clave).
2. **Recolectar** evidencia — primero listas ligeras, detalles pesados solo para elementos de alto valor.
3. **Reconstruir** la estructura de la fuente antes de interpretar (línea de tiempo, capítulos, oradores).
4. **Analizar** — hechos, cadena lógica, suposiciones, temas y cambios.
5. **Retener anclajes** — uid, bvid, article_id, marcas de tiempo, fragmentos clave de la fuente.
6. **Manejar fallos** — declarar bloqueos explícitamente, detener la especulación.

### Uso

Copia la carpeta `bili-content-analysis` en el directorio de habilidades de tu proyecto:

```
<project>/.agent/skills/bili-content-analysis/
```

El agente activará automáticamente la habilidad cuando las solicitudes del usuario involucren el rastreo de creadores de Bilibili, interpretación de transcripciones, reconstrucción de líneas de tiempo o análisis de contenido.

## Desarrollo

```bash
# Configuración
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv sync --dev

# Test
uv run pytest -q

# Integración y Rendimiento (Requiere Autenticación)
uv run python scripts/integration_suite.py -u <UID>
uv run python scripts/perf_baseline.py -u <UID> --tools dynamics -n 3
```

## Lanzamiento (Mantenedores)

> **Credenciales**: El script de lanzamiento utiliza `UV_PUBLISH_TOKEN` si está configurado; de lo contrario, lee el token coincidente de `[pypi]` o `[testpypi]` desde `$HOME\.pypirc`.
> Twine se invoca transitoriamente a través de `uvx` solo para la validación de metadatos del paquete y no es una dependencia del proyecto.

```powershell
# Build + test + validación de metadatos del paquete (sin subida)
.\scripts\pypi_release.ps1

# Subir a TestPyPI
.\scripts\pypi_release.ps1 -TestPyPI -Upload

# Subir a PyPI
.\scripts\pypi_release.ps1 -Upload
```

## Docker

Se ejecuta mediante transporte `stdio`. No hay puertos expuestos.

```bash
docker build -t bilistalker-mcp .
docker run -e SESSDATA=... bilistalker-mcp
```

## Solución de Problemas

- **412 Precondition Failed**: El sistema anti-scraping de Bilibili fue activado. Actualiza `SESSDATA` o proporciona `BUVID3`.
- **IPs de Nube**: Altamente susceptibles de bloqueo; se recomienda la ejecución local.

## Licencia

MIT

> **Descargo de responsabilidad**: Solo para investigación personal y aprendizaje. Queda prohibido el perfilado masivo, el acoso o la vigilancia comercial.

---
*Este proyecto ha sido construido y mantenido con la ayuda de IA.*
