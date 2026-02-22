# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2026-02-22

### Added — GCS Image Storage, "Don't Fix What's Good" Guardrails, Bug Fixes

**GCS Bucket for Image Storage:**
- `terraform/main.tf`: Added `google_storage_bucket.images` (bucket name: `{project}-facelift-images`)
  with public read access, CORS config, and 365-day lifecycle rule.
- `google_project_service.storage` enables Cloud Storage API before bucket creation.
- `app/gcs_storage.py`: New utility module with `upload_image()` and `upload_bytes()`.
  Lazy-init GCS client, graceful fallback to local storage if GCS unavailable.
- Uploaded images → `uploads/{user_id}/filename` in GCS.
- Generated images → `generated/{user_id}/filename` in GCS.
- GCS URLs stored in session state (`gcs_upload_urls`) for Firestore referencing.

**"Don't Fix What's Good" Guardrails (REGLA DE ORO):**
- **Philosophy**: Maximize WOW effect with MINIMUM investment. If something is already
  in good condition (parquet floor, white ceiling, clean walls) → DO NOT CHANGE IT.
- `_vision_inventory()`: New field `¿Merece cambio?: SÍ/NO` for each element.
  Elements marked NO are guardrailed as MANTENER in all alternatives.
- `_ai_generate_cds_alternatives()`: Explicit rules that elements with "¿Merece cambio?: NO"
  MUST be MANTENER. Parquet in good condition → ALWAYS KEEP. White ceiling → ALWAYS KEEP.
- `CONSISTENCY_RULES`: Added "REGLA DE ORO" — suelo/parquet in good condition must appear
  IDENTICAL in generated image. Techo and paredes in good condition → MANTENER.
- `prompts.py`: All three agent instructions (Master, Exterior, Interior) now include
  the REGLA DE ORO guardrails. Interior designer has specific rules for parquet, accent walls,
  and prioritizing high-impact low-cost changes (lighting, textiles, paint accents).

**Bug Fix: Image Accumulation Across Turns (5 images instead of 2):**
- `uploaded_images` state list was appending forever across turns. If user sent 2 images
  in turn 1, then 2 more in turn 2, the list had 4+ images (plus any from previous sessions).
- **Fix**: `_persist_uploaded_images` now tracks `current_turn_images` locally and REPLACES
  `uploaded_images` state (not appends) when new images arrive. If no new images in a turn,
  the previous turn's images are preserved for tools to use.

**Bug Fix: 'anon' in Generated Image Filenames:**
- `_generate_image()` reads `tool_context.state.get("_user_id", "anon")` but `_user_id`
  was never stored in state.
- **Fix**: `_persist_uploaded_images` callback now stores `state["_user_id"] = user_id` and
  `state["_session_id"] = session_id` so all tools can access the real user identity.

### Changed
- `app/agent.py`: Store `_user_id`/`_session_id` in state, reset `uploaded_images` per turn,
  GCS upload integration, `_upload_version` only increments when new images arrive.
- `app/tools.py`: Import `gcs_storage`, upload generated images to GCS, `_vision_inventory`
  adds "¿Merece cambio?" field, `_ai_generate_cds_alternatives` has REGLA DE ORO guardrails,
  `CONSISTENCY_RULES` updated with floor/ceiling preservation rules.
- `app/prompts.py`: All agent instructions updated with REGLA DE ORO philosophy.
- `terraform/main.tf`: Added GCS bucket + Storage API enablement.
- New file: `app/gcs_storage.py`.

## [1.1.0] - 2026-02-22

### Added — Image Display Fix, Multi-Upload, Descriptive Filenames, Consistency Improvements

**ULTRA FIX: Broken Images in Carousel:**
- Images were not visible in the frontend carousel (broken `<img>` tags).
- **Root cause**: Frontend was fetching artifacts via base64 data URLs through the ADK artifact API,
  which was fragile and often failed.
- **Fix**: Vite plugin `serveLocalFiles()` in `frontend/vite.config.js` serves `/static/` and
  `/uploads/` directories directly from the project root. Generated images now load as
  `/static/{filename}.png` — fast, reliable, cacheable.
