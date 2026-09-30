import os
import json
import functools
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
MAPPINGS_DIR = os.path.join(BASE_DIR, "mappings")
FALLBACK_JSON_PATH = os.path.join(MAPPINGS_DIR, "cedex_reference_data.json")

_cached_fallback_data = None


def _get_fallback_data() -> dict:
    global _cached_fallback_data
    if _cached_fallback_data is None:
        if os.path.exists(FALLBACK_JSON_PATH):
            try:
                with open(FALLBACK_JSON_PATH, "r", encoding="utf-8") as f:
                    _cached_fallback_data = json.load(f)
            except Exception as e:
                print(f"[DataLoader] Warning: Could not read fallback JSON: {e}")
                _cached_fallback_data = {}
        else:
            _cached_fallback_data = {}
    return _cached_fallback_data


@functools.lru_cache(maxsize=16)
def get_cedex_sheet(sheet_name: str = "TN") -> pd.DataFrame:
    """
    Loads CEDEX Master sheet ('TN' for Tank, 'GP' for Dry Container).
    Tries data/CEDEX Master.xlsx first, falling back to bundled JSON reference.
    """
    excel_path = os.path.join(DATA_DIR, "CEDEX Master.xlsx")
    if os.path.exists(excel_path):
        try:
            return pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            print(f"[DataLoader] Notice: Error loading {excel_path} sheet {sheet_name}: {e}. Using fallback.")

    fallback = _get_fallback_data()
    records = fallback.get(sheet_name, [])
    if records:
        return pd.DataFrame(records)

    # Minimal schema fallback so callers never crash
    return pd.DataFrame(columns=[
        "Eqp. Type", "Eqp. Type Desc.", "Component", "COM Desc.",
        "Component Desc.", "Repair", "Repair Desc.", "Location",
        "Formula", "Formula Desc.", "Favourite"
    ])


@functools.lru_cache(maxsize=4)
def get_damage_codes() -> pd.DataFrame:
    """Loads damage codes reference from Excel or fallback JSON."""
    excel_path = os.path.join(DATA_DIR, "DamageCodes.xlsx")
    if os.path.exists(excel_path):
        try:
            return pd.read_excel(excel_path)
        except Exception as e:
            print(f"[DataLoader] Notice: Error loading DamageCodes.xlsx: {e}. Using fallback.")

    fallback = _get_fallback_data()
    records = fallback.get("DamageCodes", [])
    if records:
        return pd.DataFrame(records)

    return pd.DataFrame(columns=["Code", "Description"])


@functools.lru_cache(maxsize=4)
def get_iso_equipment_group() -> pd.DataFrame:
    """Loads ISO equipment group reference from Excel or fallback JSON."""
    excel_path = os.path.join(DATA_DIR, "ifgEquipmentISOGroup.xlsx")
    if os.path.exists(excel_path):
        try:
            return pd.read_excel(excel_path, engine="openpyxl")
        except Exception as e:
            print(f"[DataLoader] Notice: Error loading ifgEquipmentISOGroup.xlsx: {e}. Using fallback.")

    fallback = _get_fallback_data()
    records = fallback.get("ISO", [])
    if records:
        return pd.DataFrame(records)

    return pd.DataFrame(columns=["Current ISO Code", "Active"])
