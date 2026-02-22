# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # Load .env before any Google SDK import

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools import preload_memory_tool
from app.prompts import (
    MASTER_DESIGNER_INSTRUCTION,
    EXTERIOR_DESIGNER_INSTRUCTION,
    INTERIOR_DESIGNER_INSTRUCTION,
)
from app.tools import (
    analyze_and_propose,
    refine_and_generate,
    search_products,
)
from app import memory_store
from app import gcs_storage

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")


def _persist_uploaded_images(callback_context, llm_request):
    """Before-model callback: save images + inject hierarchical memory context."""
    from google.genai import types as genai_types

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    # Get real user_id + session_id from ADK invocation context
    try:
        inv_ctx = callback_context._invocation_context
        user_id = inv_ctx.session.user_id or "anon"
        session_id = inv_ctx.session.id or "default"
    except Exception:
        user_id = "anon"
        session_id = "default"

    # Inject hierarchical memory context as system instruction
    try:
        section_id = session_id.split("__", 1)[1] if "__" in session_id else session_id
        ctx_text = memory_store.get_full_context(user_id, section_id)
        if ctx_text:
            memory_part = genai_types.Part(
                text=f"[MEMORIA DEL PROYECTO]\n{ctx_text}\n[/MEMORIA DEL PROYECTO]"
            )
            memory_content = genai_types.Content(role="user", parts=[memory_part])
            if llm_request.contents:
                llm_request.contents.insert(0, memory_content)
            logger.debug(
                "Injected project memory context for %s/%s", user_id, section_id
            )
    except Exception as e:
        logger.warning("Failed to inject memory context: %s", e)

    # Store user_id in state so tools (_generate_image) can access it
    state = callback_context.state
    state["_user_id"] = user_id
    state["_session_id"] = session_id

    # Build descriptive filename parts from session state
    project_style = (state.get("project_style") or "moderno")[:15].replace(" ", "_")
    section_type = (state.get("section_type") or "general")[:12].replace(" ", "_")
    section_name = (state.get("section_name") or "seccion")[:15].replace(" ", "_")
    version = state.get("_upload_version", 0)

    # Reset current_turn_images each turn — prevents accumulation across turns
    current_turn_images = []

    # Save uploaded images with descriptive names
    img_index = 0
    for content in llm_request.contents or []:
        if content.role != "user" or not content.parts:
            continue
        for part in content.parts:
            inline = getattr(part, "inline_data", None)
            if not inline:
                continue
            mime = getattr(inline, "mime_type", "") or ""
            if not mime.startswith("image/"):
                continue
            ext = mime.split("/")[-1].replace("jpeg", "jpg")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            short_id = uuid.uuid4().hex[:6]
            # Descriptive: project_style_room_version_index_uuid.ext
            filename = f"{user_id}_{project_style}_{section_type}_{section_name}_v{version}_{img_index}_{short_id}.{ext}"
            path = os.path.join(UPLOADS_DIR, filename)
            with open(path, "wb") as f:
                f.write(inline.data)
            current_turn_images.append(path)
            # Upload to GCS (non-blocking, fallback to local)
            gcs_url = gcs_storage.upload_image(path, gcs_folder=f"uploads/{user_id}")
            if gcs_url:
                gcs_urls = state.get("gcs_upload_urls", [])
                gcs_urls.append(gcs_url)
                state["gcs_upload_urls"] = gcs_urls
            logger.info("Saved uploaded image to %s", path)
            img_index += 1

    # Only update state if we actually got new images this turn
    if current_turn_images:
        state["_upload_version"] = version + 1
        # Replace uploaded_images with ONLY this turn's images (fix accumulation)
        state["uploaded_images"] = current_turn_images
        state["last_uploaded_image"] = current_turn_images[-1]
        logger.info("This turn: %d new image(s)", len(current_turn_images))
    # If no new images this turn, keep existing uploaded_images for tools to use

    return None


async def _save_memory_after_agent(callback_context):
    """After-agent callback: persist session to memory + hierarchical style memory."""
    try:
        inv_ctx = callback_context._invocation_context
        await inv_ctx.memory_service.add_session_to_memory(inv_ctx.session)
        logger.debug("Session memory saved")
    except Exception as e:
        logger.warning("Failed to save ADK session memory: %s", e)

    # Persist hierarchical style memory to Firestore/local
    try:
        state = callback_context.state
        inv_ctx = callback_context._invocation_context
        project_id = inv_ctx.session.user_id
        session_id = inv_ctx.session.id
        # Extract section_id from session_id (format: project__section)
        section_id = session_id.split("__", 1)[1] if "__" in session_id else session_id

        # Save project-level style if present
        project_style = state.get("project_style")
        if project_style:
            memory_store.save_project_memory(project_id, {"style": project_style})

        # Save section-level data
        section_data = {}
        section_type = state.get("section_type")
        if section_type:
            section_data["type"] = section_type
        cds = state.get("current_cds") or state.get("design_alternatives")
        if cds:
            section_data["last_cds"] = cds[:2000]  # Truncate for storage
            # Generate a brief style summary from the CDS
            section_data["style_summary"] = cds[:300]
        if section_data:
            memory_store.save_section_memory(project_id, section_id, section_data)
            logger.info("Saved hierarchical memory for %s/%s", project_id, section_id)
    except Exception as e:
        logger.warning("Failed to save hierarchical memory: %s", e)


# ─── Sub-agents: specialized designers ───────────────────────────────────────

exterior_designer = Agent(
    name="ExteriorDesigner",
    model=MODEL_ID,
    description=(
        "Especialista en diseño de EXTERIORES: fachadas, jardines, terrazas, "
        "piscinas, caminos, iluminación exterior. Delega aquí cuando la imagen "
        "sea de exterior o fachada."
    ),
    instruction=EXTERIOR_DESIGNER_INSTRUCTION,
    tools=[
        analyze_and_propose,
        refine_and_generate,
        search_products,
        preload_memory_tool.PreloadMemoryTool(),
    ],
    before_model_callback=_persist_uploaded_images,
    after_agent_callback=_save_memory_after_agent,
)

interior_designer = Agent(
    name="InteriorDesigner",
    model=MODEL_ID,
    description=(
        "Especialista en diseño de INTERIORES: baños, cocinas, dormitorios, "
        "salones. Delega aquí cuando la imagen sea de un espacio interior."
    ),
    instruction=INTERIOR_DESIGNER_INSTRUCTION,
    tools=[
        analyze_and_propose,
        refine_and_generate,
        search_products,
        preload_memory_tool.PreloadMemoryTool(),
    ],
    before_model_callback=_persist_uploaded_images,
    after_agent_callback=_save_memory_after_agent,
)

# ─── Master designer: root agent that orchestrates and ensures consistency ───
root_agent = Agent(
    name="MasterDesigner",
    model=MODEL_ID,
    description="Master designer: orchestrates exterior and interior specialists",
    instruction=MASTER_DESIGNER_INSTRUCTION,
    tools=[search_products],
    sub_agents=[exterior_designer, interior_designer],
    before_model_callback=_persist_uploaded_images,
    after_agent_callback=_save_memory_after_agent,
)

app = App(
    root_agent=root_agent,
    name="app",
)
