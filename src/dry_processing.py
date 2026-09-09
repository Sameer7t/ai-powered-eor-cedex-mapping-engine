import pandas as pd
from cedex_converter import process_row
from custom_maping_by_human import (
    is_valid_damage_code,
    read_mapping_file,
    get_mapping_files,
)

# ---- GP sheet = dry-container mapping data in the same CEDEX Master.xlsx used for tanks ----
# columns: Eqp. Type, Eqp. Type Desc., Component, COM Desc., Repair, Repair Desc.,
#          Location, Formula, Formula Desc., Favourite
# NOTE: Location cells can hold MULTIPLE space-separated 2-char codes, e.g. "BX BR BL",
# not one 4-char code like the tank (TN) sheet - see location_prefix_matches() below.
df_gp = pd.read_excel(".\\data\\CEDEX Master.xlsx", sheet_name="GP")


def location_prefix_matches(cell_value, prefix_2char):
    """
    GP sheet Location cells look like "BX BR BL" or "DB DX" - one or more
    2-char codes separated by spaces. cedex_converter's LOCN output is a
    4-char padded code like "DXXX" or "BXXX" - we only need the first 2
    characters of that to match one of the codes in the cell.
    """
    if pd.isna(cell_value) or not prefix_2char:
        return False
    codes_in_cell = str(cell_value).strip().upper().split()
    return prefix_2char.strip().upper() in codes_in_cell


def dry_processing(job_description_list, man_hour_rate):
    """
    Takes the raw job_description list straight from PDF extraction
    (same shape as tank's: [{"job_description": ..., "manhour": ..., "material_cost_aed": ...}, ...])
    and runs each description through cedex_converter's rule-based classifier.
    Before validating against the GP sheet, any previously-learned human
    corrections (dry-route only) are applied as overrides, so a code a
    human already fixed once will resolve automatically next time.
    """
    structured = []
    failed_jobs = []

    # Load learned human corrections for the DRY route only
    dry_files = get_mapping_files("dry")
    component_map = read_mapping_file(dry_files["component"])
    repair_map = read_mapping_file(dry_files["repair"])
    location_map = read_mapping_file(dry_files["location"])
    damage_map = read_mapping_file(dry_files["damage"])

    for idx, item in enumerate(job_description_list, start=1):
        desc = item.get("job_description", "") or ""
        manhour = item.get("manhour") or 0
        material_cost = item.get("material_cost_aed")
        labour_cost = manhour * (man_hour_rate or 0)

        job_id = idx

        base_job = {
            "job_id": job_id,
            "manhour": manhour,
            "labour_cost": labour_cost,
            "material_cost_aed": material_cost,
            "job_description": desc,
        }

        result = process_row(desc)

        if result is None:
            # blank/NaN row - nothing to classify
            base_job["status"] = "unmapped"
            failed_jobs.append(base_job)
            continue

        locn = result.get("LOCN") or ""
        cmp_ = result.get("CMP") or ""
        dmg = result.get("DMG") or ""
        rpr = result.get("RPR") or ""

        # ---- apply previously-learned human corrections BEFORE validating ----
        if cmp_.strip().lower() in component_map:
            cmp_ = component_map[cmp_.strip().lower()]
        if rpr.strip().lower() in repair_map:
            rpr = repair_map[rpr.strip().lower()]
        if dmg.strip().lower() in damage_map:
            dmg = damage_map[dmg.strip().lower()]
        if locn.strip().lower() in location_map:
            learned_loc = location_map[locn.strip().lower()]
            locn = learned_loc.ljust(4, "X") if len(learned_loc) < 4 else learned_loc

        locn_prefix = locn.strip().upper()[:2] if locn else ""

        # ---- verify component + repair + location exist together in GP sheet ----
        match = df_gp[
            (df_gp["Component"].astype(str).str.strip().str.upper() == cmp_.strip().upper()) &
            (df_gp["Repair"].astype(str).str.strip().str.upper() == rpr.strip().upper()) &
            (df_gp["Location"].apply(lambda v: location_prefix_matches(v, locn_prefix)))
        ]

        # ---- separately verify the damage code (GP sheet has no Damage column) ----
        damage_ok = is_valid_damage_code(dmg) if dmg else False

        if match.empty or not damage_ok:
            base_job.update({
                "location": locn,
                "component": cmp_,
                "repair": rpr,
                "damage": dmg,
                "status": "unmapped",
            })
            failed_jobs.append(base_job)
            continue

        structured.append({
            **base_job,
            "location": locn,
            "component": cmp_,
            "repair": rpr,
            "damage": dmg,
            "status": "mapped",
            "cedex_code": f"{locn} {cmp_} {rpr} {dmg}",
        })

    return {
        "success_jobs": structured,
        "failed_jobs": failed_jobs,
    }


def dry_processing_node(state):
    data = state["data"]
    job_list = data["job_description"]
    man_hour_rate = data.get("man_hour_rate")

    result = dry_processing(job_list, man_hour_rate)

    # combine both, same pattern as arranging_by_id does for tank -
    # unmapped ones will get caught by confidence_node/human_review_node downstream
    sorted_jobs = result["success_jobs"] + result["failed_jobs"]

    return {"sorted_jobs": sorted_jobs}