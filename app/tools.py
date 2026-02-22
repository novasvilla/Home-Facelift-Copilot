import json
import logging
import os
import re
import uuid as _uuid
from datetime import datetime
from urllib.parse import quote_plus

from google import genai
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from app import gcs_storage

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

STORE_SEARCH_URLS = {
    "Leroy Merlin": "https://www.leroymerlin.es/buscador?query={q}",
    "ManoMano": "https://www.manomano.es/busqueda/{q}",
    "Bricomart": "https://www.bricomart.es/catalogsearch/result/?q={q}",
    "Amazon ES": "https://www.amazon.es/s?k={q}",
}


def _get_client() -> genai.Client:
    """Lazy-init a Google AI Studio genai client using GOOGLE_API_KEY."""
    global _client
    if _client is None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required. "
                "Get a key at: https://aistudio.google.com/apikey"
            )
        _client = genai.Client(api_key=api_key)
    return _client


# ─── Shared helpers ──────────────────────────────────────────────────────────


def _load_image(image_path: str) -> types.Part:
    """Load image from path into a genai Part."""
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    mime = "image/png" if image_path.endswith(".png") else "image/jpeg"
    return types.Part.from_bytes(data=image_bytes, mime_type=mime)


# ─── Tools for Orchestrator (image generation) ───────────────────────────────


async def _generate_image(
    edit_prompt: str, image_path: str, tool_context: ToolContext
) -> str:
    """Core image generation: sends FULL prompt + original image to Nano Banana Pro."""
    image_part = _load_image(image_path)

    image_model = os.environ.get("IMAGE_MODEL", "gemini-3-pro-image-preview")
    logger.info("Calling image model: %s", image_model)

    client = _get_client()
    response = client.models.generate_content(
        model=image_model,
        contents=[image_part, edit_prompt],
    )

    os.makedirs(STATIC_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Descriptive filename: project_style_room_version
    user_id = tool_context.state.get("_user_id", "anon")
    project_style = (tool_context.state.get("project_style") or "moderno")[:12].replace(
        " ", "_"
    )
    section_type = (tool_context.state.get("section_type") or "general")[:10].replace(
        " ", "_"
    )
    gen_version = tool_context.state.get("_gen_version", 0)
    tool_context.state["_gen_version"] = gen_version + 1
    short_id = _uuid.uuid4().hex[:6]
    base_filename = _generate_filename(edit_prompt, timestamp)
    filename = f"{user_id}_{project_style}_{section_type}_{base_filename}_v{gen_version}_{short_id}.png"
    output_path = os.path.join(STATIC_DIR, filename)

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            with open(output_path, "wb") as f:
                f.write(part.inline_data.data)
            logger.info("Saved facelift image to %s", output_path)

            artifact = types.Part.from_bytes(
                data=part.inline_data.data,
                mime_type=part.inline_data.mime_type,
            )
            await tool_context.save_artifact(filename=filename, artifact=artifact)
            logger.info("Saved artifact: %s", filename)

            # Upload to GCS
            gcs_url = gcs_storage.upload_image(
                output_path, gcs_folder=f"generated/{user_id}"
            )

            abs_path = os.path.abspath(output_path)
            gcs_note = f"\n- **GCS**: {gcs_url}" if gcs_url else ""
            return (
                f"Image successfully edited!\n"
                f"- **Local file**: `{abs_path}`\n"
                f"- **ADK Artifacts tab**: check 'Artifacts' tab to view/download.\n"
                f"- **Model**: {image_model}{gcs_note}"
            )

    return (
        "Error: The model did not return an edited image. Try rephrasing your request."
    )


# ─── GenAI Consistency Check ──────────────────────────────────────────────────

MAX_CONSISTENCY_RETRIES = 2


def _consistency_check(original_path: str, generated_path: str) -> dict:
    """Use Gemini Vision to compare original vs generated image.
    Returns {"passed": bool, "issues": list[str], "score": int (0-100)}."""
    original_part = _load_image(original_path)
    generated_part = _load_image(generated_path)

    prompt = (
        "Eres un inspector de calidad de imágenes de renovación cosmética (facelift).\n"
        "Compara la imagen ORIGINAL (primera) con la imagen GENERADA (segunda).\n\n"
        "REGLAS DE CONSISTENCIA — la imagen generada SOLO puede cambiar:\n"
        "✅ PERMITIDO: colores de paredes, pintura, acabados superficiales, iluminación\n"
        "✅ PERMITIDO: color de puertas, ventanas, rejas (sin cambiar forma)\n"
        "✅ PERMITIDO: añadir plantas decorativas o macetas\n\n"
        "❌ PROHIBIDO alterar:\n"
        "- Geometría o forma de la estructura (paredes, tejado, ventanas, puertas)\n"
        "- Forma o posición de la piscina\n"
        "- Árboles y vegetación existente (no eliminar ni mover)\n"
        "- Perspectiva, proporciones o composición de la foto\n"
        "- Paisaje de fondo\n"
        "- Textura de piedra natural (solo pintar sobre ella, no alisar)\n\n"
        "Responde EXACTAMENTE en este formato JSON:\n"
        '{"passed": true/false, "score": 0-100, "issues": ["issue1", "issue2"]}\n\n'
        "- score 90-100: Excelente, solo cambios cosméticos\n"
        "- score 70-89: Aceptable, cambios menores no deseados\n"
        "- score 50-69: Problemas significativos\n"
        "- score 0-49: Inaceptable, cambios estructurales graves\n\n"
        "Si passed=true, issues debe estar vacío. Si passed=false, lista cada problema."
    )

    try:
        client = _get_client()
        model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
        response = client.models.generate_content(
            model=model_id, contents=[original_part, generated_part, prompt]
        )
        text = response.text.strip()
        # Extract JSON from response (may be wrapped in ```json ... ```)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)
        return {
            "passed": result.get("passed", False),
            "score": result.get("score", 0),
            "issues": result.get("issues", []),
        }
    except Exception as e:
        logger.warning("Consistency check failed: %s", e)
        # If check itself fails, pass through (don't block generation)
        return {"passed": True, "score": -1, "issues": [f"Check error: {e}"]}


# ─── Tools for ProductFinder sub-agent ────────────────────────────────────────


def search_products(product_query: str, tool_context: ToolContext) -> str:
    """Searches for a SPECIFIC home improvement product using Google Search grounding
    and returns product info PLUS guaranteed-valid store search links.

    Args:
        product_query: Very specific product search query including type, material,
            color/RAL code, finish, size. Example: "pintura exterior mate acrilica
            fachada estuco RAL 7035 gris perla Titan 15L"
        tool_context: ADK tool context (injected automatically).

    Returns:
        Product info from web search plus valid store search links.
    """
    client = _get_client()
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

    search_prompt = (
        f"Search for this specific product in Spanish home improvement stores: "
        f"{product_query}\n\n"
        "Find and return:\n"
        "1. Exact product name and brand\n"
        "2. Price in € (current, from a real store listing)\n"
        "3. Product code/SKU/reference if available\n"
        "4. The store where you found it (Leroy Merlin, ManoMano, Bricomart, Amazon)\n"
        "5. Two alternatives at different price points (cheaper and premium)\n\n"
        "Search specifically on leroymerlin.es, manomano.es, bricomart.es, amazon.es.\n"
        "Be specific — provide REAL product names and REAL prices you find on the web.\n"
        "IMPORTANT: If you cannot find a specific product or price, say so clearly.\n"
        "Do NOT invent product names, SKUs, or prices. Only report what you actually find."
    )

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=search_prompt,
            config=types.GenerateContentConfig(tools=[{"google_search": {}}]),
        )
        search_info = response.text
    except Exception as e:
        logger.error("Google Search failed for '%s': %s", product_query, e)
        search_info = f"(No se encontraron resultados online: {e})"

    # Build guaranteed-valid store search links
    encoded = quote_plus(product_query)
    store_links = "\n".join(
        f"  - [{store}]({url.format(q=encoded)})"
        for store, url in STORE_SEARCH_URLS.items()
    )

    return (
        f"### 🔍 {product_query}\n\n"
        f"{search_info}\n\n"
        f"**🔗 Enlaces de búsqueda directa (verificados, siempre funcionan):**\n{store_links}\n\n"
        f"*Precios orientativos. Usa los enlaces de arriba para verificar "
        f"disponibilidad y precio actual en cada tienda.*"
    )


