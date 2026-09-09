import pandas as pd

from mappings.mapping import (
    component_mapping as static_comp_map,
    repair_mapping as static_rep_map,
    location_mapping as static_loc_map,
    damage_mapping as static_dmg_map,
)
from custom_maping_by_human import (
    read_mapping_file,
    get_mapping_files,
)

# Load both sheets into memory globally
df_tn = pd.read_excel(".\\data\\CEDEX Master.xlsx", sheet_name="TN")
df_gp = pd.read_excel(".\\data\\CEDEX Master.xlsx", sheet_name="GP")

def cedex_mapping(normal_job_dict, container_route="tank"):
    # Pull fresh data from human memory files - route-specific (dry vs tank)
    route_files = get_mapping_files(container_route)
    human_component_mapping = read_mapping_file(route_files["component"])
    human_repair_mapping = read_mapping_file(route_files["repair"])
    human_location_mapping = read_mapping_file(route_files["location"])
    human_damage_mapping = read_mapping_file(route_files["damage"])

    # Merge dictionaries
    comp_map = {**static_comp_map, **human_component_mapping}
    rep_map = {**static_rep_map, **human_repair_mapping}
    loc_map = {**static_loc_map, **human_location_mapping}
    dmg_map = {**static_dmg_map, **human_damage_mapping}

    df = df_gp if container_route == "dry" else df_tn

    # Safely extract all possible column variations from the master sheet
    comp_col = df.get("Component", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    comp_desc_1 = df.get("COM Desc.", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    comp_desc_2 = df.get("Component Desc.", pd.Series(dtype=str)).astype(str).str.strip().str.lower()

    rep_col = df.get("Repair", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    rep_desc_1 = df.get("Repair Desc.", pd.Series(dtype=str)).astype(str).str.strip().str.lower()

    damage_by_job_id = {}
    for items in normal_job_dict:
        raw_damage = items.get("damage", "")
        key = raw_damage.lower() if raw_damage else ""
        damage_by_job_id[items["job_id"]] = dmg_map.get(key, raw_damage)

    failed_jobs = []
    structured = []

    for items in normal_job_dict:
        component = items.get("component", "").strip().lower()
        repair = items.get("repair", "").strip().lower()
        location = items.get("location", "").strip().lower()

        mapped_component = str(comp_map.get(component, component)).strip().lower()
        mapped_repair = str(rep_map.get(repair, repair)).strip().lower()
        mapped_location_raw = loc_map.get(location, location)

        job_damage = damage_by_job_id.get(items["job_id"], items.get("damage", ""))
        job_loc_prefix = str(mapped_location_raw)[:2].upper() if mapped_location_raw else ""

        # OMNI-SEARCH QUERY: Checks Abbreviation Code OR Description Columns safely
        query = (
            ( (comp_col == mapped_component) | (comp_desc_1 == mapped_component) | (comp_desc_2 == mapped_component) ) &
            ( (rep_col == mapped_repair) | (rep_desc_1 == mapped_repair) )
        )

        result = df[query]

        if result.empty:
            items["status"] = "unmapped"
            failed_jobs.append(items)
            continue

        matched_row = None
        final_location_code = None

        for _, row in result.iterrows():
            master_loc_cell = str(row.get("Location", "")).strip().upper()

            if container_route == "dry":
                master_codes = master_loc_cell.split()
                master_prefixes = [code[:2] for code in master_codes]

                if job_loc_prefix and job_loc_prefix in master_prefixes:
                    matched_row = row
                    final_location_code = job_loc_prefix.ljust(4, "X")
                    break
                elif not job_loc_prefix and len(master_codes) == 1:
                    matched_row = row
                    final_location_code = master_codes[0][:2].ljust(4, "X")
                    break
            else:
                if job_loc_prefix and master_loc_cell.startswith(job_loc_prefix):
                    matched_row = row
                    final_location_code = job_loc_prefix.ljust(4, "X")
                    break
                elif not job_loc_prefix:
                    matched_row = row
                    final_location_code = master_loc_cell[:2].ljust(4, "X")
                    break

        if matched_row is None or final_location_code is None:
            items["status"] = "unmapped"
            failed_jobs.append(items)
            continue

        structured.append({
            "job_id": items["job_id"],
            "location": final_location_code,
            "component": matched_row["Component"],
            "repair": matched_row["Repair"],
            "damage": job_damage,
            "manhour": items["manhour"],
            "labour_cost": items["labour_cost"],
            "material_cost_aed": items["material_cost_aed"],
            "status": "mapped",
            "cedex_code": f"{final_location_code} {matched_row['Component']} {matched_row['Repair']} {job_damage}",
            "job_description": items["job_description"],
        })

    return {
        "success_jobs": structured,
        "failed_jobs": failed_jobs,
    }