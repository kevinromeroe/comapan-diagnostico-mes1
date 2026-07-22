# ONBOARDING · Agregar un nuevo cliente

Cómo agregar un cliente adicional al pipeline. La arquitectura es multi-tenant desde el schema (todas las tablas tienen `client_id`), así que agregar un cliente NO requiere duplicar el código — solo config + seeds.

Estimado: **60-90 min** primera vez, **30 min** después.

## Prerequisitos

- Cliente ha firmado contrato con Datalítica.
- Handles/URLs oficiales de sus redes sociales.
- Dominio destino (si es propio) o subdominio de `datalitica.com.co`.
- Branding: paleta de colores, logos, tipografía.

## Paso 1 · Crear registro en Supabase

Ejecutar en el SQL Editor:

```sql
-- 1a. Registrar el cliente
INSERT INTO clients (id, name, agency_name)
VALUES ('nombrecliente', 'Nombre Cliente', 'Agencia (si aplica)')
ON CONFLICT (id) DO NOTHING;

-- 1b. Crear el periodo "diagnostico" (baseline) — cambiar fechas si aplica
INSERT INTO periods (id, client_id, label, starts_on, ends_on, is_baseline)
VALUES (
  'diagnostico',
  'nombrecliente',
  'Diagnóstico (Ene-May 2026)',
  '2026-01-01',
  '2026-05-31',
  TRUE
)
ON CONFLICT (id) DO NOTHING;
```

**Nota:** el `id` de `periods` es único global (no compuesto). Si otro cliente ya tiene `'diagnostico'`, usar algo como `'nombrecliente-diagnostico'`.

Alternativa mejor: cambiar el schema para que `periods` tenga PK compuesta `(client_id, id)`. Pendiente de refactor.

## Paso 2 · Crear config del cliente

Copiar `config/clients/comapan.yaml` a `config/clients/nombrecliente.yaml` y editar:

```yaml
client:
  id: nombrecliente
  name: Nombre Cliente
  agency:
    name: "Agencia Ltd."
    nit: "..."
    contact_email: "..."
    contact_phone: "..."

  cycle: mensual
  cron_utc: "0 11 1 * *"    # dia 1 de cada mes, 06:00 Bogotá
  window_days: 30

  deploy:
    repo: <org>/<repo>            # puede ser mismo repo o uno nuevo
    branch: main
    domain: nombrecliente.datalitica.com.co
    output_path: index.html

branding:
  primary: "#..."
  # ... resto del branding

platforms:
  instagram:
    enabled: true
    handle: <username>
    url: https://www.instagram.com/<username>/
    apify:
      actor_id: shu8hvrXbJbY3Eb9W       # apify/instagram-scraper
      actor_name: apify/instagram-scraper
      input:
        directUrls: ["https://www.instagram.com/<username>/"]
        resultsLimit: 100

  facebook:
    enabled: true
    handle: <PageName>
    url: https://www.facebook.com/<PageName>
    apify:
      pages:
        actor_id: <id>
        actor_name: apify/facebook-pages-scraper
        input: {...}
      posts:
        actor_id: <id>
        actor_name: apify/facebook-posts-scraper
        input: {...}

  tiktok:
    enabled: true
    handle: <username>
    url: https://www.tiktok.com/@<username>
    apify:
      profile:
        actor_id: 0FXVyOXXEmdGcV88a     # clockworks/tiktok-profile-scraper
        actor_name: clockworks/tiktok-profile-scraper
        input:
          profiles: ["<username>"]
      # NOTA: no configurar bloque "posts" — el profile-scraper ya trae posts
      # (fix 2026-07-21).

  linkedin:
    enabled: true
    handle: <company-slug>
    url: https://www.linkedin.com/company/<company-slug>/
    apify:
      actor_id: <id>
      actor_name: harvestapi/linkedin-company-posts
      input: {...}
```

## Paso 3 · Actualizar `ingest_monthly.py` (si el pipeline lo requiere)

El pipeline actual está hardcoded a `CLIENT_ID = "comapan"` en varios lugares. Para multi-cliente hay que refactorizar:

1. Aceptar `--client` como arg (probablemente ya existe, verificar).
2. Reemplazar `CLIENT_ID = "comapan"` global por `args.client`.
3. Cargar el YAML del cliente correcto: `config/clients/{args.client}.yaml`.

Verificar en el código actual si ya está multi-tenant o necesita refactor.

## Paso 4 · Ejecutar diagnóstico inicial

Ingesta manual local (una vez):

```bash
python scripts/ingest_monthly.py --client nombrecliente --period diagnostico
python scripts/build_diagnostico_extendido_html.py --client nombrecliente --period diagnostico
```

