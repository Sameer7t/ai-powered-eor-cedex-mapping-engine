import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure src is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from data_loader import get_cedex_sheet, get_damage_codes, get_iso_equipment_group
from engine_service import (
    process_uploaded_document,
    process_single_estimate_data,
    execute_human_mapping_review,
    get_demo_samples,
    create_report_workbooks,
    OUTPUT_DIR,
)
from excel_report import generate_excel_report

app = FastAPI(
    title="AI-Powered EOR Processing & CEDEX Mapping Engine",
    description="Container repair estimate parsing, ISO/CEDEX standard mapping, and LangGraph Human-in-the-Loop validation.",
    version="1.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mount
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>AI-Powered EOR Processing & CEDEX Mapping Engine</h1><p>API is running.</p>")


@app.get("/api/health")
async def health_check():
    gemini_key = os.environ.get("GEMINI_API_KEY")
    return {
        "status": "healthy",
        "service": "ai-powered-eor-cedex-mapping-engine",
        "version": "1.0.0",
        "gemini_configured": bool(gemini_key and len(gemini_key.strip()) > 5),
    }


@app.get("/api/reference-mappings")
async def get_reference_stats():
    df_tn = get_cedex_sheet("TN")
    df_gp = get_cedex_sheet("GP")
    df_dmg = get_damage_codes()
    df_iso = get_iso_equipment_group()

    return {
        "tank_codes_count": len(df_tn),
        "dry_codes_count": len(df_gp),
        "damage_codes_count": len(df_dmg),
        "iso_codes_count": len(df_iso),
    }


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
):
    filename = file.filename or "uploaded_estimate"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in [".pdf", ".xlsx", ".xls"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{ext}'. Please upload .pdf or .xlsx/.xls files.",
        )

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = temp_file.name

    try:
        result = process_uploaded_document(
            file_path=temp_path,
            filename=filename,
            api_key=x_gemini_key,
        )
        return result
    except Exception as e:
        print(f"[API] Error processing {filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


class DemoRequest(BaseModel):
    sample_type: str = "tank"


@app.post("/api/process-demo")
async def process_demo_sample(
    payload: DemoRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
):
    demos = get_demo_samples()
    sample_type = payload.sample_type.lower()

    if sample_type not in demos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown demo type: '{sample_type}'. Choose 'tank' or 'dry'.",
        )

    estimate_data = demos[sample_type]

    try:
        invoice = process_single_estimate_data(estimate_data, api_key=x_gemini_key)
        reports = create_report_workbooks([invoice], prefix=f"DEMO_{sample_type.upper()}")

        return {
            "success": True,
            "filename": f"synthetic_{sample_type}_demo.xlsx",
            "total_estimates": 1,
            "success_count": reports["mapped_jobs_count"],
            "review_count": reports["unmapped_jobs_count"],
            "invoices": [invoice],
            "success_report_file": reports["success_report_file"],
            "failed_report_file": reports["failed_report_file"],
            "all_mapped": reports["all_mapped"],
        }
    except Exception as e:
        print(f"[API] Error running demo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing demo: {str(e)}",
        )


class GenerateReportsRequest(BaseModel):
    invoices: list[dict]


@app.post("/api/generate-reports")
async def generate_dynamic_reports(payload: GenerateReportsRequest):
    """Dynamically generates and updates Excel reports whenever jobs are updated or reviewed in the UI."""
    reports = create_report_workbooks(payload.invoices, prefix="SYNC")
    return {
        "success": True,
        **reports,
    }


class HumanReviewRequest(BaseModel):
    job_id: int
    route: str
    human_code_input: str
    raw_job: dict


@app.post("/api/review-job")
async def review_job_mapping(payload: HumanReviewRequest):
    result = execute_human_mapping_review(
        job_id=payload.job_id,
        route=payload.route,
        human_code_input=payload.human_code_input,
        raw_job=payload.raw_job,
    )
    if not result.get("success"):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=result)
    return result


@app.get("/api/download-report/{report_name}")
async def download_report(report_name: str):
    # Sanitize filename
    safe_name = os.path.basename(report_name)
    file_path = os.path.join(OUTPUT_DIR, safe_name)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report file '{safe_name}' not found.",
        )

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_name,
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting CEDEX Mapping Engine Web Server on http://0.0.0.0:{port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
