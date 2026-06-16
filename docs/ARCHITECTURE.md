# Arquitectura del Pipeline

Documento de referencia para entender por qué cada decisión está donde está. Útil para nuevos colaboradores y para auditorías de futuros refactors.

## Principios de diseño (innegociables)

### 1. Config-first

Lo que cambia entre clientes, cuentas o periodos vive en YAML. El código Python no contiene handles, IDs de actores, colores de marca ni nada específico de un cliente. Cambiar de Comapan a otro cliente debe ser editar un archivo de configuración, no tocar código.

### 2. Shape canónico interno

Existe **un único formato de datos** que el pipeline produce: el objeto `DATA` (documentado en `DATA_DICTIONARY.md`). Todo lo demás se adapta a ese shape. Si mañana cambiamos de Apify a APIs oficiales o a otra fuente, solo el extractor cambia. El transform, render, publish quedan intactos.

### 3. Separación E / T / L / R / P / N

Cada etapa del pipeline es un módulo independiente con contrato claro:

| Módulo | Recibe | Devuelve |
|---|---|---|
| **Extract** | config + APIs externas | raw responses (dict/JSON) |
| **Transform** | raw responses | shape canónico DATA |
| **Load** | DATA + recursos externos | data/YYYY-MM-DD.json + thumbs |
| **Render** | template + DATA | index.html |
| **Publish** | index.html + repo target | commit + push exitoso |
| **Notify** | resultado del run | mensaje enviado |

Cada módulo se puede testear, reemplazar o saltar de forma independiente.

### 4. Idempotencia

Correr el pipeline dos veces seguidas produce el mismo output. Esto significa:
- No depende de `now()` para valores que no son timestamps de generación.
- No agrega data (siempre sobrescribe la del periodo).
- Los hash de thumbnails son determinísticos (SHA-1 corto del ID del post).
- Los IDs internos se generan de forma estable.

### 5. Observabilidad

Cada corrida deja:
- Log estructurado JSON en stdout (parseable por GitHub Actions).
- Resumen humano-legible al final (`✅ 3 actores OK · ⚠️ 1 sin data · ❌ 0 fallos`).
- Métricas: ¿cuántos posts se procesaron por plataforma? ¿Cuántos thumbs se descargaron? ¿Cuánto demoró cada etapa?

### 6. Fail-loud, fail-safe

Si una plataforma falla (timeout de Apify, dataset vacío, schema cambió), el pipeline:
- **No aborta** las demás plataformas.
- **Falla loud**: la notificación final marca claramente qué falló y deja stack trace en logs.
- **Fail-safe**: no publica un reporte con plataforma incompleta sin marca visual de "data incompleta para X".

## Capas del sistema

```
┌─────────────────────────────────────────────────────────┐
│ ORCHESTRATION                                           │
│ ├── Apify Schedules (cron quincenal)                    │
│ └── GitHub Actions (recibe webhook, orquesta pipeline)  │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ CONFIG                                                  │
│ ├── config/global.yaml          (defaults compartidos)  │
│ └── config/clients/comapan.yaml (específico cliente)    │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ EXTRACT  (pipeline/extract/)                            │
│ ├── apify_client.py    (wrapper sobre Apify API)        │
│ ├── instagram.py       (apify/instagram-scraper)        │
│ ├── facebook.py        (apify/facebook-posts + pages)   │
│ ├── tiktok.py          (clockworks/tiktok-*)            │
│ ├── linkedin.py        (harvestapi/linkedin-*)          │
│ └── ga4.py             (Google Analytics 4)             │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ TRANSFORM  (pipeline/transform/)                        │
│ ├── normalize.py    (raw response → estructura común)   │
│ ├── aggregate.py    (by_day, by_week, by_hour, by_type) │
│ ├── top_posts.py    (top 5 con engagement + thumbs)     │
│ ├── hashtags.py     (extrae y rankea hashtags)          │
│ └── assemble.py     (ensambla el DATA final)            │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ LOAD  (pipeline/load/)                                  │
│ ├── json_writer.py  (data/YYYY-MM-DD.json, gitignored)  │
│ └── thumbs.py       (descarga + hash + guardar)         │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ RENDER  (pipeline/render/)                              │
│ ├── template.html   (index.html sin const DATA)         │
│ └── build.py        (template + DATA → index.html)      │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ PUBLISH  (pipeline/publish/)                            │
│ └── git.py          (clone, commit, push)               │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│ NOTIFY  (pipeline/notify/)                              │
│ ├── email.py        (SMTP simple, plantilla HTML)       │
│ └── slack.py        (webhook a canal, opcional)         │
└─────────────────────────────────────────────────────────┘
```