Costo aprox: $2-3 USD por el diagnóstico (5 meses de scraping x 5 plataformas).

Validar en Supabase que se hayan insertado:
- Fila en `clients`
- Fila en `periods` para `diagnostico`
- Filas en `accounts` (una por plataforma)
- Filas en `posts` (~100-300 dependiendo actividad)
- Filas en `aggregates` (unas 10 por plataforma)

## Paso 5 · Configurar el deploy

### Opción A · Mismo repo (compartido)

Si vas a hostear varios clientes en `kevinromeroe/comapan-diagnostico-mes1`:

1. El HTML del cliente se genera en `/{client_id}/index.html`.
2. Configurar dominio adicional en `CNAME`? Complejo — GH Pages permite solo 1 CNAME por repo.
3. Alternativa: usar subrutas — `datalitica.com.co/nombrecliente/`. Requiere `CNAME` a `datalitica.com.co` en el repo.

### Opción B · Repo nuevo por cliente

Recomendado para clean separation:

1. Crear repo `nombrecliente-diagnostico` en GitHub.
2. Copiar la estructura del repo actual excluyendo `.git` y `data/`.
3. Actualizar `.github/workflows/*.yml` con los secrets del nuevo repo.
4. Configurar GitHub Pages: Settings → Pages → Source: main branch, root.
5. Configurar `CNAME` con el dominio del cliente.
6. Configurar DNS del cliente para apuntar a `<org>.github.io`.

## Paso 6 · Configurar secrets en el repo

En Settings → Secrets and variables → Actions:

- `APIFY_TOKEN` — mismo token de Datalítica
- `SUPABASE_URL` — mismo (mismo proyecto multi-tenant)
- `SUPABASE_SERVICE_KEY` — mismo
- `GEMINI_API_KEY` — mismo (nueva cuota si supera 250 RPD)

## Paso 7 · Configurar workflows

Copiar los 3 workflows (`ingest_monthly.yml`, `build_diagnostico_extendido.yml`, `keepalive_supabase.yml`) al repo nuevo o parametrizar el existente.

Si es workflow parametrizado:

```yaml
on:
  workflow_dispatch:
    inputs:
      client:
        description: 'Client ID (ej comapan)'
        required: true
        default: 'comapan'
```

Y en el step:

```yaml
run: python scripts/ingest_monthly.py --client ${{ github.event.inputs.client }}
```

## Paso 8 · Programar primer ciclo

Si el cliente contrató mensual:

- Editar `keepalive_supabase.yml` o crear cron scheduled workflow.
- Recordatorio manual mensual el día 1 para disparar Ingest → Build.
- Alternativa: convertir workflows a `schedule: cron` (con cuidado, revisar aprobación cliente antes).

## Paso 9 · Documentar el nuevo cliente

- Actualizar `README.md` con el cliente en la lista.
- Crear `docs/clients/nombrecliente.md` con sus handles, dominios, contacto.
- Actualizar `CHANGELOG.md` con la fecha de onboarding.

## Checklist final

- [ ] Registro en Supabase (`clients`, `periods`, seed diagnóstico)
- [ ] Config YAML creado y validado
- [ ] Ingesta diagnóstico ejecutada — datos en Supabase
- [ ] Build diagnóstico ejecutado — HTML generado
- [ ] Deploy configurado (repo + Pages + dominio)
- [ ] Secrets configurados en GH Actions
- [ ] Workflows probados manualmente
- [ ] Cron / recordatorio mensual programado
- [ ] Documentación actualizada
- [ ] Cliente notificado con URL del reporte

## Consideraciones legales / seguridad

- El cliente debe firmar el contrato de tratamiento de datos personales (Ley 1581 Colombia).
- Los datos scrapeados son **públicos** (perfiles públicos de redes sociales), pero el análisis y el reporte son confidenciales.
- El repo debe ser **privado** si el reporte incluye insights sensibles o si el cliente lo pide explícitamente.
- Nunca commitear credenciales, tokens, ni JSONs de data cruda.

## Preguntas frecuentes

**¿Se puede reusar el mismo proyecto Supabase para varios clientes?**
Sí — el schema es multi-tenant por diseño. Todas las tablas filtran por `client_id`.

**¿Se puede usar la misma cuenta Apify?**
Sí — todos los actores aceptan cualquier `profile` como input. La factura de Apify es unificada.

**¿Y Gemini?**
Sí, misma API key. Cuidado con el free tier de 250 RPD si tienes muchos clientes activos simultáneamente. Considera pagar tier si escalas.
