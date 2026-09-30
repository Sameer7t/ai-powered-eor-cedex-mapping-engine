import os
import json
import uuid
import tempfile
from typing import Optional

from custom_maping_by_human import (
    learn_from_human,
    read_mapping_file,
    write_mapping_file,
    get_mapping_files,
)
from pdf_extractor import pdf_extractor, validate_cost_hour, classify_jobs, process_estimate
from excel_extractor import excel_extractor
from process_normal_jobs import process_normal_jobs
from process_special_jobs import process_special_jobs
from categorize import categorize_list
from cedex_mapping import cedex_mapping
from arranging_by_job_id import arranging_by_id
from dry_processing import dry_processing
from build_invoice import build_invoice
from excel_report import generate_excel_report
from translation_cache import translate_job_description
from ai_client import get_genai_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_DIR = os.path.join(BASE_DIR, "mappings")
CONTAINER_TYPE_FILE = os.path.join(MAPPINGS_DIR, "human_container_type_mapping.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "data", "output")

TANK_TYPES = {
    "IMO 1", "IMO 2", "IMO 3", "22K1", "20TK", "22T1", "20T1", "TANK"
}

DRY_TYPES = {
    "22G1", "42G1", "45G1", "20GP", "20DV", "40GP", "40HC", "45HC", "L5G1", "DRY"
}


def detect_container_route(container_type: Optional[str]) -> str:
    """Classifies container into 'tank' or 'dry' route, consulting memory files if needed."""
    if not container_type:
        return "tank"

    clean_type = container_type.strip().upper()

    if clean_type in {t.upper() for t in TANK_TYPES}:
        return "tank"
    if clean_type in {t.upper() for t in DRY_TYPES}:
        return "dry"

    learned_types = read_mapping_file(CONTAINER_TYPE_FILE)
    if clean_type in learned_types:
        return learned_types[clean_type]

    # Heuristic fallback
    if "TANK" in clean_type or "TK" in clean_type or "IMO" in clean_type:
        return "tank"
    if "GP" in clean_type or "HC" in clean_type or "DV" in clean_type or "G1" in clean_type:
        return "dry"

    return "tank"


def compute_confidence(jobs: list[dict]) -> tuple[float, str]:
    """Calculates confidence score based on completeness of 4-tuple CEDEX code."""
    if not jobs:
        return 1.0, "high"

    score = 1.0
    for job in jobs:
        if not job.get("component"):
            score -= 0.15
        if not job.get("repair"):
            score -= 0.15
        if not job.get("location"):
            score -= 0.10
        if not job.get("damage"):
            score -= 0.10
        if job.get("status") in ["unmapped", "skipped"]:
            score -= 0.20

    score = max(0.0, min(1.0, round(score, 2)))
    level = "high" if score >= 0.75 else ("medium" if score >= 0.5 else "low")
    return score, level


def extract_document_text(file_path: str) -> str:
    """Extracts text from PDF or Excel workbook."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return pdf_extractor(file_path)
    elif ext in [".xlsx", ".xls"]:
        return excel_extractor(file_path)
    else:
        raise ValueError(f"Unsupported document format: {ext}")


def process_single_estimate_data(estimate_data: dict, api_key: Optional[str] = None) -> dict:
    """
    Executes the CEDEX mapping pipeline for a single estimate dictionary.
    Supports both Tank and Dry container branches.
    """
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key

    # Validate schema integrity
    try:
        validate_cost_hour(estimate_data)
    except Exception as e:
        print(f"[Engine] Notice during validation: {e}")

    container_type = estimate_data.get("container_type", "")
    route = detect_container_route(container_type)

    job_descriptions = estimate_data.get("job_description", [])

    if route == "dry":
        man_hour_rate = estimate_data.get("man_hour_rate") or 0.0
        dry_result = dry_processing(job_descriptions, man_hour_rate)
        sorted_jobs = dry_result.get("success_jobs", []) + dry_result.get("failed_jobs", [])
    else:
        # Tank Container Pipeline
        if not container_type:
            estimate_data["container_type"] = "22K1"

        try:
            classification_data = classify_jobs(estimate_data)
            jobs_split = categorize_list(job_descriptions, classification_data)
            n_jobs = process_normal_jobs(jobs_split["normal_jobs"])
            s_jobs = process_special_jobs(jobs_split["special_jobs"])
            mapped_jobs = cedex_mapping(n_jobs, route="tank")
            sorted_jobs = arranging_by_id(mapped_jobs, s_jobs)
        except Exception as e:
            print(f"[Engine] Tank classification fallback due to: {e}")
            # Fallback to direct mapping without LLM classification if API quota or error
            n_jobs = []
            for idx, item in enumerate(job_descriptions, start=1):
                n_jobs.append({
                    "job_id": idx,
                    "location": "",
                    "component": "",
                    "repair": "",
                    "damage": "",
                    "manhour": item.get("manhour", 0.0),
                    "labour_cost": (item.get("manhour", 0.0) or 0) * (estimate_data.get("man_hour_rate", 0) or 0),
                    "material_cost_aed": item.get("material_cost_aed", 0.0),
                    "job_description": item.get("job_description", ""),
                    "status": "unmapped",
                })
            sorted_jobs = cedex_mapping(n_jobs, route="tank")

    # Add translated description and human review recommendation flags
    review_needed_count = 0
    for job in sorted_jobs:
        status = job.get("status", "unmapped")
        if status in ["unmapped", "skipped"] or not job.get("cedex_code"):
            job["needs_human_review"] = True
            review_needed_count += 1
        else:
            job["needs_human_review"] = False

        # Pre-cache or resolve human readable description for UI review
        raw_desc = job.get("job_description", "")
        job["display_description"] = translate_job_description(raw_desc) if raw_desc else ""

    conf_score, conf_level = compute_confidence(sorted_jobs)

    # Build final standardized invoice record
    invoice = build_invoice(estimate_data, sorted_jobs)
    invoice["route"] = route
    invoice["confidence_score"] = conf_score
    invoice["confidence_level"] = conf_level
    invoice["review_needed_count"] = review_needed_count

    return invoice


def process_uploaded_document(file_path: str, filename: str = "", api_key: Optional[str] = None) -> dict:
    """
    Ingests an uploaded document, parses all container estimates, runs
    classification and CEDEX code mapping, and prepares report downloads.
    """
    text = extract_document_text(file_path)
    if not text or not text.strip():
        raise ValueError(f"Could not extract any readable text from {filename or file_path}")

    # Use Gemini to extract structured estimates from document text
    estimates = process_estimate(text)
    if not estimates:
        raise ValueError("No valid repair estimates identified in the document.")

    success_invoices = []
    failed_invoices = []
    all_invoices = []

    for est in estimates:
        invoice = process_single_estimate_data(est, api_key=api_key)
        all_invoices.append(invoice)

        has_failures = any(
            j.get("status") in ["unmapped", "skipped"] or j.get("needs_human_review")
            for j in invoice.get("jobs", [])
        )

        if has_failures:
            failed_invoices.append(invoice)
        else:
            success_invoices.append(invoice)

    # Generate master Excel workbooks
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session_id = uuid.uuid4().hex[:8]
    success_path = os.path.join(OUTPUT_DIR, f"SUCCESS_{session_id}.xlsx")
    failed_path = os.path.join(OUTPUT_DIR, f"FAILED_DLQ_{session_id}.xlsx")

    if success_invoices:
        generate_excel_report(success_invoices, success_path)
    if failed_invoices:
        generate_excel_report(failed_invoices, failed_path)

    return {
        "success": True,
        "filename": filename or os.path.basename(file_path),
        "total_estimates": len(all_invoices),
        "success_count": len(success_invoices),
        "review_count": len(failed_invoices),
        "invoices": all_invoices,
        "success_report_file": os.path.basename(success_path) if success_invoices else None,
        "failed_report_file": os.path.basename(failed_path) if failed_invoices else None,
    }


def execute_human_mapping_review(
    job_id: int,
    route: str,
    human_code_input: str,
    raw_job: dict,
) -> dict:
    """
    Processes human intervention for low-confidence or unmapped jobs,
    updating the route-specific memory JSON if valid.
    Format expected: 'LOCATION COMPONENT REPAIR DAMAGE' (e.g. 'AFXX YXT AX DY')
    """
    job_copy = dict(raw_job)
    job_copy["job_id"] = job_id
    success = learn_from_human(job_copy, human_code_input, route=route)
    if not success:
        return {
            "success": False,
            "message": "Invalid code sequence or combination not recognized in CEDEX Master reference.",
        }

    return {
        "success": True,
        "message": f"Successfully mapped and persisted learning for Job #{job_id}.",
        "updated_job": job_copy,
    }


# Synthetic Demo Estimates for 1-click cloud testing
DEMO_TANK_ESTIMATE = {
    "container_id": "TCNU9891165",
    "container_type": "22K1",
    "depot_name": "Seaport Emirates Depot Dubai",
    "currency": "AED",
    "man_hour_rate": 65.0,
    "job_description": [
        {
            "job_description": "Top front corner manlid gasket leaking renewed PTFE seal",
            "manhour": 1.5,
            "material_cost_aed": 180.0,
        },
        {
            "job_description": "Bottom discharge valve handle bent straightened",
            "manhour": 0.8,
            "material_cost_aed": 45.0,
        },
        {
            "job_description": "Pressure gauge glass cracked replaced new gauge",
            "manhour": 1.0,
            "material_cost_aed": 220.0,
        },
        {
            "job_description": "Tank shell standard chemical package cleaning",
            "manhour": 3.0,
            "material_cost_aed": 350.0,
        },
    ],
}

DEMO_DRY_ESTIMATE = {
    "container_id": "TSLU0527650",
    "container_type": "42G1",
    "depot_name": "Intermodal Logistics Hub",
    "currency": "USD",
    "man_hour_rate": 55.0,
    "job_description": [
        {
            "job_description": "L/SIDE PANEL DENTED TO REPLACE 2 X 3 FT",
            "manhour": 2.5,
            "material_cost_aed": 150.0,
        },
        {
            "job_description": "REAR RIGHT CORNER POST SCRATCHED REPAINT",
            "manhour": 1.2,
            "material_cost_aed": 75.0,
        },
        {
            "job_description": "DOOR GASKET LOOSE SECURE AND SEAL",
            "manhour": 0.8,
            "material_cost_aed": 30.0,
        },
    ],
}


def get_demo_samples() -> dict:
    """Returns curated synthetic sample estimates for interactive browser demonstrations."""
    return {
        "tank": DEMO_TANK_ESTIMATE,
        "dry": DEMO_DRY_ESTIMATE,
    }
