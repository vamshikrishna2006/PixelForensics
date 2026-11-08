"""Analyze / history / detail / delete / compare / reports (PDF+JSON)."""
import asyncio
import json
import os
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.config import get_settings
from app.core.database import get_db
from app.core.observability import log_event, log_exception, sanitize_text
from app.forensic.narrative import build_narrative
from app.forensic.pipeline import run_full_analysis, run_comparison
from app.models.models import Analysis, AnalysisResult, Profile, SuspiciousRegion
from app.reports.naming import download_name, report_basename
from app.reports.signing import sign_meta
from app.schemas.schemas import AnalysisOut, CompareOut, ReportOut
from app.security.deps import current_user, admin_user
from app.security.uploads import validate_upload, safe_storage_name, storage_file_path
from app.core.storage import store_image, get_image_bytes, delete_image

router = APIRouter(tags=["analysis"])
settings = get_settings()
analysis_semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)


def _out(a):
    return AnalysisOut(id=a.id, filename=a.filename, status=a.status, verdict=a.verdict,
                       confidence=a.confidence, final_score=a.final_score,
                       created_at=a.created_at.isoformat(), processing_time_s=a.processing_time_s)



@router.post("/api/analyze", response_model=ReportOut)
async def analyze(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                  user: Profile = Depends(current_user)):
    raw = await file.read()
    try:
        mime = validate_upload(raw, file.filename or "upload.jpg",
                               file.content_type or "image/jpeg",
                               settings.allowed_mime_list, settings.max_upload_bytes)
    except ValueError as e:
        log_event(
            "warning",
            "upload",
            "upload validation rejected",
            alert=False,
            module="analysis",
            reason=sanitize_text(e),
            size_bytes=len(raw),
        )
        raise HTTPException(400, str(e))
    # Dimension / decompression bomb protection
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            h, w = img.shape[:2]
            if max(h, w) > settings.MAX_IMAGE_DIMENSION:
                raise ValueError(f"Image dimensions too large (max {settings.MAX_IMAGE_DIMENSION}px on a side)")
            if h * w > settings.MAX_PIXEL_COUNT:
                raise ValueError(f"Image pixel count too high (max {settings.MAX_PIXEL_COUNT})")
    except ValueError:
        raise
    except Exception:
        # If dimension check fails, reject to stay safe
        raise HTTPException(400, "Unable to validate image dimensions")
    # Run analysis under concurrency limit and off event loop
    async with analysis_semaphore:
        try:
            result = await asyncio.to_thread(run_full_analysis, raw, file.filename or "upload.jpg", mime)
        except Exception as e:
            log_exception(
                e,
                "analysis",
                "image analysis pipeline failed",
                module="analysis",
                size_bytes=len(raw),
                mime=mime,
            )
            raise HTTPException(422, "Image analysis could not be completed. Please try again later.")
    narrative = build_narrative(result)
    result["narrative"] = narrative
    rel = safe_storage_name(user.id, os.path.splitext(file.filename or ".jpg")[1])
    try:
        # Store image to configured backend (local / Supabase / hybrid)
        store_image(user.id, "pending", raw, file.filename or "upload.jpg", relative_path=rel)
        # keep rel as safe_storage_name for DB reference
    except Exception as e:
        log_exception(
            e,
            "storage",
            "uploaded image could not be stored",
            module="analysis",
            size_bytes=len(raw),
        )
        raise HTTPException(503, "The service is temporarily unavailable. Please try again.")
    a = Analysis(user_id=user.id, filename=file.filename or "upload.jpg", storage_path=rel,
                 mime=mime, size_bytes=len(raw), status="completed", verdict=result["verdict"],
                 confidence=result["confidence"], final_score=result["final_score"],
                 processing_time_s=result["processing_time_s"], completed_at=datetime.utcnow())
    db.add(a)
    await db.flush()
    db.add(AnalysisResult(analysis_id=a.id, full_json=result))
    for r in result["regions"]:
        db.add(SuspiciousRegion(analysis_id=a.id, x=r["x"], y=r["y"],
                                width=r["width"], height=r["height"], reason=r["reason"]))
    await db.commit()
    await db.refresh(a)
    log_event(
        "info",
        "analysis",
        "image analysis completed",
        alert=False,
        module="analysis",
        verdict=a.verdict,
        processing_time_s=a.processing_time_s,
    )
    return ReportOut(analysis=_out(a), detectors=result["detectors"], breakdown=result["breakdown"],
                     explanation=result["explanation"], regions=result["regions"],
                     artifacts=result["artifacts"], image_info=result["image_info"],
                     narrative=narrative,
                     report_name=report_basename(file.filename, result.get("image_profile"),
                                                 a.created_at))