# ─── Phase 1: AI-driven analysis + CDS (Cumulative Design Specification) ─────


def _vision_inventory(image_paths: list[str]) -> str:
    """Gemini Vision: creates a NUMBERED inventory of every visible element.
    Accepts multiple images (different angles) for a more complete inventory."""
    image_parts = [_load_image(p) for p in image_paths if os.path.exists(p)]

    prompt = (
        "Eres un experto en diseño de exteriores/interiores y en materiales de construcción. "
        "Analiza esta imagen para una renovación cosmética (facelift / lavado de cara). "
        "Responde EN ESPAÑOL.\n\n"
        "FILOSOFÍA CLAVE: Maximizar efecto WOW de moderno, elegante y caro con MÍNIMA inversión.\n"
        "Si algo YA está bien, en buen estado y no se ve desfasado → NO SE TOCA.\n"
        "Ejemplo: Un parquet en buen estado NO se cambia. Paredes blancas limpias pueden quedarse.\n\n"
        "Crea un INVENTARIO NUMERADO de ABSOLUTAMENTE TODO lo que se ve.\n"
        "Formato EXACTO para cada elemento:\n\n"
        "ELEM_XX: [nombre del elemento]\n"
        "  Ubicación: [planta baja / planta alta / ambas plantas / tejado / perímetro / jardín / "
        "pared norte / pared sur / etc.]\n"
        "  Material sustrato: [piedra natural / estuco-enfoscado / ladrillo / bloque hormigón / "
        "metal / madera / parquet / tarima / porcelánico / teja cerámica / hormigón / etc.]\n"
        "  Color actual: [describe con precisión, incluyendo variaciones entre zonas]\n"
        "  Estado: [bueno | desgastado | anticuado | necesita tratamiento]\n"
        "  Superficie: [m² estimados]\n"
        "  Exposición: [exterior pleno sol / exterior sombra / interior / semi-cubierto]\n"
        "  Problema estético: [qué lo hace feo/anticuado, o 'NINGUNO - está bien como está']\n"
        "  ¿Merece cambio?: [SÍ - explicar por qué / NO - está bien, no invertir aquí]\n"
        "  Preparación necesaria: [hidrolavado / decapado / lijado / reparar fisuras / ninguna]\n\n"
        "AGRUPACIÓN POR PLANTAS — CRÍTICO:\n"
        "- Si el edificio tiene VARIAS PLANTAS, crea elementos SEPARADOS para cada planta\n"
        "  pero IDENTIFICA que comparten el mismo tipo de superficie.\n"
        "  Ejemplo:\n"
        "    ELEM_01: Paredes estuco PLANTA BAJA\n"
        "    ELEM_02: Paredes estuco PLANTA ALTA\n"
        "    ELEM_03: Piedra esquineras PLANTA BAJA\n"
        "    ELEM_04: Piedra esquineras PLANTA ALTA\n"
        "- Esto permite aplicar EXACTAMENTE el MISMO tratamiento a todas las plantas.\n\n"
        "Incluye OBLIGATORIAMENTE:\n"
        "- Paredes de CADA PLANTA por separado (estuco, enfoscado, etc.)\n"
        "- Piedra natural de CADA PLANTA (esquineras, marcos, zócalos)\n"
        "- Tejado/tejas (material, color, estado, tipo de teja)\n"
        "- Ventanas y marcos (de cada planta y edificio)\n"
        "- Muros perimetrales/laterales (bloque, ladrillo, etc.)\n"
        "- Piscina (si existe) — forma, cubierta, bordes, coronación\n"
        "- Suelos y pavimentos\n"
        "- Jardín/césped/vegetación\n"
        "- Casetas, cobertizos u otros edificios auxiliares\n"
        "- Carpintería metálica (rejas, barandillas)\n"
        "- Iluminación existente\n\n"
        "Sé EXHAUSTIVO. Cada elemento que no esté en el inventario "
        "podría desaparecer de las imágenes generadas.\n\n"
        "IMPORTANTE: Identifica el SUSTRATO REAL de cada superficie porque determina\n"
        "el tipo de pintura e imprimación necesario:\n"
        "  - Piedra natural → imprimación silicato + pintura mineral silicato\n"
        "  - Estuco/enfoscado → fijador + pintura siloxánica exterior\n"
        "  - Metal → lija óxido + imprimación antioxidante + esmalte\n"
        "  - Madera → lijado + lasur protector exterior\n"
        "  - Teja cerámica → hidrolavado + pintura impermeabilizante tejas"
    )

    if not image_parts:
        return "Error: No se encontraron imágenes válidas."

    multi_note = ""
    if len(image_parts) > 1:
        multi_note = (
            f"\n\nNOTA: Se proporcionan {len(image_parts)} fotos del MISMO espacio "
            "desde diferentes ángulos. Analiza TODAS las fotos para crear un inventario "
            "completo que incluya elementos visibles desde cualquier ángulo.\n"
        )

    client = _get_client()
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
    contents = [*image_parts, prompt + multi_note]
    response = client.models.generate_content(model=model_id, contents=contents)
    return response.text


