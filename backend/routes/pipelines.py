"""The pipelines in backend/pipelines/, for the app's map of a session's steps (core/pipeline.py)."""
from fastapi import APIRouter, Depends, HTTPException

from auth import get_optional_user
from core.pipeline import PipelineError, delete, load, names, save
from core.workspace import HOSTED

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


def _local_only():
    # A pipeline is a file on the server: on a hosted server, one user's edit would change every user's pipelines
    if HOSTED:
        raise HTTPException(status_code=403, detail="Pipelines can only be edited on a local Loop Runner.")


@router.put("/{name}")
def save_pipeline(name: str, body: dict, _: dict | None = Depends(get_optional_user)):
    """Check the pipeline and save it as backend/pipelines/<name>.yaml; the reason comes back if it can't run."""
    _local_only()
    try:
        return save(name, body).to_json()
    except PipelineError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{name}")
def delete_pipeline(name: str, _: dict | None = Depends(get_optional_user)):
    _local_only()
    try:
        delete(name)
    except PipelineError as e:
        raise HTTPException(status_code=404 if "no pipeline" in str(e) else 422, detail=str(e))
    return {"deleted": name}
