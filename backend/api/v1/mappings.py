"""Field mapping CRUD and transformation endpoints for a pipeline."""
import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...db.models import CompiledTransformation, FieldMapping, Pipeline
from ...transformation.compiler import MappingCompiler
from ...transformation.sandbox import TransformationEngine
from ...transformation.validator import TransformValidator

router = APIRouter()


class MappingUpsert(BaseModel):
    source_field: str | None = None
    target_field: str | None = None
    transform_name: str = "passthrough"
    transform_args: dict | None = None
    expression: str | None = None
    is_required: bool = False


class TransformationUpdate(BaseModel):
    forward_code: str | None = None
    reverse_code: str | None = None


class TestRecord(BaseModel):
    record: dict


@router.get("/{pipeline_id}/mappings")
async def list_mappings(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FieldMapping).where(FieldMapping.pipeline_id == pipeline_id)
    )
    rows = result.scalars().all()
    return {"items": [_ser_mapping(m) for m in rows]}


@router.post("/{pipeline_id}/mappings", status_code=201)
async def upsert_mapping(pipeline_id: str, body: MappingUpsert, db: AsyncSession = Depends(get_db)):
    await _pipeline_or_404(pipeline_id, db)
    fm = FieldMapping(
        id=str(uuid.uuid4()),
        pipeline_id=pipeline_id,
        source_field=body.source_field,
        target_field=body.target_field,
        transform_name=body.transform_name,
        transform_args=body.transform_args,
        expression=body.expression,
        is_required=body.is_required,
    )
    db.add(fm)
    await db.commit()
    await db.refresh(fm)
    return _ser_mapping(fm)


@router.delete("/{pipeline_id}/mappings/{mapping_id}", status_code=204)
async def delete_mapping(pipeline_id: str, mapping_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FieldMapping).where(
            FieldMapping.id == mapping_id,
            FieldMapping.pipeline_id == pipeline_id,
        )
    )
    fm = result.scalar_one_or_none()
    if not fm:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.delete(fm)
    await db.commit()


@router.get("/{pipeline_id}/transformation")
async def get_transformation(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CompiledTransformation).where(CompiledTransformation.pipeline_id == pipeline_id)
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="No transformation compiled yet")
    return _ser_transformation(ct)


@router.put("/{pipeline_id}/transformation")
async def update_transformation(
    pipeline_id: str,
    body: TransformationUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompiledTransformation).where(CompiledTransformation.pipeline_id == pipeline_id)
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="No transformation found")

    if body.forward_code is not None:
        ct.forward_code = body.forward_code
    if body.reverse_code is not None:
        ct.reverse_code = body.reverse_code

    validator = TransformValidator()
    validation = validator.validate(ct.forward_code, ct.reverse_code)
    ct.validation_passed = validation["passed"]
    ct.validation_report = validation
    ct.code_hash = hashlib.sha256(
        json.dumps({"f": ct.forward_code, "r": ct.reverse_code}).encode()
    ).hexdigest()
    ct.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ct)
    return _ser_transformation(ct)


@router.post("/{pipeline_id}/transformation/test")
async def test_transformation(
    pipeline_id: str,
    body: TestRecord,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompiledTransformation).where(CompiledTransformation.pipeline_id == pipeline_id)
    )
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="No transformation found")

    try:
        engine = TransformationEngine(ct.forward_code, ct.reverse_code)
        output = engine.transform_forward(body.record, {"pipeline_id": pipeline_id})
        return {"output": output, "error": None}
    except Exception as exc:
        return {"output": None, "error": str(exc)}


@router.post("/{pipeline_id}/transformation/regenerate", status_code=202)
async def regenerate_transformation(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    """Recompile transformation from current field mappings."""
    result = await db.execute(
        select(FieldMapping).where(FieldMapping.pipeline_id == pipeline_id)
    )
    mappings = result.scalars().all()
    if not mappings:
        raise HTTPException(status_code=400, detail="No field mappings defined for this pipeline")

    compiler = MappingCompiler()
    code = compiler.compile([_ser_mapping(m) for m in mappings])

    validator = TransformValidator()
    validation = validator.validate(code["forward"], code["reverse"])
    code_hash = hashlib.sha256(json.dumps(code, sort_keys=True).encode()).hexdigest()

    existing = await db.execute(
        select(CompiledTransformation).where(CompiledTransformation.pipeline_id == pipeline_id)
    )
    ct = existing.scalar_one_or_none()

    if ct:
        ct.forward_code = code["forward"]
        ct.reverse_code = code["reverse"]
        ct.code_hash = code_hash
        ct.generated_by = "compiler"
        ct.validation_passed = validation["passed"]
        ct.validation_report = validation
        ct.version += 1
        ct.updated_at = datetime.utcnow()
    else:
        ct = CompiledTransformation(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            forward_code=code["forward"],
            reverse_code=code["reverse"],
            code_hash=code_hash,
            generated_by="compiler",
            validation_passed=validation["passed"],
            validation_report=validation,
        )
        db.add(ct)

    await db.commit()
    return {"status": "regenerated", "validation_passed": validation["passed"]}


async def _pipeline_or_404(pipeline_id: str, db: AsyncSession) -> Pipeline:
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return p


def _ser_mapping(m: FieldMapping) -> dict:
    return {
        "id": m.id,
        "pipeline_id": m.pipeline_id,
        "source_field": m.source_field,
        "target_field": m.target_field,
        "transform_name": m.transform_name,
        "transform_args": m.transform_args,
        "expression": m.expression,
        "is_required": m.is_required,
        "version": m.version,
    }


def _ser_transformation(ct: CompiledTransformation) -> dict:
    return {
        "id": ct.id,
        "pipeline_id": ct.pipeline_id,
        "forward_code": ct.forward_code,
        "reverse_code": ct.reverse_code,
        "code_hash": ct.code_hash,
        "generated_by": ct.generated_by,
        "llm_model": ct.llm_model,
        "validation_passed": ct.validation_passed,
        "validation_report": ct.validation_report,
        "version": ct.version,
        "updated_at": ct.updated_at.isoformat() if ct.updated_at else None,
    }
