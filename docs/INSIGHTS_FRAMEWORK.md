# Framework de Insights

Este documento define **cómo Datalítica genera hallazgos** a partir de los datos de redes sociales. Es el manual oficial del oficio analítico para este proyecto y para cualquier futuro cliente que use este pipeline. Si un hallazgo no cumple con este framework, no se incluye en el reporte.

---

## La regla del "¿y entonces qué?"

Antes de incluir cualquier métrica, gráfico o número en el reporte, hay que contestar: **"¿y entonces qué significa esto para el negocio?"**.

Si la respuesta es "no sé" o "se ve interesante", la métrica **no entra**. Reportes saturados de métricas sin interpretación son ruido caro.

---

## Jerarquía de análisis (4 capas)

Un reporte serio recorre las cuatro capas, no se queda en la primera:

| Capa | Pregunta | Ejemplo |
|---|---|---|
| **Descriptiva** | ¿Qué pasó? | "IG cerró el periodo con 13.422 seguidores" |
| **Diagnóstica** | ¿Por qué pasó? | "El crecimiento se concentró las dos semanas posteriores al post viral del 8-mar" |
| **Predictiva** | ¿Qué va a pasar? | "Al ritmo actual, IG superará 14k seguidores en septiembre" |
| **Prescriptiva** | ¿Qué hacer? | "Replicar el formato del post del 8-mar con frecuencia semanal" |

El 80% de los reportes que llegan al cliente se quedan en descriptiva. **El valor está en bajar las capas**.

---

## Marco de comparación obligatorio

Ningún número va solo. Cada métrica debe tener mínimo **una** de estas comparaciones, idealmente dos:

- vs **período anterior** (mes vs mes, quincena vs quincena, año vs año)
- vs **media histórica** propia (¿es atípico o normal para esta cuenta?)
- vs **benchmark de sector** (panaderías o FMCG en LATAM)
- vs **meta interna** (si Catorce Días o el cliente definió un target)

> Ejemplo malo: "Engagement promedio: 116 likes por post"
> Ejemplo bueno: "Engagement promedio: 116 likes/post, +24% vs quincena anterior y 3.7× el de Facebook"

---

## Categorías de hallazgo

Solo cuenta como "hallazgo" lo que entra en una de estas seis categorías. Todo lo demás es decoración descriptiva:

### 1. Patrón
Comportamiento recurrente en los datos.
> *"Los videos publicados los sábados tienen 2.5× más engagement promedio que el resto de la semana, sostenido los últimos 3 meses."*

### 2. Anomalía
Outlier que requiere explicación.
> *"El post del 8-mar superó por 4 desviaciones estándar la media de engagement de IG; analizar qué hizo único a ese contenido."*

### 3. Tendencia
Dirección sostenida durante ≥3 periodos.
> *"El engagement de TikTok crece 41% trimestre tras trimestre desde Q4-2025."*

### 4. Brecha
Gap entre realidad y potencial.
> *"LinkedIn publica 3× menos que las otras plataformas y rinde 80% menos por post; representa una oportunidad cuantificable."*

### 5. Correlación
Relación entre dos variables (cuidando no confundir con causalidad).
> *"Los Reels duran 22% más en feed que los Image posts; coincide con un mayor engagement, aunque no podemos afirmar causalidad."*

### 6. Punto ciego
Métrica relevante que no se está midiendo y debería medirse.
> *"No tenemos data de saves en IG; ese es un proxy más fuerte de intent que likes y deberíamos solicitarlo."*

---

## Estructura fija de cada hallazgo

Cada hallazgo debe contener los 5 elementos. Si falta uno, no es un hallazgo: es un dato suelto.

```
1. DATO            Número específico con unidad y contexto temporal.
2. COMPARATIVO     Contra qué se mide (anterior, benchmark, meta).
3. INTERPRETACIÓN  Qué significa en términos de negocio. Máx 30 palabras.
4. IMPLICACIÓN     Qué consecuencia tiene si no se atiende. Máx 30 palabras.
5. RECOMENDACIÓN   Acción priorizada. Máx 25 palabras + prioridad + esfuerzo.
```

### Ejemplo aplicado completo

> **Dato**: Los carruseles de Instagram generan 36 likes promedio en el periodo (n=14 publicaciones).
>
> **Comparativo**: 3.7× menos engagement por publicación que los videos del mismo periodo (132 likes promedio, n=51).
>
> **Interpretación**: El formato carrusel está subperformando para esta cuenta, pese a representar el 18% del calendario editorial.
>
> **Implicación**: Se está invirtiendo tiempo de producción gráfica en un formato con retorno bajo, restando capacidad para producir más video.
>
> **Recomendación (Prioridad ALTA, Esfuerzo BAJO)**: Reducir carruseles a 1 por semana y reorientar 4 horas/semana de diseño hacia producción de video corto.

---

## Reglas del oficio (innegociables)

1. **Ningún hallazgo sin número** que lo sustente.
2. **Ningún número sin contra-qué** que le dé contexto.
3. **Ninguna recomendación sin priorización** (Alta/Media/Baja por impacto × esfuerzo).
4. **Cambios <5% no son hallazgo**: son ruido estadístico.
5. **Cambios >15% siempre son hallazgo**: hay que explicarlos.
6. **Distinguir correlación de causalidad** explícitamente. "Coincide con", "se observa junto a" en lugar de "es causado por".
7. **Si hay >20 hallazgos**, los top 5 al inicio del reporte; el resto en anexos.
8. **Cero adjetivos vacíos**: prohibido "genial", "increíble", "destacado", "importante" sin un número que lo justifique.
9. **Cero jerga vacía**: prohibido "engagement de calidad", "alcance significativo", "interacciones relevantes" sin definición numérica.
10. **N mínimo para significancia**: muestras de <5 publicaciones no permiten hablar de patrón. Decir "muestra pequeña".

