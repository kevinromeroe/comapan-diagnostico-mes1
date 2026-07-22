# SETUP · Entorno de desarrollo local

Guía paso a paso para poner el proyecto a correr en tu Mac (o Linux). Estimado: **15 min** la primera vez.

## Prerequisitos

- Python 3.11+ (`python3 --version`)
- Git configurado con credenciales para el repo
- Editor de código (VS Code recomendado)

## 1. Clonar el repo

```bash
cd ~/Desktop  # o donde prefieras
git clone https://github.com/kevinromeroe/comapan-diagnostico-mes1.git
cd comapan-diagnostico-mes1
```

## 2. Crear virtualenv e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` incluye: `pyyaml`, `requests`, `python-dateutil`, `Pillow`, `apify-client`, `anthropic`, `google-analytics-data`, `pytest`, `pytest-cov`, `ruff`, `mypy`.

## 3. Configurar variables de entorno

Crear `.env` en la raíz del repo (**nunca commitearlo** — ya está en `.gitignore`):

```bash
# Credenciales — pedirle a Kevin Romero (owner) las claves
APIFY_TOKEN=apify_api_XXXXXXXXXXXXXXXX
SUPABASE_URL=https://pmeotakzlgkjdbwdttyf.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
GEMINI_API_KEY=AIzaSy...

# Opcional (para tests de LinkedIn):
# HARVESTAPI_TOKEN=...
```

Cargar el `.env` antes de correr scripts:

```bash
export $(cat .env | xargs)   # bash / zsh
# o instala 'dotenv' y agrega `from dotenv import load_dotenv; load_dotenv()` en scripts
```

## 4. Verificar setup con tests

```bash
pytest tests/ -v
```

Deben pasar todos los tests. Si alguno falla por credenciales, verifica el `.env`.

## 5. Correr ingesta local (opcional, cuidado con costos)

```bash
python scripts/ingest_monthly.py --client comapan --period 2026-07
```

**Costo:** ~$0.60 USD por corrida. **Solo hacerlo si es necesario debuggear.** El workflow de GH Actions ya cubre las ingestas mensuales.

## 6. Correr build local (gratis, no toca Apify)

```bash
python scripts/build_diagnostico_extendido_html.py --client comapan --period 2026-07
```

Esto lee de Supabase, corre Gemini (usa tu `GEMINI_API_KEY`) y sobreescribe `2026-07/index.html`. No hace commit ni push.

Para regenerar todos los períodos:

```bash
python scripts/build_diagnostico_extendido_html.py --client comapan --period all
```

## 7. Preview del HTML localmente

```bash
python3 -m http.server 8000
# Abrir http://localhost:8000/2026-07/ en el browser
```

## 8. Estructura de código

```
scripts/                                    # entry points ejecutables
├── ingest_monthly.py                       # ingesta desde Apify → Supabase
├── build_diagnostico_extendido_html.py     # build del reporte HTML
├── generate_narratives.py                  # narrativas LLM (obsoleto, revisar)
└── ingest_to_supabase.py                   # ingest antiguo (fallback histórico)

pipeline/                                   # librerías reutilizables
├── extract/                                # clientes Apify
├── transform/                              # normalizadores + agregadores
│   ├── normalize.py                        # raw → shape canónico
│   ├── aggregate.py                        # by_type, by_day, by_hour, etc.
│   ├── top_posts.py                        # ranking top5/atipicos/worst5
│   └── llm_providers/                      # Gemini + Anthropic
├── load/                                   # persistencia
│   ├── supabase_client.py                  # cliente REST liviano (urllib)
│   ├── thumbs.py                           # descarga+resize+persistencia
│   └── json_writer.py                      # dumps intermedios (gitignored)
├── render/                                 # template + build.py (auxiliar)
├── publish/                                # git commit + push
├── notify/                                 # email (opcional)
└── util/                                   # config, log

config/clients/                             # config por cliente
└── comapan.yaml                            # branding, plataformas, actores

tests/                                      # unit tests + fixtures
├── test_aggregate.py
├── test_render.py
├── test_notify.py
└── fixtures/                               # responses Apify de muestra
```

## 9. Convenciones de código

- **Zona horaria:** todo lo relacionado a fechas de posts se maneja en `America/Bogota` (UTC-5, sin DST). Ver `_to_bogota()` en el build script.
- **Filtro de posts al período:** siempre usar `VENTANA_DESDE`/`VENTANA_HASTA` (Bogotá). Nunca operar sobre `sb.select("posts", ...)` sin filtrar.
- **Miniaturas:** `posts.media_url_local` debe ser path absoluto (`/assets/thumbs/...`). Nunca relativo.
- **Configuración:** todo lo específico del cliente vive en `config/clients/<client>.yaml`. No hardcodear `comapan` en scripts.
- **Estilo:** `ruff` para lint, `mypy` para type check. Ambos configurados en `pyproject.toml` (si existe).

## 10. Debugging tips

- **Ver qué datos hay en Supabase:** abrir `https://supabase.com/dashboard/project/pmeotakzlgkjdbwdttyf/editor` y correr queries SQL directamente.
- **Ver logs de un workflow:** `github.com/kevinromeroe/comapan-diagnostico-mes1/actions/runs/<run_id>`.
- **Reproducir un bug del build:** ejecutar `build_diagnostico_extendido_html.py` con `--period <periodo-afectado>` y agregar `print()` estratégicos.
- **Reproducir un bug del ingest:** más caro (paga Apify). Considera primero descargar el dataset del run anterior desde Apify Console → JSON → analizar local.

## 11. Antes de pushear

```bash
# Correr tests
pytest

# (Opcional) lint
ruff check .

# (Opcional) type check
mypy scripts/ pipeline/

git status
git diff  # revisar cambios antes de commit
git add <files>
git commit -m "tipo(scope): descripción"
git push origin main
```

Los commits estilo Conventional Commits (`fix(tt):`, `docs:`, `feat:`, `chore:`) ayudan a leer el CHANGELOG.

## 12. Deploy

**No hay deploy manual.** GitHub Pages publica automáticamente todo lo que hay en `main`. Después de un `git push` exitoso, esperar 1-2 min y validar en `https://comapan.datalitica.com.co/`.

Si el sitio no actualiza:
1. Verificar `Actions → pages-build-deployment` en GitHub.
2. Verificar CNAME y DNS (nunca deberían cambiar, pero worth revisar).
3. Hard refresh en el browser (Cmd+Shift+R).