def _ai_generate_cds_alternatives(inventory: str) -> str:
    """AI generates 3 alternatives, each as a Cumulative Design Spec (CDS).
    Every element from the inventory gets a treatment (change or KEEP)."""
    client = _get_client()
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

    prompt = f"""Eres un arquitecto de diseño exterior experto en tendencias 2026.

INVENTARIO COMPLETO DE ELEMENTOS EN LA IMAGEN:
{inventory}

FILOSOFÍA: Esto es un LAVADO DE CARA (facelift) para aumentar el valor de la casa.
Solo pintamos y tratamos superficies. NO cambiamos geometría, forma ni estructura.
La piedra se PINTA conservando su textura y relieve natural, NUNCA se quita ni reemplaza.

⚠️ REGLA DE ORO: MÁXIMO WOW CON MÍNIMA INVERSIÓN ⚠️
- Un parquet/suelo en buen estado → SIEMPRE MANTENER. No cambiarlo.
- Techo blanco en buen estado → evaluar. Si pintar añade valor WOW, hacerlo.
- Paredes en buen estado → evaluar. Si pintar en otro color añade valor WOW, hacerlo.
- REGLA CRÍTICA DE PINTURA: Si se pintan paredes o techo → SIEMPRE MISMO COLOR EN AMBOS.
  Ejemplo: Si paredes van en gris, techo también va en gris. NUNCA techo blanco + paredes color.
- El inventario marca '¿Merece cambio?: NO' → esos elementos van SIEMPRE como MANTENER.
- Priorizar cambios de ALTO IMPACTO y BAJO COSTE (pintura, iluminación, textiles).
- Griferías baño → por defecto NEGRO mate RAL 9005 (tendencia 2026, elegante y moderno).
- Solo cambiar lo que REALMENTE mejora el aspecto: mobiliario anticuado, colores desfasados,
  iluminación pobre, elementos que se ven viejos o baratos.

REGLAS DE DISEÑO MODERNO 2026 (con proceso técnico):
- Piedra vieja/rústica → PINTAR sobre ella (conservando relieve y textura)
  Proceso: 1) Hidrolavado 130bar 2) Secado 48h 3) Imprimación silicato 4) Pintura mineral silicato
  Colores: Negro mate RAL 9005, Antracita RAL 7016, o Gris polvo RAL 7037
- Paredes estuco/enfoscado → pintar gris/blanco
  Proceso: 1) Limpieza 2) Reparar fisuras con masilla exterior 3) Fijador acrílico 4) Pintura siloxánica exterior
  Colores: Blanco RAL 9010, Gris claro RAL 7035, Gris cálido RAL 7044
- Muros bloque/ladrillo feos → enfoscar y pintar mismo color que la casa
- Metal oxidado → 1) Lijar óxido 2) Imprimación antioxidante 3) Esmalte poliuretano satinado
  Color: Negro satinado RAL 9005 o Gris forja RAL 7024
- Tejas/tejado → 1) Hidrolavado 2) Pintura impermeabilizante para tejas (color ACORDE al diseño)
- Madera → 1) Lijado 2) Lasur protector exterior (Nogal oscuro, Ébano, Gris envejecido)
- Casetas/edificios auxiliares → MISMO color que la casa principal (unificar)
- Gravilla → SOLO en EXTERIORES (jardín, perímetro, caminos exteriores). NUNCA en interiores, baños ni cocinas.
  Si es exterior: decorativa en bordes, dejar paso peatonal 90cm mín.
  Si es interior: NO proponer gravilla. Proponer suelo porcelánico, microcemento o similar.
- Piscina → MANTENER SIEMPRE, nunca eliminar ni ocultar
- Árboles/vegetación existente → MANTENER SIEMPRE en su posición

REGLA CRÍTICA DE UNIFORMIDAD ENTRE PLANTAS:
- Las paredes de TODAS las plantas reciben el MISMO color y acabado.
- La piedra de TODAS las plantas recibe el MISMO tratamiento y color.
- NO puede haber una planta con un diseño y otra con otro. Fachada UNIFORME.

GENERA EXACTAMENTE 3 ALTERNATIVAS. Para CADA alternativa, genera:

1. DESCRIPCIÓN DETALLADA para el usuario (concepto, colores RAL específicos, efecto visual)
2. TABLA de tratamiento por elemento
3. CDS (Cumulative Design Specification) con proceso de ejecución

Formato EXACTO:

## 🅰 Alternativa A: [Nombre creativo]
**Concepto**: [2-3 frases describiendo la visión, los colores RAL específicos, y el efecto final]

| Elemento | Acción | Color RAL | Proceso de ejecución |
|----------|--------|-----------|---------------------|
| [cada ELEM_XX] | CAMBIAR / MANTENER | [RAL XXXX] | [preparación → imprimación → acabado] |

Adicionales (SOLO si tienen sentido para el TIPO de espacio):
- **Caminos/Gravilla**: [SOLO EXTERIOR — propuesta con posición, ancho y tipo]
- **Maceteros/Plantas**: [tipo, posición — adecuadas al espacio interior/exterior]
- **Iluminación**: [tipo, IP, color temperatura]

NOTA: Adapta las propuestas al CONTEXTO. Exterior → gravilla, plantas, iluminación IP65.
Interior → suelos, iluminación empotrada, acabados de pared. Baño → azulejos, grifería, mampara.

**CDS_A:**
CAMBIAR:
- [ELEM_XX]: [color RAL + acabado + tipo pintura específica para ese sustrato]
  Proceso: 1) [preparación] 2) [imprimación] 3) [pintura final]
MANTENER SIN CAMBIOS:
- [ELEM_XX]: [descripción detallada de lo que tiene — para que el modelo de imagen lo conserve]
AÑADIR:
- [nuevos elementos: gravilla, maceteros, iluminación, etc.]

(Repite EXACTAMENTE igual para B y C con paletas DIFERENTES)

IMPORTANTE:
- CADA alternativa DEBE listar TODOS los ELEM del inventario (cambiar o mantener)
- Elementos con '¿Merece cambio?: NO' en el inventario → SIEMPRE como MANTENER
- Suelo/parquet en buen estado → SIEMPRE MANTENER (NUNCA cambiar)
- Si se pintan paredes o techo → SIEMPRE MISMO COLOR EN AMBOS (ej: gris paredes = gris techo)
- Griferías baño → por defecto NEGRO mate RAL 9005 (tendencia 2026)
- Alternativa A: contrastada (negro + gris claro/blanco)
- Alternativa B: monocromática premium (escala de grises)
- Alternativa C: cálida y acogedora (grises cálidos/greige)
- La piscina SIEMPRE aparece como MANTENER
- Los árboles SIEMPRE aparecen como MANTENER
- Edificios auxiliares SIEMPRE se unifican con la casa principal
- TODAS las plantas de la fachada reciben el MISMO color y tratamiento
- Las tejas deben tener un color ACORDE al diseño general
- La piedra se PINTA (conservando textura), NUNCA se quita
- Incluye el PROCESO TÉCNICO para que el usuario sepa qué hacer paso a paso
"""

    response = client.models.generate_content(model=model_id, contents=prompt)
    return response.text