- `AlternativeCarousel.jsx` now uses direct `/static/` URLs instead of base64 data URLs.
- Added `onError` fallback on `<img>` tags to show placeholder if image fails to load.

**Original Image in Carousel:**
- The original uploaded photo is now displayed as the FIRST card in the carousel with an
  amber "ORIGINAL" badge, so users can visually compare before/after.
- Multiple original images (different angles) shown as thumbnails below the main original.
- `originalImages` state tracks all uploaded images as data URLs across the session.

**Click-to-Zoom Lightbox:**
- All images (original + generated alternatives) are now clickable.
- Clicking opens a fullscreen lightbox overlay with the image at maximum resolution.
- `ZoomIn` icon indicator on each image. Close with X button or click outside.

**Multiple Image Uploads:**
- `ImageUpload.jsx` now supports `multiple` file selection (HTML `multiple` attribute).
- Users can upload several photos of the same room from different angles.
- All pending images shown as removable thumbnails with individual ✕ buttons.
- Backend `_vision_inventory()` now accepts `list[str]` of image paths and sends ALL
  images to Gemini Vision for a more complete element inventory.
- Multi-image note injected into the vision prompt when >1 image is provided.

**Descriptive Filenames (project_style_room_version):**
- **Uploads**: `{user}_{style}_{type}_{name}_v{N}_{idx}_{uuid}.{ext}`
  e.g. `casa_alovera_moderno_dormitorio_principal_v0_0_a3b2c1.jpg`
- **Generated images**: `{user}_{style}_{type}_{descriptive}_{vN}_{uuid}.png`
  e.g. `casa_alovera_moderno_dormitorio_fachada_gris_seda_v0_d914a9.png`
- Filename parts sourced from session state (`project_style`, `section_type`, `section_name`).
- Generic defaults used if frontend values unavailable (`moderno`, `general`, `seccion`).

**Terraform: Firestore API Activation:**
- `terraform/main.tf` now includes `google_project_service.firestore` resource that enables
  `firestore.googleapis.com` API BEFORE creating the database.
- `google_firestore_database.facelift` has `depends_on` to ensure correct ordering.
- Fixes the `SERVICE_DISABLED` error on first `terraform apply`.

### Changed
- `frontend/src/components/ChatPanel.jsx`: Complete refactor of image handling — multi-image
  support, `pendingImages[]` array, `originalImages[]` tracking, direct `/static/` URLs.
- `frontend/src/components/ImageUpload.jsx`: `processFiles()` handles multiple files,
  `onImageSelect` now receives `[{base64, mime}, ...]` array.
- `frontend/src/components/AlternativeCarousel.jsx`: Original image card, lightbox zoom,
  `onError` fallback, `ZoomIn`/`X` icons from lucide-react.
- `app/agent.py`: Descriptive filenames with project/style/room/version in `_persist_uploaded_images`.
- `app/tools.py`: `_vision_inventory()` accepts `list[str]`, multi-image Gemini Vision,
  descriptive generated filenames, `analyze_and_propose` uses all uploaded images.
- `terraform/main.tf`: Added `google_project_service.firestore` with `depends_on`.
- Removed `getArtifact` import from `adk-client.js` (no longer needed).

## [1.0.0] - 2026-02-22

### Added — Multi-Agent Architecture, Persistent Memory, Concurrency & PDF Export

**Multi-Agent Architecture (ADK sub_agents):**
- **MasterDesigner** (root): Orchestrates and delegates based on space type.
  Determines if image is exterior or interior and routes to the correct specialist.
- **ExteriorDesigner** (sub-agent): Fachadas, jardines, terrazas, piscinas, caminos.
  Has `analyze_and_propose`, `refine_and_generate`, `search_products` + `PreloadMemoryTool`.
- **InteriorDesigner** (sub-agent): Baños, cocinas, dormitorios, salones.
  Specialized materials (pintura azulejos, porcelánico, microcemento). NEVER proposes gravilla.