@router.get("/api/analysis/history", response_model=list[AnalysisOut])
async def history(db: AsyncSession = Depends(get_db), user: Profile = Depends(current_user)):
    rows = (await db.execute(select(Analysis).where(Analysis.user_id == user.id)
                             .order_by(desc(Analysis.created_at)).limit(100))).scalars().all()
    return [_out(a) for a in rows]


@router.get("/api/analysis/{aid}", response_model=ReportOut)
async def detail(aid: str, db: AsyncSession = Depends(get_db), user: Profile = Depends(current_user)):
    from sqlalchemy.orm import selectinload as _sl
    a = (await db.execute(select(Analysis).where(
        Analysis.id == aid, Analysis.user_id == user.id).options(_sl(Analysis.result)))).scalar_one_or_none()
    if not a or not a.result:
        raise HTTPException(404, "Analysis not found.")
    r = a.result.full_json
    narrative = r.get("narrative") or build_narrative(r)
    stored_name = ((next((d for d in r.get("detectors") or []
                          if d.get("method") == "METADATA"), {}) or {})
                   .get("details") or {}).get("filename") or a.filename
    return ReportOut(analysis=_out(a), detectors=r["detectors"], breakdown=r["breakdown"],
                     explanation=r["explanation"], regions=r["regions"],
                     artifacts=r["artifacts"], image_info=r["image_info"],
                     narrative=narrative,
                     report_name=report_basename(stored_name, r.get("image_profile"),
                                                 a.created_at))