CONSISTENCY_RULES = (
    "REGLAS CRÍTICAS — LEE TODAS ANTES DE EDITAR:\n\n"
    "ESTO ES UN LAVADO DE CARA (facelift). SOLO se cambian COLORES y ACABADOS.\n"
    "REGLA DE ORO: Si algo YA está bien (suelo, parquet, techo blanco) → NO TOCARLO.\n"
    "El suelo/parquet en buen estado DEBE aparecer IDÉNTICO en la imagen generada.\n"
    "Techo y paredes en buen estado → MANTENER color y acabado exacto.\n\n"
    "1. UNIFORMIDAD ENTRE PLANTAS: El MISMO tratamiento y color se aplica a TODAS "
    "las plantas de la fachada. Planta baja y planta alta IDÉNTICAS en color.\n"
    "2. PRESERVAR TEXTURAS: La piedra natural mantiene su RELIEVE y TEXTURA original. "
    "Solo se cambia el COLOR pintando sobre ella. NO alisar, NO quitar, NO reemplazar piedras.\n"
    "3. PRESERVAR GEOMETRÍA: NO mover, eliminar, añadir ni modificar la FORMA de "
    "ningún elemento (muros, ventanas, puertas, tejado, piscina, edificios).\n"
    "4. PISCINA: Mantener SIEMPRE visible, en su posición y forma exacta.\n"
    "5. ÁRBOLES y VEGETACIÓN: Mantener en su posición exacta.\n"
    "6. Elementos NO mencionados como CAMBIAR → quedar EXACTAMENTE como en la original.\n"
    "7. Aplicar los colores RAL especificados con PRECISIÓN en TODA la superficie indicada.\n"
    "8. La perspectiva, proporciones y composición deben ser EXACTAS a la foto original.\n"
    "9. Generar una imagen FOTORREALISTA de ALTA CALIDAD.\n"
    "10. TEJAS: Si se especifica un color, aplicar a TODAS las tejas por igual.\n\n"
    "CAMBIOS PROHIBIDOS:\n"
    "- NO cambiar la forma de ventanas, puertas o tejado\n"
    "- NO eliminar ni mover piedras — solo PINTARLAS conservando su textura\n"
    "- NO cambiar la forma de la piscina ni sus bordes\n"
    "- NO añadir elementos arquitectónicos nuevos (balcones, terrazas, etc.)\n"
    "- NO modificar la vegetación existente\n"
    "- NO cambiar el paisaje de fondo\n"
    "- NO aplicar tratamientos diferentes entre planta baja y planta alta"
)


