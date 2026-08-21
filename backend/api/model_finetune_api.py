from __future__ import annotations

from fastapi import APIRouter

from backend.dependencies import get_model_finetune_service


router = APIRouter(prefix="/model-finetune", tags=["model-finetune"])


@router.get("/overview")
async def model_finetune_overview() -> dict[str, object]:
    return get_model_finetune_service().overview()


@router.get("/capabilities")
async def model_finetune_capabilities() -> dict[str, object]:
    return get_model_finetune_service().capability_snapshot()


@router.get("/templates")
async def model_finetune_templates() -> list[dict[str, object]]:
    return get_model_finetune_service().training_templates()


@router.get("/datasets")
async def model_finetune_datasets() -> list[dict[str, object]]:
    return get_model_finetune_service().dataset_exports()


@router.post("/datasets/export")
async def export_model_finetune_datasets() -> dict[str, object]:
    return get_model_finetune_service().export_seed_datasets()


@router.get("/eval-gates")
async def model_finetune_eval_gates() -> dict[str, object]:
    return get_model_finetune_service().eval_gates()


@router.post("/eval-gates/run")
async def run_model_finetune_eval_gates() -> dict[str, object]:
    return get_model_finetune_service().run_eval_gates()


@router.get("/adapters")
async def model_finetune_adapters() -> dict[str, object]:
    return get_model_finetune_service().adapter_registry()