- ADK `transfer_to_agent` mechanism routes automatically based on LLM analysis of image content.

**Hierarchical Persistent Memory (Firestore + local fallback):**
- `app/memory_store.py`: Dual-mode persistence — Google Cloud Firestore (cloud) + local JSON (fallback).
- **Project-level memory**: Stores central style, `style_summary`, `sections_overview`.
- **Section-level memory**: Stores section type, style refinements, last CDS (truncated).
- **Propagation**: When a section is updated, parent project `sections_overview` is refreshed.
- **Memory injection**: `before_model_callback` injects `[MEMORIA DEL PROYECTO]` context
  from all sections into the LLM request so agents know about previous design decisions.
- **Terraform**: `terraform/main.tf` creates GCP Firestore database (`facelift-memory`)
  in `capella-vertex-rag` / `europe-west1`. Run `cd terraform && terraform init && terraform apply`.
- `google-cloud-firestore` added to dependencies.
- ADK `InMemoryMemoryService` enabled (auto by `adk api_server`).
- `PreloadMemoryTool` on sub-agents for cross-session recall.
- Data persists across server restarts (local JSON in `.adk/memory/`, or Firestore).

**Concurrency & Multi-User Fixes:**
- **Image overwriting fixed**: Uploaded images now saved as
  `{user_id}__{session_id}__{timestamp}_{index}_{uuid}.{ext}` — never overwritten.
- **'anon' filenames fixed**: Real `user_id` and `session_id` extracted from
  `callback_context._invocation_context.session` (was using `getattr` which returned None).
- **Multiple images supported**: `uploaded_images` state key stores list of all uploads.
- **Generated images**: Filenames include `{user_id}__{descriptive_name}_{uuid}.png`.
- **Context-aware naming**: Interior images named `bano_*`, `cocina_*`, `dormitorio_*`
  instead of always `fachada_*`. AI prompt for filename generation now enforces space-type prefix.

**Image Upload UX Fix (Frontend):**
- Uploading an image NO LONGER auto-sends the chat. User can attach image, then type
  their own message before sending. If no text typed, a default analysis prompt is used.

**PDF Shopping List Export (Frontend):**
- New "PDF" button in chat header downloads a formatted PDF with:
  - Project name, section, date
  - Product list with prices
  - Clickable store search links (Leroy Merlin, ManoMano, Bricomart, Amazon)
  - Footer disclaimer about price verification
- Uses `jspdf` library for client-side PDF generation.

**make dev fix (Windows):**
- `make dev` now opens TWO SEPARATE cmd windows: one for backend, one for frontend.
- Backend starts first with 5s delay before frontend launches.
- Each window shows its own logs independently.

**Proxy Error Handling:**
- Vite proxy now catches ECONNRESET/ECONNREFUSED gracefully.
- Returns 502 JSON error instead of crashing when backend is not ready.

**Product Search Improvements:**
- Prompts now explicitly forbid hallucinated URLs.
- Only verified store search links (query-based) are returned.

### Changed
- `app/prompts.py`: Now exports `MASTER_DESIGNER_INSTRUCTION`,
  `EXTERIOR_DESIGNER_INSTRUCTION`, `INTERIOR_DESIGNER_INSTRUCTION` (was single `ROOT_AGENT_INSTRUCTION`).
- `app/agent.py`: Multi-agent setup with `sub_agents`, unique image filenames, memory callbacks,
  hierarchical memory injection.
- `app/tools.py`: `uuid` in all generated filenames, `re` import at top, context-aware `_generate_filename`.
- `frontend/vite.config.js`: Proxy error handler for graceful 502 responses.
- `frontend/src/components/ChatPanel.jsx`: Image upload no longer auto-sends.
- `Makefile`: `make dev` opens separate Windows cmd windows.

## [0.9.0] - 2026-02-22

### Added — Custom React Frontend + Context-Aware Gravilla Fix