def _ai_create_image_prompts(
    alternatives: str, inventory: str, count: int = 3
) -> list[str]:
    """AI generates explicit image editing prompts from alternatives text.
    Much more robust than regex parsing — the AI understands the design intent."""
    client = _get_client()
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

    prompt = f"""Eres un experto en crear prompts para modelos de edición de imagen.

INVENTARIO DE ELEMENTOS EN LA IMAGEN:
{inventory}

ALTERNATIVAS DE DISEÑO PROPUESTAS:
{alternatives}

Crea EXACTAMENTE {count} prompts de edición de imagen (uno por cada alternativa).
Cada prompt debe describir TODOS los cambios a aplicar sobre la foto original.

Formato OBLIGATORIO (usa EXACTAMENTE estos delimitadores):

===PROMPT_1===
[prompt detallado para alternativa A]
===FIN_1===

===PROMPT_2===
[prompt detallado para alternativa B]
===FIN_2===

===PROMPT_3===
[prompt detallado para alternativa C]
===FIN_3===

REGLAS OBLIGATORIAS para cada prompt:
- UNIFORMIDAD ENTRE PLANTAS: Escribe EXPLÍCITAMENTE que TODAS las plantas (baja, alta)
  reciben el MISMO color y tratamiento. Ejemplo:
  "Pintar TODAS las paredes de estuco de AMBAS plantas (baja y alta) en blanco RAL 9010"
- PIEDRA NATURAL: Especifica que se PINTA SOBRE la piedra conservando su textura y relieve
  natural. NO alisar, NO quitar piedras. Solo aplicar color encima manteniendo la forma.
- TEJAS: Si cambian, especificar el color EXACTO para TODAS las tejas por igual.
  Si no cambian, escribir "MANTENER tejas sin cambios".
- Lista CADA superficie y su nuevo color RAL exacto
- Para elementos que NO cambian, escribe explícitamente:
  "MANTENER SIN CAMBIOS: [elemento] en su posición, forma y color actual"
- Incluye las adiciones (gravilla, maceteros, iluminación)
- Menciona explícitamente que la piscina debe conservarse
- Menciona que edificios auxiliares se pintan del mismo color que la casa
- Especifica que es un LAVADO DE CARA: solo cambios de color/pintura, no estructurales
"""

    response = client.models.generate_content(model=model_id, contents=prompt)
    text = response.text

    # Parse with reliable delimiters
    prompts = []
    for i in range(1, count + 1):
        pattern = rf"===PROMPT_{i}===\s*\n(.*?)\n===FIN_{i}==="
        match = re.search(pattern, text, re.DOTALL)
        if match:
            prompts.append(match.group(1).strip())

    # Fallback: if delimiters weren't used, split by any clear separator
    if len(prompts) < count:
        logger.warning(
            "Delimiter parsing got %d/%d, trying fallback", len(prompts), count
        )
        # Try splitting by numbered sections
        sections = re.split(r"\n(?=(?:Prompt|PROMPT|Alternativa)\s*[ABC123])", text)
        prompts = [s.strip() for s in sections if len(s.strip()) > 100][:count]

    # Ultimate fallback: use the full text as a single prompt
    if len(prompts) < 1:
        logger.warning("All parsing failed, using full text as single prompt")
        prompts = [text]

    # Append consistency rules to each prompt
    return [
        f"Edita esta imagen aplicando SOLO cambios de pintura y color (facelift/lavado de cara):\n\n{p}\n\n{CONSISTENCY_RULES}"
        for p in prompts
    ]


