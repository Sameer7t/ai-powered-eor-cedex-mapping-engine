"""
One-off cleanup: strips placeholder/poisoned entries (ZZ, ZZZ, XX, XXXX)
out of every route-specific mapping file - checking BOTH the key and the
value, since a poisoned entry can appear on either side
(e.g. "sn": "ZZ" OR "zz": "SN" are both corruption).
Run once from src/.
"""
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_DIR = os.path.join(BASE_DIR, "mappings")

PLACEHOLDER_VALUES = {"ZZ", "ZZZ", "XX", "XXXX"}

FILES_TO_CLEAN = [
    "component_mapping_dry.json", "component_mapping_tank.json",
    "repair_mapping_dry.json",    "repair_mapping_tank.json",
    "damage_mapping_dry.json",    "damage_mapping_tank.json",
    "location_mapping_dry.json",  "location_mapping_tank.json",
]

def _is_placeholder(value: str) -> bool:
    return str(value).strip().upper() in PLACEHOLDER_VALUES

def clean():
    for fname in FILES_TO_CLEAN:
        path = os.path.join(MAPPINGS_DIR, fname)
        if not os.path.exists(path):
            print(f"Skip {fname}: not found.")
            continue

        with open(path, "r") as f:
            data = json.load(f)

        removed = {
            k: v for k, v in data.items()
            if _is_placeholder(k) or _is_placeholder(v)
        }
        cleaned = {
            k: v for k, v in data.items()
            if not _is_placeholder(k) and not _is_placeholder(v)
        }

        if removed:
            with open(path, "w") as f:
                json.dump(cleaned, f, indent=4)
            print(f"{fname}: removed {len(removed)} poisoned entr{'y' if len(removed)==1 else 'ies'} -> {removed}")
        else:
            print(f"{fname}: clean, nothing removed.")

if __name__ == "__main__":
    clean()