**Frontend (React + Vite + TailwindCSS):**
- Custom frontend that connects to ADK via `adk api_server` REST + SSE streaming.
- **Project management**: Organiza reformas por proyecto (userId en ADK) con secciones
  (sessionId en ADK) — fachada, baño, cocina, etc.
- **Estilo central por proyecto**: Cada proyecto tiene un estilo predeterminado
  ("moderno elegante") que todas las secciones heredan.
- **Chatbot con imágenes**: Sube fotos directamente desde el chat. Se envían como
  base64 `inlineData` al endpoint `/run_sse` de ADK.
- **Carrusel de alternativas**: Las 3 alternativas se muestran en tarjetas horizontales
  con imagen arriba y texto explicativo abajo. PC = 3 cards visibles, mobile = scroll
  horizontal con snap. Cada tarjeta tiene botón "Elegir" + "Más" para detalle técnico.
- **Artifacts de ADK**: Las imágenes generadas se obtienen via
  `GET /apps/app/users/{userId}/sessions/{sessionId}/artifacts/{name}` y se muestran
  como `data:` URLs en el carrusel.
- **Streaming SSE**: Los mensajes del agente se muestran token a token en tiempo real.
- **Persistencia local**: Proyectos y secciones se guardan en localStorage.
- **Responsive**: Sidebar colapsable en móvil, carrusel con scroll snap, layout adaptativo.

**Nuevos targets en Makefile:**
- `make frontend-install` — Instalar dependencias npm del frontend.
- `make frontend` — Iniciar dev server Vite (puerto 3000, proxy a ADK 8000).
- `make backend` — Iniciar ADK API server (puerto 8000).
- `make dev` — Iniciar backend + frontend juntos.

**Bug fix — Gravilla solo en exteriores:**
- La gravilla se proponía en TODOS los espacios (incluidos baños e interiores).
- Ahora la regla en `_ai_generate_cds_alternatives` especifica:
  "Gravilla → SOLO en EXTERIORES. NUNCA en interiores, baños ni cocinas."
  Para interiores propone suelo porcelánico, microcemento o similar.
- La sección "Adicionales" del formato CDS ahora dice
  "SOLO si tienen sentido para el TIPO de espacio" con guía contextual.

## [0.8.0] - 2026-02-22

### Changed — Consistency, Material Awareness & CDS Drift Prevention

**7 problemas resueltos de la conversación real:**

1. **Texto de alternativas no se mostraba** — Root agent ahora usa `ROOT_AGENT_INSTRUCTION`
   (importado de `prompts.py`) que OBLIGA a mostrar el texto ÍNTEGRO devuelto por las
   herramientas. Antes usaba una instrucción inline de 25 líneas que no lo exigía.

2. **Diseño inconsistente entre plantas** (baja ≠ alta) — Nueva regla de UNIFORMIDAD
   ENTRE PLANTAS en TODOS los prompts: `_vision_inventory`, `_ai_generate_cds_alternatives`,
   `_ai_create_image_prompts`, `_ai_create_refined_image_prompt`, `_ai_update_design_spec`,
   y `CONSISTENCY_RULES`. El inventario ahora agrupa elementos POR PLANTA.

3. **Piedras destruidas/reemplazadas** en vez de pintadas — Reforzado "PRESERVAR TEXTURAS"
   en `CONSISTENCY_RULES` + lista explícita de CAMBIOS PROHIBIDOS. Todos los image prompts
   ahora dicen "LAVADO DE CARA: solo pintura y color, no cambios de forma".

4. **CDS drift** (olvida piedras, pierde elementos entre iteraciones) — `_ai_update_design_spec`
   ahora tiene reglas de HERENCIA ("HEREDAR EXACTAMENTE el tratamiento de la CDS anterior"),
   marcadores HEREDADO/MODIFICADO, y CHECKLIST OBLIGATORIO de validación antes de responder.

5. **Sin conciencia de materiales** (exterior vs interior, impermeabilizante, proceso técnico) —
   `_vision_inventory` ahora identifica sustrato, exposición y preparación necesaria.
   `_ai_generate_cds_alternatives` incluye PROCESO TÉCNICO por superficie
   (hidrolavado → imprimación → pintura) con tipo de pintura específico por sustrato.
   `_ai_update_design_spec` genera tabla de ejecución con sustrato/preparación/imprimación/pintura.

