# RUNBOOK — Operación semanal Comapan

## Workflows disponibles (los únicos que hay)

Solo 3 workflows en el repo:

| Workflow | Cuándo | Costo | Trigger |
|---|---|---|---|
| `ingest_monthly.yml` | Refresh mensual o nuevo mes | ~$0.80 USD | Manual (workflow_dispatch) |
| `build_diagnostico_extendido.yml` | Después de cada ingest | $0 | Manual |
| `keepalive_supabase.yml` | Automático semanal | $0 | Cron (lunes 6 AM Bogotá) |

## Rutina semanal recomendada (cada lunes)

### 0. Pre-check (opcional, ~30 seg)

Abrir Supabase y correr:
```sql
SELECT NOW(), (SELECT COUNT(*) FROM posts WHERE client_id='comapan');
```

Si responde OK → seguí al paso 1. Si no responde, esperar 1 min (el keepalive
debería mantenerlo activo).

### 1. Ingest del mes en curso (~5-8 min, ~$0.80 USD)

**https://github.com/kevinromeroe/comapan-diagnostico-mes1/actions/workflows/ingest_monthly.yml**

- Run workflow ▼
- **period**: mes actual en formato `YYYY-MM` (ej `2026-07`)
- Run workflow

Esto trae posts nuevos + refresca engagement + descarga thumbnails al instante + los persiste automáticamente en el repo.

### 2. Build (~1 min, $0)

**https://github.com/kevinromeroe/comapan-diagnostico-mes1/actions/workflows/build_diagnostico_extendido.yml**

- Run workflow (dejá `period=all` por default)
- Run workflow

Regenera diagnóstico + todos los meses con la data actualizada.

### 3. Verificación (~30 seg)

Abrir en incógnito https://comapan.datalitica.com.co/ y validar que el dropdown
muestre el mes en curso.

## Procedimientos especiales

### Agregar un mes nuevo por primera vez

Antes del ingest del mes:
```sql
INSERT INTO periods (id, client_id, label, starts_on, ends_on, is_baseline)
VALUES ('YYYY-MM', 'comapan', 'Mes YYYY', 'YYYY-MM-01', 'YYYY-MM-31', false)
ON CONFLICT (id) DO NOTHING;
```

Después seguir la rutina normal.

### Corregir tags mal clasificados

Si el equipo detecta posts mal etiquetados:

```sql
UPDATE posts
SET tag_primary = NULL, tags = NULL, tagged_at = NULL
WHERE client_id = 'comapan'
  AND posted_at >= 'YYYY-MM-01' AND posted_at <= 'YYYY-MM-31 23:59:59';
```

Correr el build. Gemini re-clasifica solo los posts sin tag.

### Actor de una red social falla con HTTP 400

Si algún actor de Apify cambia su schema (ya nos pasó con TikTok en junio 2026):

1. Ir a la página del actor en Apify Store
2. Revisar el input schema actualizado
3. Editar `config/clients/comapan.yaml` en la sección correspondiente
4. Commit + push
5. Re-correr el ingest

## Configuración blindada (no requiere intervención)

### Supabase no-pause
Workflow `keepalive_supabase.yml` corre cada lunes 6 AM Bogotá. Hace un
`SELECT` trivial que resetea el timer de inactividad de 7 días.

### Thumbnails persistidos
El workflow `ingest_monthly.yml` descarga las imágenes durante el ingest
mientras las CDN URLs siguen frescas, y las commitea automáticamente al
repo. **No vuelve a pasar el bug de imágenes rotas.**

### Tags persistidos
Los tags de Gemini se guardan en `posts.tag_primary`. Cada build reusa lo
que ya está tageado, solo llama a Gemini para posts nuevos. **Costo de
tagging tras la primera vez: $0.**

## Secrets requeridos en GitHub

En Settings → Secrets → Actions:

| Secret | Valor / origen |
|---|---|
| `SUPABASE_URL` | `https://pmeotakzlgkjdbwdttyf.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Service role key (Supabase dashboard → Settings → API) |
| `APIFY_TOKEN` | Personal token en Apify Console → Settings → Integrations |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

## Costos operativos mensuales

| Concepto | Costo |
|---|---|
| GitHub Actions runners | $0 (public repo, unlimited) |
| GitHub Pages | $0 |
| Supabase free tier | $0 |
| Gemini 2.5 Flash free tier | $0 |
| Apify scraping mensual (1 ingest) | ~$0.80 USD |
| **Total por mes** | **~$0.80 USD** |

## Escalado a más clientes

Si Datalítica quiere replicar este setup para otro cliente:

1. Nuevo repo con la misma estructura
2. Nuevo proyecto Supabase (o reusar con `client_id` diferente)
3. Nuevo YAML de config en `config/clients/`
4. Los workflows funcionan igual — solo cambia el `CLIENT_ID`

Con la infraestructura actual, agregar un cliente cuesta ~$0.80 USD/mes adicional (solo Apify).