@router.delete("/api/analysis/{aid}")
async def remove(aid: str, db: AsyncSession = Depends(get_db), user: Profile = Depends(current_user)):
    a = (await db.execute(select(Analysis).where(
        Analysis.id == aid, Analysis.user_id == user.id))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Analysis not found.")
    try:
        delete_image(a.storage_path)
    except Exception as exc:
        log_event(
            "warning",
            "storage",
            "stored image could not be removed",
            alert=False,
            module="analysis",
            error_type=type(exc).__name__,
        )
    await db.delete(a)
    await db.commit()
    return {"ok": True}


@router.post("/api/compare", response_model=CompareOut)
async def compare(files: list[UploadFile] = File(...), user: Profile = Depends(current_user)):
    if len(files) < 2 or len(files) > 4:
        raise HTTPException(400, "Upload 2-4 images to compare.")
    imgs = []
    for f in files:
        raw = await f.read()
        try:
            validate_upload(raw, f.filename or "img.jpg", f.content_type or "image/jpeg",
                            settings.allowed_mime_list, settings.max_upload_bytes)
        except ValueError as e:
            log_event(
                "warning",
                "upload",
                "comparison upload rejected",
                alert=False,
                module="analysis",
                reason=sanitize_text(e),
                size_bytes=len(raw),
            )
            raise HTTPException(400, f"{f.filename}: {e}")
        imgs.append((f.filename or "img", raw))
    try:
        return run_comparison(imgs)
    except Exception as exc:
        log_exception(exc, "analysis", "image comparison failed", module="analysis")
        raise HTTPException(422, "Image comparison could not be completed. Please try again later.")


@router.get("/api/report/{aid}/json")
async def report_json(aid: str, db: AsyncSession = Depends(get_db), user: Profile = Depends(current_user)):
    a = (await db.execute(select(Analysis).where(
        Analysis.id == aid, Analysis.user_id == user.id).options(selectinload(Analysis.result)))).scalar_one_or_none()
    if not a or not a.result:
        raise HTTPException(404, "Not found.")
    data = dict(a.result.full_json)
    data["narrative"] = data.get("narrative") or build_narrative(data)
    name = download_name(report_basename(a.filename, data.get("image_profile"), a.created_at), "json")
    try:
        content = json.dumps(data)
    except Exception as exc:
        log_exception(exc, "report", "JSON report generation failed", module="reports")
        raise HTTPException(500, "Report generation failed. Please try again later.")
    return Response(content=content, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Access-Control-Expose-Headers": "Content-Disposition"})


@router.get("/api/report/{aid}/pdf")
async def report_pdf(aid: str, db: AsyncSession = Depends(get_db), user: Profile = Depends(current_user)):
    from app.reports.pdf import build_pdf
    a = (await db.execute(select(Analysis).where(
        Analysis.id == aid, Analysis.user_id == user.id).options(selectinload(Analysis.result)))).scalar_one_or_none()
    if not a or not a.result:
        raise HTTPException(404, "Not found.")
    result = a.result.full_json
    name = download_name(report_basename(a.filename, result.get("image_profile"), a.created_at), "pdf")
    image_path_str = None
    temp_path = None
    try:
        img_bytes = get_image_bytes(a.storage_path)
        if img_bytes:
            import tempfile, os
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(img_bytes)
            tmp.flush()
            tmp.close()
            temp_path = tmp.name
            image_path_str = temp_path
        else:
            image_path = storage_file_path(settings.LOCAL_STORAGE_PATH, a.storage_path)
            image_path_str = str(image_path) if image_path and image_path.exists() else None
        async with analysis_semaphore:
            pdf = await asyncio.to_thread(build_pdf, {
                "id": a.id, "filename": a.filename, "verdict": a.verdict,
                "confidence": a.confidence, "final_score": a.final_score,
                "created_at": a.created_at.isoformat(), "processing_time_s": a.processing_time_s,
                "owner": user.username,
                "image_path": image_path_str,
            }, result)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"; '
                                                        f"filename*=UTF-8''{quote(name)}",
                                 "Access-Control-Expose-Headers": "Content-Disposition",
                                 "Cache-Control": "no-store"})
    except Exception as exc:
        log_exception(exc, "report", "PDF report generation failed", module="reports")
        raise HTTPException(500, "Report generation failed. Please try again later.")
    finally:
        # Explicit cleanup of temporary image file
        if temp_path:
            try:
                import os
                os.unlink(temp_path)
            except Exception:
                pass


@router.get("/api/report/{aid}/signature")
async def report_signature(aid: str, db: AsyncSession = Depends(get_db),
                           user: Profile = Depends(current_user)):
    """Signature block for a report, so a downloaded/printed copy can be verified."""
    a = (await db.execute(select(Analysis).where(
        Analysis.id == aid, Analysis.user_id == user.id).options(selectinload(Analysis.result)))).scalar_one_or_none()
    if not a or not a.result:
        raise HTTPException(404, "Not found.")
    return sign_meta({
        "id": a.id, "filename": a.filename, "verdict": a.verdict,
        "final_score": a.final_score, "confidence": a.confidence,
        "created_at": a.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "algorithm_version": settings.FORENSIC_ALGORITHM_VERSION,
    })