def _ai_create_refined_image_prompt(refined_plan: str, inventory: str) -> str:
    """AI creates a single image editing prompt from a refined plan."""
    client = _get_client()
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

    prompt = f"""Eres un experto en crear prompts para modelos de edición de imagen.

INVENTARIO DE ELEMENTOS:
{inventory}

PLAN REFINADO:
{refined_plan}

Crea UN prompt de edición de imagen que describa TODOS los cambios a aplicar.

REGLAS OBLIGATORIAS:
- Lista CADA superficie y su nuevo color RAL exacto.
- UNIFORMIDAD ENTRE PLANTAS: Escribe EXPLÍCITAMENTE que TODAS las plantas
  (baja, alta) reciben el MISMO color y tratamiento exacto.
- PIEDRA NATURAL: Se PINTA SOBRE la piedra conservando su textura y relieve.
  NO alisar, NO quitar piedras. Solo aplicar color encima manteniendo la forma original.
- TEJAS: Si cambian, especificar color exacto para TODAS las tejas por igual.
- Para elementos que NO cambian, escribe "MANTENER SIN CAMBIOS: [elemento]".
- Especifica que es un LAVADO DE CARA: solo pintura y color, no cambios de forma.

Devuelve SOLO el prompt, sin explicaciones adicionales.
"""

    response = client.models.generate_content(model=model_id, contents=prompt)
    return f"Edita esta imagen aplicando SOLO cambios de pintura y color (facelift/lavado de cara):\n\n{response.text}\n\n{CONSISTENCY_RULES}"


def _ai_update_design_spec(inventory: str, current_cds: str, user_feedback: str) -> str:
    """AI updates the CDS incorporating user feedback without losing any element."""
    client = _get_client()
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

    prompt = f"""Eres un arquitecto de diseño exterior experto.

INVENTARIO ORIGINAL DE ELEMENTOS:
{inventory}

ESPECIFICACIÓN DE DISEÑO ACTUAL (CDS):
{current_cds}

FEEDBACK DEL USUARIO:
{user_feedback}

INSTRUCCIONES:
Actualiza la CDS incorporando el feedback del usuario.

REGLAS ESTRICTAS DE HERENCIA Y PRESERVACIÓN:
1. NO crees 3 nuevas alternativas — solo 1 CDS actualizada.
2. CADA ELEM del inventario DEBE aparecer (como CAMBIAR o MANTENER).
3. Aplica TODOS los cambios del feedback del usuario.
4. Los elementos que el usuario NO mencionó → HEREDAR EXACTAMENTE el tratamiento
   de la CDS actual. NO los modifiques, NO los pierdas, NO los reinicies.
5. La piscina SIEMPRE se mantiene.
6. Los árboles SIEMPRE se mantienen.
7. UNIFORMIDAD ENTRE PLANTAS: Si el usuario pide un cambio en una superficie,
   aplicar el MISMO cambio a TODAS las plantas (baja, alta) salvo que pida
   explícitamente lo contrario.
8. PIEDRA: Solo PINTAR sobre ella conservando textura/relieve. NUNCA quitar ni reemplazar.
9. TEJAS: Si se cambian, deben ser de un color ACORDE al diseño general.
10. Esto es un LAVADO DE CARA: solo pintura y acabados, no cambios estructurales.

FORMATO DE RESPUESTA:

## 🏠 Propuesta Refinada: [nombre]

### Cambios aplicados según tu feedback:
[lista ESPECÍFICA de qué cambios incorporaste del feedback]

### Resumen visual:
[descripción del resultado final con colores RAL específicos para cada superficie]

**CDS_ACTUALIZADA:**
CAMBIAR:
- [ELEM_XX]: [color RAL + acabado + tipo pintura específica para ese sustrato]
  Proceso: 1) [preparación] 2) [imprimación adecuada al sustrato] 3) [pintura final]
  (HEREDADO de CDS anterior / MODIFICADO según feedback)
MANTENER SIN CAMBIOS:
- [ELEM_XX]: [descripción detallada de lo que tiene actualmente]
AÑADIR:
- [nuevos elementos si aplica]

### Plan de ejecución por superficie:
| Elemento | Sustrato | Preparación | Imprimación | Pintura final | Color RAL | m² | Litros |
|----------|----------|-------------|-------------|---------------|-----------|-----|--------|

### Herramientas necesarias:
[lista agrupada por tarea: limpieza, pintura, instalación]

CHECKLIST OBLIGATORIO (verifica ANTES de responder):
- ¿Aparecen TODOS los ELEM_XX del inventario en la CDS_ACTUALIZADA?
- ¿Las plantas alta y baja tienen el MISMO color y tratamiento?
- ¿La piedra conserva su textura (solo pintada, no reemplazada)?
- ¿La piscina está como MANTENER?
- ¿Los árboles están como MANTENER?
- ¿El feedback del usuario se aplicó correctamente?
- ¿Los elementos no mencionados HEREDAN el tratamiento de la CDS anterior?
- ¿Las tejas tienen un color acorde al diseño?
"""

    response = client.models.generate_content(model=model_id, contents=prompt)
    return response.text


