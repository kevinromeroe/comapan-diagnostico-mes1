# Diagnóstico Comapan — Reportería de Redes Sociales

Entregable confidencial generado por **Datalítica Colombia S.A.S.** para **Catorce Días Colombia**, sobre las cuentas digitales de **Comapan**.

© 2026 Datalítica Colombia S.A.S. — Todos los derechos reservados. El acceso, copia o distribución no autorizada de este material está prohibido.

---

## Qué es este repositorio

Este repositorio aloja dos cosas claramente separadas:

1. **El sitio publicado** en `comapan.datalitica.com.co` — los archivos en la raíz (`index.html`, `assets/`, `CNAME`) son los artefactos que GitHub Pages sirve.
2. **El pipeline ETL** que genera ese sitio automáticamente cada quincena a partir de los datos extraídos vía Apify de las plataformas de Comapan.

Los datos crudos, los CSVs, los JSONs intermedios y los scripts con credenciales **nunca** se commitean. El `.gitignore` es de tipo whitelist: solo lo explícitamente permitido entra al repo.

## Estructura

```
.
├── index.html              ⬅ página inicial (copia del diagnóstico Ene–May 2026)
├── diagnostico/            ⬅ diagnóstico Ene–May 2026 (index.html + reporte.pdf)
├── 2026-MM/                ⬅ un informe por mes (index.html + reporte.pdf)
├── CNAME, robots.txt       ⬅ configuración GitHub Pages
├── assets/                 ⬅ logos, favicons, thumbnails de top posts
│
├── docs/                   ⬅ documentación viva del proyecto
│   ├── ARCHITECTURE.md
│   ├── RUNBOOK.md
│   ├── DATA_DICTIONARY.md
│   ├── INSIGHTS_FRAMEWORK.md
│   ├── ONBOARDING_CLIENT.md
│   └── apify_schemas/      ⬅ shapes de cada actor de Apify
│
├── config/                 ⬅ configuración por cliente
│   └── clients/
│       └── comapan.yaml
│
├── pipeline/               ⬅ código Python del ETL
│   ├── extract/            consume APIs de Apify y GA4
│   ├── transform/          raw → shape canónico DATA
│   ├── load/               escribe JSON + descarga thumbnails
│   ├── render/             template + DATA → HTML final
│   ├── publish/            commit + push al repo público
│   └── notify/             email/Slack al equipo
│
├── scripts/                ⬅ herramientas operacionales
├── tests/                  ⬅ tests + fixtures de respuestas Apify
└── .github/workflows/      ⬅ CI/CD: cron y manual triggers
```

## Cómo se actualiza el reporte

Cadencia: **semanal**, todos los martes a las 21:00 hora Bogotá (miércoles 02:00 UTC), por el cron de `ingest_monthly.yml`.

Flujo automático (cada workflow arranca solo si el anterior terminó OK, vía `workflow_run`):

```
Ingest mensual        → corre los actores de Apify (IG, FB, TT, LI) del mes en curso
                      → inserta/actualiza posts en Supabase
                      → commit de miniaturas en assets/thumbs/
Build diagnóstico     → lee Supabase, recalcula agregados, Gemini taggea posts nuevos
                      → regenera diagnostico/, 2026-MM/ e index.html
                      → actualiza la evolución mes a mes
                      → commit && push + smoke test del mes actual (HTTP 200)
Render PDF            → Playwright genera <periodo>/reporte.pdf
                      → commit && push
GitHub Pages          → republica automático
```

Tiempo total aproximado: **10–15 minutos** entre el inicio de la ingesta y los PDF publicados.

## Cliente y cuentas analizadas

**Cliente que paga**: Catorce Días Colombia S.A.S. (NIT 901.732.649-9)
**Cuenta final analizada**: Comapan

| Plataforma | Handle |
|---|---|
| Instagram | @comapan_co |
| Facebook | ComapanCo |
| TikTok | @comapanco |
| LinkedIn | comapan-s-a- |
| Página web | comapan.com.co *(pendiente acceso GA4)* |

## Para empezar a colaborar

1. Lee `docs/ARCHITECTURE.md` para entender por qué cada cosa está donde está.
2. Lee `docs/RUNBOOK.md` para saber cómo correr el pipeline local y cómo debuggear.
3. Lee `docs/INSIGHTS_FRAMEWORK.md` para entender la rigurosidad analítica que el output debe respetar.
4. Para agregar un cliente nuevo, sigue `docs/ONBOARDING_CLIENT.md`.

## Seguridad

- Credenciales (Apify token, GitHub PAT) viven en **GitHub Secrets**, jamás en el código.
- Los datos crudos del cliente jamás se commitean — el `.gitignore` bloquea explícitamente CSVs, JSONs de data y raw responses.
- El sitio publicado tiene `robots.txt` bloqueando indexación.
- Política de rotación: Apify cada 6 meses, GitHub PAT anual.

## Stack

- **Lenguaje**: Python 3.11+
- **Orquestación**: GitHub Actions + Apify Schedules
- **Visualización**: Chart.js 4.4 (CDN), HTML estático
- **Tipografía**: Roboto Slab + Roboto (Google Fonts)
- **Deploy**: GitHub Pages con dominio custom

## Contacto

Datalítica Colombia S.A.S.
comercial@datalitica.com.co
+57 322 835 2172

## Workflows disponibles

El repo tiene 4 workflows. Todos se pueden disparar a mano (`workflow_dispatch`); además, la ingesta y el keepalive corren por cron, y el build y el PDF se encadenan solos al terminar el paso anterior.

| Workflow | Cuándo corre | Qué hace |
|---|---|---|
| **`ingest_monthly.yml`** | Cron martes 21:00 Bogotá, o manual (período `YYYY-MM`, vacío = mes actual) | Corre los actores de Apify (IG, FB pages, FB posts, **TikTok profile únicamente**, LinkedIn), filtra al mes (Bogotá), inserta/actualiza posts en Supabase, descarga miniaturas y hace commit |
| **`build_diagnostico_extendido.yml`** | Automático al terminar OK la ingesta, o manual (`all` por defecto) | Lee Supabase, recomputa agregados y heatmaps filtrando al período, corre Gemini para taggear posts nuevos, regenera hallazgos + resumen y publica en `comapan.datalitica.com.co/<periodo>/` |
| **`render_pdf.yml`** | Automático al terminar OK el build, o manual (períodos separados por espacio, vacío = todos) | Sirve el sitio localmente, renderiza `<periodo>/reporte.pdf` con Playwright (A4 horizontal) y hace commit |
| **`keepalive_supabase.yml`** | Automático (cron lunes 06:00 Bogotá) | Ping simple a Supabase para que no se pause por inactividad (plan free) |

### Flujo típico para actualizar el dashboard a mano

1. Actions → **Ingest mensual** → Run workflow (~3 min)
2. El **Build diagnóstico extendido HTML** arranca solo al terminar (~3 min)
3. El **Render PDF de informes** arranca solo al terminar el build
4. Verificar en `https://comapan.datalitica.com.co/<mes-actual>/` (recarga forzada: Ctrl+Shift+R)

### Nota TikTok

Desde el fix del 2026-07-21, la ingesta usa **solo** el actor `clockworks/tiktok-profile-scraper` (ID `0FXVyOXXEmdGcV88a`), que retorna cuenta + posts frescos en un mismo dataset. Se descartó `clockworks/tiktok-scraper` (`GdWCkxBtKWOsKjdch`) porque devolvía dataset stale de forma intermitente.