6. **Tejas inconsistentes** — Regla explícita: "TEJAS: Si se especifica un color, aplicar a
   TODAS las tejas por igual" en `CONSISTENCY_RULES` + regla en alternatives y refined prompts.

7. **Enlaces verificados no aparecían** — `search_products` ahora formatea los enlaces de
   búsqueda directa con `🔗 Enlaces de búsqueda directa (verificados, siempre funcionan)`
   + nota de precios orientativos. Root agent instruction exige mostrarlos destacados.
   Añadida cláusula de honestidad: "Do NOT invent product names, SKUs, or prices."

**Cambios de arquitectura:**
- `prompts.py`: Reescrito completo — ahora contiene `ROOT_AGENT_INSTRUCTION` (antes tenía
  3 prompts obsoletos `ORCHESTRATOR_PROMPT`, `DESIGN_EXPERT_PROMPT`, `PRODUCT_FINDER_PROMPT`
  que NO se importaban en ningún sitio).
- `agent.py`: Importa `ROOT_AGENT_INSTRUCTION` de `prompts.py` en vez de instrucción inline.
- `custom_agents.py`: Limpiado código muerto (importaba funciones inexistentes
  `analyze_uploaded_image`, `apply_facelift_image_edit`).
- Ruff + format passing.

## [0.7.0] - 2026-02-22

### Changed — CDS Architecture + Nano Banana Pro (consistency fix)

**Problemas resueltos:**
1. Piscina desaparecía entre iteraciones
2. Caseta izquierda quedaba naranja aunque se pidiera pintar
3. Colores revertían al original sin aviso
4. Se usaba modelo de imagen básico (gemini-2.5-flash-image)

**Modelo de imagen**: `gemini-3-pro-image-preview` (Nano Banana Pro — frontier de Google, 4K)

**CDS (Cumulative Design Specification):**
- `_vision_inventory()` crea inventario NUMERADO (ELEM_01, ELEM_02...) de cada elemento visible
- Cada alternativa genera un CDS con CAMBIAR / MANTENER / AÑADIR para CADA elemento
- `_build_image_prompt_from_cds()` construye prompt con secciones explícitas DO/DON'T
- `_ai_update_design_spec()` actualiza el CDS acumulativamente (nunca pierde elementos)
- El CDS se guarda en `session.state["current_cds"]` y se acumula entre iteraciones

**Reglas de consistencia en el prompt de imagen:**
- Elementos MANTENER → quedar EXACTAMENTE como en la original
- Piscina → SIEMPRE visible, nunca eliminar
- Árboles → SIEMPRE en su posición
- NO mover elementos estructurales
- Solo cambiar COLORES y ACABADOS listados

## [0.6.0] - 2026-02-22

### Changed — AI-Driven Architecture (no more hardcoded alternatives)

**Problema resuelto**: Las alternativas eran hardcoded y el sistema siempre llamaba al mismo tool.

**Nueva arquitectura con 2 tools separados:**
- **`analyze_and_propose`** (Fase 1): Gemini Vision analiza la imagen REAL → AI genera 3 alternativas BASADAS en el análisis → 3 imágenes preview en paralelo
- **`refine_and_generate`** (Fase 2): AI refina la alternativa elegida con el feedback del usuario → genera imagen final
- El LLM decide qué tool usar según el contexto (imagen nueva → Phase 1, feedback → Phase 2)

**Flujo de datos AI-driven:**
1. `_vision_inventory()` — Gemini Vision crea inventario numerado de cada elemento
2. `_ai_generate_cds_alternatives()` — AI genera 3 alternativas con CDS completo
3. `_ai_update_design_spec()` — AI actualiza CDS acumulativo con feedback (NO crea 3 nuevas)
4. Inventario + CDS guardados en `session.state` para consistencia entre iteraciones

