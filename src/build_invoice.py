import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ISO_MASTER_FILE = os.path.join(BASE_DIR, "..", "data", "ifgEquipmentISOGroup.xlsx")

try:
    df_iso = pd.read_excel(ISO_MASTER_FILE, engine='openpyxl')
    active_codes = df_iso[df_iso['Active'] == True]['Current ISO Code'].dropna()
    VALID_ISO_CODES = set(active_codes.astype(str).str.strip().str.upper())
except Exception as e:
    print(f"Warning: Could not load ISO Master file: {e}")
    VALID_ISO_CODES = set()

ISO_6346_MAPPING = {
    "20OT": "22U1",
    "20DV": "22G1",
    "20GP": "22G1",
    "20DV/OT": "22G1",
    "40DV": "42G1",
    "40HC": "45G1",
    "45HC": "L5G1",
    "IMO 1": "22T1",
    "IMO 2": "22T1",
    "IMO 3": "22T1",
}

def build_invoice(data: dict, sorted_jobs: list) -> dict:

    raw_type = str(data.get("container_type", "")).strip().upper()
    mapped_type = ISO_6346_MAPPING.get(raw_type, raw_type)

    if mapped_type in VALID_ISO_CODES:
        final_iso_type = mapped_type
    elif raw_type in VALID_ISO_CODES:
        final_iso_type = raw_type
    else:
        final_iso_type = f"UNVERIFIED: {raw_type}"

    # --- THE COST RECOVERY INTERCEPT ---
    # The LangGraph nodes (like process_normal_jobs) are accidentally dropping labour_cost
    # when rebuilding the dictionary. We recover the pristine costs directly from
    # the original AI extraction using the job description as the mapping key.

    original_jobs = data.get("job_description", [])
    pristine_costs = {}

    for og_job in original_jobs:
        desc = str(og_job.get("job_description", "")).strip()
        pristine_costs[desc] = {
            "labour_cost": float(og_job.get("labour_cost") or 0.0),
            "manhour": float(og_job.get("manhour") or 0.0),
            "material_cost_aed": float(og_job.get("material_cost_aed") or 0.0)
        }

    # Overlay the pristine costs back onto the sorted jobs before Excel generation
    for s_job in sorted_jobs:
        desc = str(s_job.get("job_description", "")).strip()
        if desc in pristine_costs:
            s_job["labour_cost"] = pristine_costs[desc]["labour_cost"]
            s_job["manhour"] = pristine_costs[desc]["manhour"]
            s_job["material_cost_aed"] = pristine_costs[desc]["material_cost_aed"]

    return {
        "depot_name": data.get("Depot_Name"),
        "container_id": data.get("container_id"),
        "container_type": final_iso_type,
        "estimate_date": data.get("estimate_date"),
        "jobs": sorted_jobs,
        "total_amount": data.get("total_amount"),
        "man_hour_rate": data.get("man_hour_rate"),
        "total_man_hours": data.get("total_man_hours"),
    }