"""HTTP routes for the persona library (see persona_library.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import persona_library as lib
from .config import get_settings
from .connectors.llm import get_llm_client
from .reasoning_modes import parse_provider

router = APIRouter(prefix="/api/persona-library", tags=["persona-library"])


def _llm(provider: str | None):
    settings = get_settings()
    # Persona writing needs a strong model: default to Claude when it is configured.
    default = "azure_anthropic" if settings.has_azure_anthropic else settings.llm_provider
    resolved = parse_provider(provider, default=default)
    try:
        return get_llm_client(settings, resolved), resolved
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("")
def library(full: bool = False) -> dict:
    """Every district and every persona in it. `full=1` includes the long text
    (what the static site snapshot uses); otherwise summaries only."""
    records = lib.all_personas()
    return {
        "districts": lib.districts(),
        "personas": records if full else [lib.summary(r) for r in records],
    }


@router.get("/{persona_id}")
def persona(persona_id: str) -> dict:
    record = lib.get_persona(persona_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no such persona")
    return record


class GenerateRequest(BaseModel):
    districtId: str
    gender: str
    traits: dict[str, str] = Field(default_factory=dict)  # name, age, occupation, community, taluk, notes
    provider: str | None = None


@router.post("/generate")
async def generate(req: GenerateRequest) -> dict:
    """A draft persona for a district -- not saved until the user saves it."""
    llm, provider = _llm(req.provider)
    try:
        return await lib.generate(llm, district_id=req.districtId, gender=req.gender, traits=req.traits, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"persona generation failed: {exc}") from exc


class RebuildCardRequest(BaseModel):
    persona: dict
    provider: str | None = None


@router.post("/card")
async def rebuild_card(req: RebuildCardRequest) -> dict:
    """Re-distil the display card from (edited) persona text."""
    llm, _ = _llm(req.provider)
    try:
        record = lib._clean_record(req.persona)
        return await lib.build_card(llm, record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"card rebuild failed: {exc}") from exc


@router.post("/custom")
def create_custom(persona: dict) -> dict:
    try:
        return lib.save_custom(persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/custom/{persona_id}")
def update_custom(persona_id: str, persona: dict) -> dict:
    try:
        return lib.save_custom(persona, persona_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/custom/{persona_id}")
def delete_custom(persona_id: str) -> dict:
    if not lib.delete_custom(persona_id):
        raise HTTPException(status_code=404, detail="no such custom persona")
    return {"deleted": persona_id}


class AskRequest(BaseModel):
    personaId: str | None = None
    persona: dict | None = None  # an unsaved draft can be asked too
    question: str = Field(min_length=3, max_length=500)
    useEvidence: bool = True
    topic: str = "dropout"  # which study's data is the shared evidence: "dropout" | "stunting"
    provider: str | None = None


@router.post("/ask")
async def ask(req: AskRequest) -> dict:
    """The same question answered without and with the persona, on identical evidence."""
    if req.persona is not None:
        try:
            record = {**lib._clean_record(req.persona), "id": req.persona.get("id") or "draft"}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        record = lib.get_persona(req.personaId or "")
        if record is None:
            raise HTTPException(status_code=404, detail="no such persona")
    llm, provider = _llm(req.provider)
    try:
        topic = req.topic if req.topic in lib.TOPICS_EVIDENCE else "dropout"
        result = await lib.ask(llm, record, req.question.strip(), use_evidence=req.useEvidence, topic=topic)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"answer failed: {exc}") from exc
    result["provider"] = provider
    return result