**Reglas de diseño embebidas en AI:**
- Piedra vieja → pintar negro/antracita
- Paredes naranja → pintar gris/blanco
- Muros bloque/ladrillo feos → enfoscar y pintar como la casa
- Metal oxidado → imprimación + esmalte negro
- Casetas auxiliares → MISMO color que casa principal
- Caminos → gravilla blanca con espacio para caminar
- Eliminados: custom_agents.py, prompts hardcoded

## [0.5.3] - 2026-02-22

### Fixed — Generate 3 Preview Images in Phase 1
- **Orchestrator** ahora genera 3 IMÁGENES PREVIEW automáticamente en Fase 1 (una por cada alternativa A, B, C).
- **DesignExpert** incluye `PROMPT_PARA_IMAGEN` con cada alternativa para generar la imagen preview.
- **Flujo corregido**:
  - Fase 1: Análisis → 3 alternativas CON 3 imágenes preview → usuario ve las 3 imágenes y elige
  - Fase 2: Plan detallado basado en la elección del usuario
  - Fase 3: Imagen FINAL refinada con el plan completo
  - Fase 4-5: Búsqueda de productos y presentación
- Usuario puede comparar visualmente las 3 alternativas antes de decidir.
- Genera 4 imágenes en total: 3 previews + 1 final.

## [0.5.2] - 2026-02-22

### Added — Tools & Equipment Search
- **DesignExpert** ahora incluye sección 🛠️ HERRAMIENTAS Y EQUIPOS en el plan detallado:
  - Limpieza: limpiadora a presión, cepillos, rasquetas, lijadoras
  - Pintura: rodillos (tipo y tamaño), brochas, pistola pintura HVLP, cubetas, cinta carrocero
  - Instalación eléctrica: taladro percutor, brocas hormigón, destornilladores, cable eléctrico, tacos, tornillos
  - Paisajismo: palas, rastrillos, carretillas, malla antihierbas
- **ProductFinder** busca MATERIALES Y HERRAMIENTAS con queries específicos.
- **Salida separada en 2 secciones**: 🎨 MATERIALES + 🛠️ HERRAMIENTAS con uso específico de cada herramienta.
- **Presupuesto desglosado**: Subtotal materiales + Subtotal herramientas + Total proyecto.
- Ejemplos de búsqueda para herramientas (limpiadora Karcher K4 130bar, rodillo fachada 25cm, pistola Wagner W550 HVLP, taladro Bosch 18V, etc.).

## [0.5.1] - 2026-02-22

### Fixed — 3-Alternative Workflow & Modern Design Defaults
- **3 alternativas de diseño**: DesignExpert ahora presenta 3 opciones visuales breves (paleta, concepto) antes de crear el plan detallado.
- **Flujo de 2 fases con el usuario**: Fase 1 (análisis + 3 alternativas) → usuario elige → Fase 2 (plan detallado + imagen + productos).
- **Auto-proceed**: El orquestador ya NO pide confirmación entre generar imagen y buscar productos. Fases 3-5 son automáticas.
- **Diseño moderno funcional por defecto (2026)**:
  - Piedra obsoleta → se pinta SIEMPRE (imprimación silicato + pintura mineral, negro RAL 9005 o antracita RAL 7016).
  - Paredes estuco → blanco roto RAL 9010 / gris claro RAL 7035 con pintura siloxánica.
  - Metal → imprimación antioxidante + esmalte negro satinado RAL 9005.
  - Madera → lasur exterior nogal oscuro / ébano / gris envejecido.
- **Imprimaciones específicas por sustrato**: silicato para piedra, antioxidante para metal, fijadora para estuco.
- **Año corregido**: todas las referencias son 2026, no 2024.
- **Prompts en español**: todo el sistema responde en español por defecto.

## [0.5.0] - 2026-02-22