@router.get("/api/admin/statistics")
async def stats(db: AsyncSession = Depends(get_db), admin: Profile = Depends(admin_user)):
    users = (await db.execute(select(func.count(Profile.id)))).scalar()
    total = (await db.execute(select(func.count(Analysis.id)))).scalar()
    real = (await db.execute(select(func.count(Analysis.id)).where(Analysis.verdict == "LIKELY_REAL"))).scalar()
    fake = (await db.execute(select(func.count(Analysis.id)).where(Analysis.verdict == "LIKELY_AI_MANIPULATED"))).scalar()
    inc = (await db.execute(select(func.count(Analysis.id)).where(Analysis.verdict == "INCONCLUSIVE"))).scalar()
    avg_t = (await db.execute(select(func.avg(Analysis.processing_time_s)))).scalar() or 0
    return {"total_users": users, "total_analyses": total, "real": real, "fake": fake,
            "inconclusive": inc, "avg_processing_s": round(float(avg_t), 2),
            "algorithm_version": settings.FORENSIC_ALGORITHM_VERSION}


@router.get("/api/admin/users")
async def users(db: AsyncSession = Depends(get_db), admin: Profile = Depends(admin_user)):
    rows = (await db.execute(select(Profile).order_by(desc(Profile.created_at)).limit(200))).scalars().all()
    return [{"id": u.id, "username": u.username, "email": u.email, "role": u.role,
             "status": u.status, "created_at": u.created_at.isoformat()} for u in rows]


@router.get("/api/admin/system-health")
async def health(db: AsyncSession = Depends(get_db), admin: Profile = Depends(admin_user)):
    """Detailed health probe for the admin dashboard.

    Every probe is best-effort: a failing check is reported as ``error`` in the
    payload instead of raising, so the dashboard can paint a red tile rather than
    losing the whole card.
    """
    import shutil
    import time

    storage_dir = os.path.abspath(settings.LOCAL_STORAGE_PATH)
    probe_dir = storage_dir if os.path.exists(storage_dir) else "."
    try:
        disk = shutil.disk_usage(probe_dir)
        disk_free_gb = round(disk.free / 1e9, 2)
        disk_total_gb = round(disk.total / 1e9, 2)
        disk_used_pct = round(disk.used / disk.total * 100, 1)
    except OSError:
        disk_free_gb = disk_total_gb = disk_used_pct = None

    storage_files = 0
    storage_bytes = 0
    try:
        for root, _dirs, names in os.walk(storage_dir):
            for name in names:
                try:
                    storage_bytes += os.path.getsize(os.path.join(root, name))
                    storage_files += 1
                except OSError:
                    pass
    except OSError:
        pass

    db_status, db_detail, db_latency_ms = "healthy", "connected", None
    total_analyses, avg_processing_s = 0, 0.0
    try:
        t0 = time.perf_counter()
        await db.execute(text("SELECT 1"))
        db_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        total_analyses = (await db.execute(select(func.count(Analysis.id)))).scalar() or 0
        avg_t = (await db.execute(select(func.avg(Analysis.processing_time_s)))).scalar() or 0
        avg_processing_s = round(float(avg_t), 2)
    except Exception as exc:  # noqa: BLE001 — surfaced to the dashboard, never raised
        await db.rollback()
        db_status = "error"
        db_detail = f"{type(exc).__name__}: {exc}"

    return {"api": "healthy",
            "database": db_status,
            "database_detail": db_detail,
            "database_latency_ms": db_latency_ms,
            "storage_path": storage_dir,
            "storage_exists": os.path.isdir(storage_dir),
            "storage_writable": os.access(probe_dir, os.W_OK),
            "storage_files": storage_files,
            "storage_size_mb": round(storage_bytes / 1e6, 2),
            "disk_free_gb": disk_free_gb,
            "disk_total_gb": disk_total_gb,
            "disk_used_pct": disk_used_pct,
            # kept for backwards compatibility with older dashboard builds
            "storage_free_gb": disk_free_gb,
            "total_analyses": total_analyses,
            "avg_processing_s": avg_processing_s,
            "algorithm_version": settings.FORENSIC_ALGORITHM_VERSION,
            "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"}