## Por qué un solo repo (público) vs multi-repo

**Decisión tomada**: un único repo público (`kevinromeroe/comapan-diagnostico-mes1`).

**Razones**:
- **GitHub Pages gratis** solo aplica a repos públicos en cuenta personal.
- **Los actores de Apify son públicos**: no hay nada secreto en sus IDs.
- **Los handles de las cuentas son información pública**: @comapan_co lo ve cualquiera.
- **El código del pipeline no contiene lógica propietaria sensible**: es plumbing.
- **Una sola fuente de verdad**: deploy + código + docs en el mismo lugar.

**Lo que SÍ debe quedar privado** (vive en GitHub Secrets, jamás en el repo):
- `APIFY_TOKEN`
- `GH_DEPLOY_TOKEN`
- `GA4_SERVICE_ACCOUNT_JSON` (cuando exista)
- `SMTP_PASSWORD` (para notificaciones)

**Lo que SÍ debe quedar fuera del repo** (vive solo localmente y en GitHub Actions tmpfs):
- Raw responses de Apify (CSV, JSON intermedios)
- `data/YYYY-MM-DD.json` (los datos consolidados)
- Cualquier dump del cliente

El `.gitignore` whitelist garantiza esto por defensa en profundidad.

## Por qué Python en lugar de Node/JS

- Mejor ecosistema para data wrangling (pandas-style).
- Pillow para procesamiento de thumbnails.
- Tests más fáciles con pytest + fixtures JSON.
- Workflows de GitHub Actions tienen Python preinstalado.
- El JS solo aparece en el frontend (Chart.js, embebido en template.html).

## Por qué Looker Studio NO

Lo descartamos pese a ser gratis porque:
- No permite el nivel de personalización visual que el cliente espera.
- No tiene Roboto Slab nativo.
- No permite secciones de texto largo con hallazgos.
- Está atado al ecosistema Google (no flexible).
- Genera dependencia de un tercero para algo que controlamos mejor con HTML/Chart.js.

El sitio actual `comapan.datalitica.com.co` es prueba de que HTML estático con Chart.js da mejor producto.

## Cómo el sistema escala a más clientes

Agregar un cliente nuevo significa:

1. Crear `config/clients/<nuevo>.yaml` (copia de Comapan, edita valores).
2. Configurar los inputs de los actores de Apify (handle del nuevo cliente).
3. Crear nuevo repo público para ese cliente (o nueva subruta).
4. Agregar un workflow en `.github/workflows/<nuevo>.yml` que apunta a su YAML.
5. Listo. El código se reusa 100%.

Ver `ONBOARDING_CLIENT.md` para el procedimiento exacto.

## Decisiones futuras pendientes

Lista de cosas que vale la pena resolver más adelante, ordenadas por prioridad:

- **GA4 access**: cuando Catorce Días desbloquee acceso, activar el módulo `extract/ga4.py`.
- **Auth en el sitio público**: agregar Cloudflare Access con SSO contra dominios autorizados.
- **Histórico de snapshots**: hoy guardamos solo el último; vale la pena guardar histórico de seguidores para gráficos longitudinales.
- **Generación de hallazgos con LLM**: agregar paso post-transform que llama Claude API con DATA + INSIGHTS_FRAMEWORK y genera la sección de hallazgos. JSON Schema validado.
- **Apify token con scope restringido**: rotar al token actual por uno con permisos solo a los 6 actores específicos.
