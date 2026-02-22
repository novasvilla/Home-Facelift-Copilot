"""Hierarchical memory store for Home Facelift Copilot.

Provides persistent project-level and section-level style memory.
Uses Google Cloud Firestore for cloud persistence, with a local JSON fallback.

Memory hierarchy:
  projects/{project_id}
    - style: "moderno elegante"
    - style_summary: "Fachada gris perla RAL 7035, piedra antracita RAL 7016..."
    - sections/{section_id}
      - type: "exterior" | "baño" | "cocina" | ...
      - style_summary: "Baño: azulejos blancos, suelo porcelánico gris..."
      - last_cds: "..." (last CDS for this section)

When a section is updated, its parent project style_summary is also refreshed.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Local fallback path
_LOCAL_MEMORY_DIR = Path(os.path.dirname(__file__)).parent / ".adk" / "memory"

# Firestore client (lazy init)
_firestore_client = None
_firestore_available = False


def _get_firestore():
    """Try to get a Firestore client. Returns None if not available."""
    global _firestore_client, _firestore_available
    if _firestore_client is not None:
        return _firestore_client
    try:
        from google.cloud import firestore

        project = os.environ.get("GCP_PROJECT_ID", "capella-vertex-rag")
        db_name = os.environ.get("FIRESTORE_DB", "facelift-memory")
        _firestore_client = firestore.Client(project=project, database=db_name)
        _firestore_available = True
        logger.info("Firestore connected: project=%s db=%s", project, db_name)
        return _firestore_client
    except Exception as e:
        logger.warning("Firestore not available, using local fallback: %s", e)
        _firestore_available = False
        return None


def _local_path(project_id: str, section_id: str | None = None) -> Path:
    """Get path for local JSON memory file."""
    _LOCAL_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if section_id:
        return _LOCAL_MEMORY_DIR / f"{project_id}__{section_id}.json"
    return _LOCAL_MEMORY_DIR / f"{project_id}.json"


def _read_local(path: Path) -> dict:
    """Read a local JSON file, return empty dict if not found."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read local memory %s: %s", path, e)
    return {}


def _write_local(path: Path, data: dict):
    """Write data to local JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("Failed to write local memory %s: %s", path, e)


# ─── Public API ───────────────────────────────────────────────────────────────


def get_project_memory(project_id: str) -> dict:
    """Get project-level memory (style, summary, sections overview)."""
    db = _get_firestore()
    if db:
        try:
            doc = db.collection("projects").document(project_id).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.warning("Firestore read failed for project %s: %s", project_id, e)
    # Local fallback
    return _read_local(_local_path(project_id))


def save_project_memory(project_id: str, data: dict):
    """Save project-level memory."""
    db = _get_firestore()
    if db:
        try:
            db.collection("projects").document(project_id).set(data, merge=True)
        except Exception as e:
            logger.warning("Firestore write failed for project %s: %s", project_id, e)
    # Always save local too (backup)
    existing = _read_local(_local_path(project_id))
    existing.update(data)
    _write_local(_local_path(project_id), existing)


def get_section_memory(project_id: str, section_id: str) -> dict:
    """Get section-level memory (style refinements, last CDS)."""
    db = _get_firestore()
    if db:
        try:
            doc = (
                db.collection("projects")
                .document(project_id)
                .collection("sections")
                .document(section_id)
                .get()
            )
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.warning(
                "Firestore read failed for section %s/%s: %s",
                project_id,
                section_id,
                e,
            )
    return _read_local(_local_path(project_id, section_id))


def save_section_memory(project_id: str, section_id: str, data: dict):
    """Save section-level memory and update parent project summary."""
    db = _get_firestore()
    if db:
        try:
            (
                db.collection("projects")
                .document(project_id)
                .collection("sections")
                .document(section_id)
                .set(data, merge=True)
            )
        except Exception as e:
            logger.warning(
                "Firestore write failed for section %s/%s: %s",
                project_id,
                section_id,
                e,
            )
    # Local backup
    existing = _read_local(_local_path(project_id, section_id))
    existing.update(data)
    _write_local(_local_path(project_id, section_id), existing)

    # Propagate: update parent project's sections_overview
    _update_project_sections_overview(project_id)


def _update_project_sections_overview(project_id: str):
    """Rebuild the project's sections_overview from all section memories."""
    sections_overview = {}

    # Try Firestore first
    db = _get_firestore()
    if db:
        try:
            sections = (
                db.collection("projects")
                .document(project_id)
                .collection("sections")
                .stream()
            )
            for doc in sections:
                sec_data = doc.to_dict()
                sections_overview[doc.id] = {
                    "type": sec_data.get("type", "otro"),
                    "style_summary": sec_data.get("style_summary", ""),
                }
        except Exception as e:
            logger.warning("Firestore sections list failed: %s", e)

    # Also check local files
    if not sections_overview:
        for f in _LOCAL_MEMORY_DIR.glob(f"{project_id}__*.json"):
            section_id = f.stem.split("__", 1)[1] if "__" in f.stem else f.stem
            sec_data = _read_local(f)
            sections_overview[section_id] = {
                "type": sec_data.get("type", "otro"),
                "style_summary": sec_data.get("style_summary", ""),
            }

    # Save to project
    save_project_memory(project_id, {"sections_overview": sections_overview})


def get_full_context(project_id: str, section_id: str) -> str:
    """Get a text summary of project + section memory for injecting into prompts."""
    proj = get_project_memory(project_id)
    sec = get_section_memory(project_id, section_id)

    lines = []
    if proj.get("style"):
        lines.append(f"Estilo del proyecto: {proj['style']}")
    if proj.get("style_summary"):
        lines.append(f"Resumen global: {proj['style_summary']}")

    # Other sections context
    overview = proj.get("sections_overview", {})
    for sid, sdata in overview.items():
        if sid != section_id and sdata.get("style_summary"):
            lines.append(
                f"Sección {sid} ({sdata.get('type', '?')}): {sdata['style_summary']}"
            )

    if sec.get("style_summary"):
        lines.append(f"Esta sección ({section_id}): {sec['style_summary']}")
    if sec.get("last_cds"):
        lines.append(f"Último CDS de esta sección: {sec['last_cds'][:500]}")

    return "\n".join(lines) if lines else ""
