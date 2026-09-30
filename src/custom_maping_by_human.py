import os
import json
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_DIR = os.path.join(BASE_DIR, "mappings")
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

# Reserved placeholder codes - these NEVER get persisted as reusable
# mappings, whether they show up as the raw extracted text (key) or as
# the human-typed code (value). Either side being a placeholder means
# the mapping has no real meaning and would corrupt matching for future,
# unrelated jobs if saved. Case-insensitive.
PLACEHOLDER_CODES = {"ZZ", "ZZZ", "XX", "XXXX"}


def _mapping_path(name, route):
    """name: 'component' | 'repair' | 'location' | 'damage'
    route: 'dry' or 'tank' -> keeps dry (GP) and tank (TN) corrections separate."""
    suffix = "dry" if route == "dry" else "tank"
    return os.path.join(MAPPINGS_DIR, f"{name}_mapping_{suffix}.json")


def get_mapping_files(route):
    return {
        "component": _mapping_path("component", route),
        "repair": _mapping_path("repair", route),
        "location": _mapping_path("location", route),
        "damage": _mapping_path("damage", route),
    }


def read_mapping_file(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def write_mapping_file(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)


# Ensure all route-specific mapping files exist
for _route in ("tank", "dry"):
    for _f in get_mapping_files(_route).values():
        if not os.path.exists(_f):
            os.makedirs(os.path.dirname(_f), exist_ok=True)
            with open(_f, "w") as _file:
                json.dump({}, _file)

from data_loader import get_cedex_sheet

df_tn = get_cedex_sheet("TN")
df_gp = get_cedex_sheet("GP")


def is_valid_damage_code(code: str) -> bool:
    """Validates 2-character damage codes locally to prevent import crashes."""
    print(f"Checking damage code: {code}")
    if len(code) == 2 and code.isalpha():
        print("Damage code is valid.")
        return True
    return False


def find_matching_row(component_code, repair_code, location_code, route="tank"):
    """Validates the human input against the Master Sheet before allowing a save."""
    df = df_gp if route == "dry" else df_tn

    comp_col = df.get("Component", pd.Series(dtype=str)).astype(str).str.strip().str.upper()
    rep_col = df.get("Repair", pd.Series(dtype=str)).astype(str).str.strip().str.upper()

    query = (comp_col == component_code.upper()) & (rep_col == repair_code.upper())
    result = df[query]

    if result.empty:
        print(f"Error: {component_code} + {repair_code} not found in CEDEX Master ({route}).")
        return None

    for _, row in result.iterrows():
        master_loc_cell = str(row.get("Location", "")).strip().upper()

        if route == "dry":
            master_codes = master_loc_cell.split()
            master_prefixes = [c[:2] for c in master_codes]
            if location_code[:2] in master_prefixes or len(master_codes) == 1:
                return row
        else:
            if master_loc_cell.startswith(location_code[:2]) or not master_loc_cell:
                return row

    print(f"Error: Location {location_code} not valid for this component/repair.")
    return None


def _is_placeholder(value: str) -> bool:
    """Case-insensitive check against the reserved placeholder set."""
    return str(value).strip().upper() in PLACEHOLDER_CODES


def learn_from_human(job, human_answer, route="tank"):
    """Processes human input, formats the job, and saves mappings into the
    route-specific (dry/tank) files - EXCEPT where either the raw extracted
    text (key) or the human-typed code (value) is a placeholder (ZZ/ZZZ/XX/
    XXXX). A placeholder on EITHER side means the pairing has no real
    meaning and would corrupt matching for future, unrelated jobs if saved -
    so it's applied to fix this one job only and never written to disk."""
    words = human_answer.strip().split()
    if len(words) != 4:
        print("Error: Expected exactly 4 words (LOCATION COMPONENT REPAIR DAMAGE).")
        return False

    files = get_mapping_files(route)

    location_word, component_word, repair_word, damage_word = words
    location_code = location_word[:2].upper()

    if not is_valid_damage_code(damage_word):
        print("Error: Invalid or inactive damage code.")
        return False

    matched_row = find_matching_row(component_word, repair_word, location_code, route)
    if matched_row is None:
        return False

    # 1. Capture original extracted text safely BEFORE overwriting
    raw_location = str(job.get("location", "")).strip().lower()
    raw_component = str(job.get("component", "")).strip().lower()
    raw_repair = str(job.get("repair", "")).strip().lower()
    raw_damage = str(job.get("damage", "")).strip().lower()

    # 2. Mutate the Job Dictionary for the Excel output
    final_loc = location_code.ljust(4, "X")
    job["location"] = final_loc
    job["component"] = component_word.upper()
    job["repair"] = repair_word.upper()
    job["damage"] = damage_word.upper()
    job["status"] = "mapped"  # Flag as successfully mapped to bypass the Dead Letter Queue
    job["cedex_code"] = f"{final_loc} {job['component']} {job['repair']} {job['damage']}"

    # 3. Save mappings - skip any pair where EITHER side is a placeholder
    try:
        if raw_component and not _is_placeholder(raw_component) and not _is_placeholder(component_word):
            c_map = read_mapping_file(files["component"])
            c_map[raw_component] = component_word.upper()
            write_mapping_file(files["component"], c_map)
            print(f"  -> Saved Memory [{route}]: component '{raw_component}' -> {component_word.upper()}")
        elif raw_component and (_is_placeholder(raw_component) or _is_placeholder(component_word)):
            print(f"  -> Placeholder component ('{raw_component}' / '{component_word.upper()}') NOT saved to memory (this job only).")

        if raw_repair and not _is_placeholder(raw_repair) and not _is_placeholder(repair_word):
            r_map = read_mapping_file(files["repair"])
            r_map[raw_repair] = repair_word.upper()
            write_mapping_file(files["repair"], r_map)
            print(f"  -> Saved Memory [{route}]: repair '{raw_repair}' -> {repair_word.upper()}")
        elif raw_repair and (_is_placeholder(raw_repair) or _is_placeholder(repair_word)):
            print(f"  -> Placeholder repair ('{raw_repair}' / '{repair_word.upper()}') NOT saved to memory (this job only).")

        if raw_location and not _is_placeholder(raw_location) and not _is_placeholder(location_code):
            l_map = read_mapping_file(files["location"])
            l_map[raw_location] = location_code
            write_mapping_file(files["location"], l_map)
            print(f"  -> Saved Memory [{route}]: location '{raw_location}' -> {location_code}")
        elif raw_location and (_is_placeholder(raw_location) or _is_placeholder(location_code)):
            print(f"  -> Placeholder location ('{raw_location}' / '{location_code}') NOT saved to memory (this job only).")

        if raw_damage and not _is_placeholder(raw_damage) and not _is_placeholder(damage_word):
            d_map = read_mapping_file(files["damage"])
            d_map[raw_damage] = damage_word.upper()
            write_mapping_file(files["damage"], d_map)
            print(f"  -> Saved Memory [{route}]: damage '{raw_damage}' -> {damage_word.upper()}")
        elif raw_damage and (_is_placeholder(raw_damage) or _is_placeholder(damage_word)):
            print(f"  -> Placeholder damage ('{raw_damage}' / '{damage_word.upper()}') NOT saved to memory (this job only).")

    except Exception as e:
        print(f"CRITICAL ERROR SAVING MEMORY: {e}")

    return True