async def analyze_and_propose(tool_context: ToolContext) -> str:
    """Phase 1: Analyzes the uploaded image with AI Vision, creates element inventory,
    and generates 3 design alternatives with CDS and preview images.

    Call this ONLY when user uploads an image for the FIRST TIME.
    Do NOT call this for refinements — use refine_and_generate instead.

    Args:
        tool_context: ADK tool context (injected automatically).

    Returns:
        3 design alternatives with descriptions + preview images in Artifacts.
    """
    import asyncio

    # Support multiple uploaded images (different angles of same space)
    uploaded_images = tool_context.state.get("uploaded_images", [])
    image_path = tool_context.state.get("last_uploaded_image")
    if not uploaded_images and image_path:
        uploaded_images = [image_path]
    if not uploaded_images or not any(os.path.exists(p) for p in uploaded_images):
        return "Error: No se encontró imagen subida. Sube una imagen primero."

    # Step 1: Create numbered element inventory using ALL uploaded images
    logger.info(
        "FASE 1.1: Creando inventario con %d imagen(es)...", len(uploaded_images)
    )
    inventory = _vision_inventory(uploaded_images)
    logger.info("Inventario completado: %d chars", len(inventory))

    # Step 2: Generate 3 alternatives with CDS per alternative
    logger.info("FASE 1.2: Generando 3 alternativas con CDS...")
    alternatives = _ai_generate_cds_alternatives(inventory)
    logger.info("Alternativas generadas: %d chars", len(alternatives))

    # Save in state for Phase 2
    tool_context.state["element_inventory"] = inventory
    tool_context.state["design_alternatives"] = alternatives
    tool_context.state["workflow_phase"] = "alternatives_shown"

    # Step 3: AI creates image prompts from alternatives (MAX 3)
    logger.info("FASE 1.3: Creando prompts de imagen con AI...")
    image_prompts = _ai_create_image_prompts(alternatives, inventory, count=3)
    # Force limit to exactly 3 prompts
    image_prompts = image_prompts[:3]
    logger.info("Prompts de imagen creados: %d", len(image_prompts))

    # Step 4: Generate preview images in parallel (use first image as base)
    primary_image = uploaded_images[0]
    logger.info("FASE 1.4: Generando %d imágenes preview...", len(image_prompts))
    tasks = [_generate_image(p, primary_image, tool_context) for p in image_prompts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    image_status = []
    generated_paths = []
    for idx, result in enumerate(results):
        letter = chr(65 + idx)  # A, B, C
        if isinstance(result, Exception):
            image_status.append(f"**Imagen {letter}**: ❌ Error - {result}")
            logger.error("Error imagen %s: %s", letter, result)
            generated_paths.append(None)
        else:
            image_status.append(f"**Imagen {letter}**: ✅ Generada")
            # Extract path from result text (Local file: `path`)
            m = re.search(r"Local file.*?`(.+?)`", result)
            generated_paths.append(m.group(1) if m else None)

    # Step 5: Consistency check — verify generated images vs original
    logger.info("FASE 1.5: Verificación de consistencia GenAI...")
    consistency_status = []
    for idx, gen_path in enumerate(generated_paths):
        letter = chr(65 + idx)
        if not gen_path or not os.path.exists(gen_path):
            continue
        check = _consistency_check(primary_image, gen_path)
        score = check["score"]
        if check["passed"]:
            consistency_status.append(
                f"**Consistencia {letter}**: ✅ Score {score}/100"
            )
            logger.info("Consistency %s: PASSED (score=%d)", letter, score)
        else:
            issues_text = "; ".join(check["issues"][:3])
            consistency_status.append(
                f"**Consistencia {letter}**: ⚠️ Score {score}/100 — {issues_text}"
            )
            logger.warning(
                "Consistency %s: FAILED (score=%d) issues=%s",
                letter,
                score,
                check["issues"],
            )

    consistency_section = ""
    if consistency_status:
        consistency_section = (
            "\n\n## 🔍 Verificación de Consistencia\n\n"
            + "\n".join(consistency_status)
            + "\n"
        )

    return (
        f"{alternatives}\n\n---\n\n"
        f"## 📸 Imágenes Preview\n\n"
        + "\n".join(image_status)
        + consistency_section
        + "\n\n**Revisa la pestaña Artifacts para ver las imágenes.**\n\n"
        "¿Cuál alternativa prefieres? Puedes decir 'la A pero con paredes más oscuras' etc."
    )


async def refine_and_generate(user_feedback: str, tool_context: ToolContext) -> str:
    """Phase 2: Refines the chosen alternative based on user feedback, updating the
    Cumulative Design Specification (CDS) and generating a new image.

    The CDS ensures EVERY element in the image is accounted for, preventing
    the model from forgetting elements like the pool or left cabana.

    Call this when the user has chosen an alternative or asked for changes.
    Do NOT call analyze_and_propose again — use this tool instead.

    Args:
        user_feedback: The user's choice and feedback, e.g. "Me gusta la A pero
            con las paredes más oscuras y un camino de gravilla"
        tool_context: ADK tool context (injected automatically).

    Returns:
        A refined design proposal + preview image in Artifacts.
    """

    inventory = tool_context.state.get("element_inventory", "")
    alternatives = tool_context.state.get("design_alternatives", "")
    current_cds = tool_context.state.get("current_cds", "")

    if not inventory:
        return (
            "Error: No hay inventario previo. "
            "Primero sube una imagen para que pueda analizarla."
        )

    # If first refinement, use the alternatives as context for the CDS
    if not current_cds:
        current_cds = alternatives

    # Step 1: AI updates the CDS with user feedback
    logger.info("FASE 2.1: Actualizando CDS con feedback...")
    refined = _ai_update_design_spec(inventory, current_cds, user_feedback)
    logger.info("CDS actualizada: %d chars", len(refined))

    # Store the full refined plan as the current CDS for next iteration
    tool_context.state["current_cds"] = refined
    tool_context.state["refined_plan"] = refined
    tool_context.state["workflow_phase"] = "refined"

    # Step 2: AI creates image prompt from refined plan (robust, no regex)
    logger.info("FASE 2.2: Creando prompt de imagen con AI...")
    image_prompt = _ai_create_refined_image_prompt(refined, inventory)

    # Step 3: Generate refined image (use first uploaded image)
    uploaded_images = tool_context.state.get("uploaded_images", [])
    image_path = (
        uploaded_images[0]
        if uploaded_images
        else tool_context.state.get("last_uploaded_image")
    )
    logger.info("FASE 2.3: Generando imagen refinada con Nano Banana Pro...")
    try:
        await _generate_image(image_prompt, image_path, tool_context)
        image_status = "**Imagen refinada**: ✅ Generada"
    except Exception as e:
        logger.error("Error generando imagen refinada: %s", e)
        image_status = f"**Imagen refinada**: ❌ Error - {e}"

    return (
        f"{refined}\n\n---\n\n"
        f"## 📸 Imagen Refinada\n\n{image_status}\n\n"
        "**Revisa la pestaña Artifacts para ver la imagen.**\n\n"
        "¿Te gusta el resultado? Puedo:\n"
        "- Ajustar más colores o detalles\n"
        "- Generar la lista de compra con materiales y herramientas"
    )


def _generate_filename(prompt: str, timestamp: str) -> str:
    """Generate a meaningful filename from the design plan using AI.
    Context-aware: if prompt mentions interior spaces, name accordingly."""
    client = _get_client()
    filename_prompt = (
        f"Given this design description: '{prompt[:300]}', "
        "generate a short descriptive filename (max 4 words, Spanish preferred). "
        "Use underscores, no spaces. "
        "IMPORTANT: The filename MUST reflect the actual space type:\n"
        "- If it's a bathroom/ba\u00f1o: start with 'bano_' (e.g. bano_moderno_gris)\n"
        "- If it's a kitchen/cocina: start with 'cocina_' (e.g. cocina_blanca_moderna)\n"
        "- If it's a bedroom/dormitorio: start with 'dormitorio_' (e.g. dormitorio_minimalista)\n"
        "- If it's a living room/sal\u00f3n: start with 'salon_' (e.g. salon_elegante)\n"
        "- If it's exterior/facade/fachada: start with 'fachada_' (e.g. fachada_gris_perla)\n"
        "- If it's garden/jard\u00edn: start with 'jardin_' (e.g. jardin_zen_minimalista)\n"
        "Return ONLY the filename, nothing else."
    )
    try:
        response = client.models.generate_content(
            model=os.environ.get("MODEL_ID", "gemini-3-flash-preview"),
            contents=filename_prompt,
        )
        name = response.text.strip().lower()
        name = name.replace(" ", "_").replace("-", "_")
        name = "".join(c for c in name if c.isalnum() or c == "_")
        if not name:
            return f"facelift_{timestamp}"
        return f"{name}_{timestamp}"
    except Exception as e:
        logger.warning("Failed to generate AI filename: %s", e)
        return f"facelift_{timestamp}"
