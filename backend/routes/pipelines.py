"""The pipelines in backend/pipelines/, for the app's map of a session's steps (core/pipeline.py)."""
from fastapi import APIRouter, Depends, HTTPException

from auth import get_optional_user
from core.pipeline import PipelineError, load, names

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# Login like every other route on a hosted server; anonymous in local mode (ALLOW_ANONYMOUS)
@router.get("")
def list_pipelines(_: dict | None = Depends(get_optional_user)):
    """Every pipeline that loads; one that doesn't is listed with the reason, so a broken file is visible."""
    out = []
    for name in names():
        try:
            out.append(load(name).to_json())
        except PipelineError as e:
            out.append({"name": name, "error": str(e)})
    return out


@router.get("/{name}")
def get_pipeline(name: str, _: dict | None = Depends(get_optional_user)):
    if name not in names():
        raise HTTPException(status_code=404, detail=f"No pipeline {name!r}")
    try:
        return load(name).to_json()
    except PipelineError as e:
        raise HTTPException(status_code=422, detail=str(e))