### Changed — Multi-Agent Architecture Redesign
- **Root orchestrator** (`HomeFaceliftCopilot`): coordinates the full workflow, delegates to sub-agents.
- **DesignExpert sub-agent**: analyzes uploaded image (surfaces, materials, colors, areas) and creates a precise design plan with exact RAL/NCS codes, paint types per substrate, lighting specs (K, lumens, IP), plant species, and quantities.
- **ProductFinder sub-agent**: searches each product individually with SPECIFIC queries (not generic) on Leroy Merlin, ManoMano, Bricomart, Amazon ES.
- **Guaranteed-valid links**: store search URLs are constructed programmatically (`leroymerlin.es/buscador?query=...`) — always work, never 404.
- **New tool `analyze_uploaded_image`**: sends image to Gemini Vision for exhaustive surface/material analysis before any design decisions.
- **New tool `search_products`**: searches one specific product at a time with Google Search grounding + builds valid store search links.
- **Removed**: `_extract_design_elements` (generic keyword matching), `search_shopping_list` (replaced by per-product `search_products`).
- **Workflow**: DesignExpert analyzes → plans with RAL codes → Orchestrator generates image → ProductFinder searches real products.

## [0.4.0] - 2026-02-22

### Added
- **AI-generated meaningful filenames**: `_generate_filename_from_prompt()` uses AI to create descriptive filenames (e.g., `casa_mediterranea_moderna_20240222.png`) instead of generic timestamps.
- **Design element extraction**: `_extract_design_elements()` automatically extracts colors, materials, and items from user prompts.
- **Shopping list tool**: `search_shopping_list()` searches Leroy Merlin, Bricomart, Brico Depôt, AKI, and ManoMano for exact products with:
  - Product codes/SKUs
  - Prices in €
  - Direct store links
  - 2-3 cheaper alternatives per item
- **Updated system prompt**: Instructs agent to automatically call `search_shopping_list` after image generation.

### Changed
- `apply_facelift_image_edit` now extracts and stores design elements in session state.
- Added `search_shopping_list` tool to agent.
- Image files saved with descriptive names in `./static/`.

## [0.3.0] - 2026-02-22

### Fixed
- **500 INTERNAL error**: wrong image model name; now uses correct `gemini-2.5-flash-image` (Nano Banana) or `gemini-3-pro-image-preview` (Nano Banana Pro).
- **Image upload**: added `before_model_callback` to persist user-uploaded images from inline data to `./uploads/` and store path in session state.
- **ToolContext**: `apply_facelift_image_edit` now reads image from `tool_context.state` instead of hallucinated file paths.

### Added
- `IMAGE_MODEL` env var to switch between Nano Banana (`gemini-2.5-flash-image`) and Nano Banana Pro (`gemini-3-pro-image-preview`).
- Generated images saved to `./static/` with timestamps for local download.
- Generated images saved as **ADK artifacts** — viewable/downloadable from the Artifacts tab in the ADK UI.
- Async `apply_facelift_image_edit` tool with `await tool_context.save_artifact()`.

## [0.2.0] - 2026-02-22

### Changed
- Switched auth from Vertex AI ADC to **Google AI Studio API key** (`GOOGLE_API_KEY`) — fixes 429 RESOURCE_EXHAUSTED quota errors.
- Switched model from `gemini-2.5-pro` to `gemini-3-flash-preview` (configurable via `MODEL_ID` env var).
- `app/tools.py` — lazy `genai.Client(api_key=...)` instead of Vertex AI client.
- `app/agent.py` — removed `google.auth.default()` and Vertex AI env vars; uses `MODEL_ID` from `.env`.
- `.env` — now uses `GOOGLE_API_KEY` + `MODEL_ID` pattern (matching working `ADK demo2` project).

## [0.1.0] - 2026-02-22

### Added
- Initial project scaffold via Google Agent Starter Pack (`adk` template).
- `app/prompts.py` — FACELIFT_SYSTEM_PROMPT with strict no-structural-changes rule.
- `app/tools.py` — `search_design_trends` (Google Search grounded via Gemini) and `apply_facelift_image_edit` (Nano Banana image editing).
- `app/agent.py` — HomeFaceliftCopilot agent assembly.
- `.env` file with GCP project config (gitignored).
- Local ADK playground running on port 8501.