---

## Estructura del reporte (Pyramid Principle)

Top-down: conclusión arriba, soporte abajo. El ejecutivo lee solo el primer nivel y obtiene 80% del valor.

```
1. Resumen ejecutivo         ← 5 hallazgos top + 3 recomendaciones prioritarias
                               (el cliente ocupado solo lee esto)
2. Snapshot del periodo      ← KPIs por plataforma + deltas vs anterior
3. Estado por plataforma     ← IG, FB, TT, LI (mismo orden mental)
4. Hallazgos cruzados        ← patrones entre plataformas
5. Recomendaciones completas ← lista priorizada Alta/Media/Baja
6. Anexos                    ← top posts, tablas crudas, gráficos secundarios
```

---

## KPIs ordenados por bucket (mismo árbol en todas las plataformas)

Para que el cerebro del lector pueda comparar apples-to-apples sin esfuerzo:

| Bucket | Pregunta de negocio | Métricas |
|---|---|---|
| **TAMAÑO** (size) | ¿Cuánta audiencia tenemos? | seguidores, alcance, audiencia activa |
| **ACTIVIDAD** (volume) | ¿Cuánto publicamos? | publicaciones, ritmo (posts/semana), distribución por formato |
| **DESEMPEÑO** (performance) | ¿Cuánto rinde lo que publicamos? | engagement rate, top posts, mejor día, mejor hora |

**Tres buckets, idénticos en IG, FB, TT, LI**. Cuando el lector pasa de una sección a otra ya sabe qué esperar.

---

## Generación automática con LLM

El pipeline, en cada corrida, llama a la API de Claude con el JSON `DATA` y un prompt estricto que retorna hallazgos en JSON schema validado. Esto garantiza calidad consistente quincena tras quincena.

### Schema obligatorio del output

```json
{
  "hallazgos_top": [
    {
      "categoria": "patron | anomalia | tendencia | brecha | correlacion | punto_ciego",
      "plataforma": "instagram | facebook | tiktok | linkedin | cross",
      "dato": "string con número + unidad + contexto",
      "comparativo": "string con contra qué",
      "interpretacion": "string ≤ 30 palabras",
      "implicacion": "string ≤ 30 palabras",
      "recomendacion": {
        "accion": "string ≤ 25 palabras",
        "prioridad": "alta | media | baja",
        "esfuerzo": "alto | medio | bajo"
      }
    }
  ],
  "resumen_ejecutivo": "string ≤ 200 palabras, top-down"
}
```

### Reglas del prompt a Claude

El prompt debe explícitamente:

1. **Prohibir adjetivos vacíos**: "Si usas la palabra 'genial', 'importante', 'destacado', 'significativo' sin un número que lo justifique, el output será rechazado."
2. **Forzar contraste**: "Toda métrica mencionada debe venir con su comparativo. Sin contraste no se aprueba."
3. **Limitar a top 5 hallazgos**: si el modelo intenta dar 10, se rechaza.
4. **Validar schema** antes de inyectar al HTML. Si falla schema, reintento con prompt más estricto. Si falla 3 veces, se notifica y se publica sin sección de hallazgos automáticos (humano revisa).
5. **Reproducibilidad**: temperatura 0 y seed fijo para que el mismo DATA produzca los mismos hallazgos.

### Por qué LLM y no reglas hardcoded

Las reglas pueden detectar el dato (engagement cayó 23%) pero no la interpretación de negocio en lenguaje natural. El LLM, con framework + datos estructurados, produce el lenguaje. **El framework es el guardrail; el modelo solo escribe**.

---

## Cómo el reporte demuestra rigor metodológico

Para que Catorce Días y eventualmente Comapan confíen en lo que lee, el reporte debe ser transparente sobre cómo se calculó cada cosa:

- **Footer con `generated_at`**: fecha y hora exactas de generación.
- **Ventana analizada visible**: "Datos del 1 al 15 de junio de 2026" en el header.
- **Definiciones de métricas con tooltips** (ya implementado en el sitio Mes 1 con el ícono "i").
- **N visible** en cada gráfico: "n=79 publicaciones".
- **Caveats explícitos** cuando aplica: "TikTok Analytics solo retiene 60 días vía API; datos pre-marzo extraídos con muestreo".
- **Versión del pipeline** en footer (commit SHA del repo).

---

## Anti-patrones que NO usamos

| Anti-patrón | Por qué lo evitamos |
|---|---|
| "El engagement creció" sin número | Vacío |
| "Cantidad significativa de seguidores" | Sin definición numérica |
| Comparar entre plataformas sin normalizar | IG y LinkedIn tienen escalas distintas |
| Promediar sin reportar mediana | Outliers distorsionan promedios |
| Top posts sin engagement rate | El top absoluto en una cuenta grande puede tener peor ratio que un post pequeño |
| Mostrar engagement total sin alcance | 1000 likes sobre 10k impresiones es muy distinto a 1000 sobre 1M |
| Recomendar sin justificar con data | Es opinión, no analítica |

---

## Mantenimiento de este framework

Este documento es vivo. Cuando aparezca un nuevo tipo de hallazgo útil, una nueva regla de calidad, o una corrección importante, se actualiza acá. Cada modificación debe quedar versionada en git (no edición silenciosa).

El framework lo aprueba el director de datos de Datalítica antes de pasar a producción.
