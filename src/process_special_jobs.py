import json
from mappings.special_job_mapping import SPECIAL_JOB_CEDEX


def process_special_jobs(special_jobs: list):
    result = []

    for items in special_jobs:

        category = items["job_categories"]

        special_mapping = SPECIAL_JOB_CEDEX.get(category)

        if special_mapping:
            cedex_code = (
                f'{special_mapping["location"]} '
                f'{special_mapping["component"]} '
                f'{special_mapping["repair"]} '
                f'{special_mapping["damage"]}'
            )

            result.append(
                {
                    "job_id": items["job_id"],
                    **special_mapping,
                    "manhour": items["manhour"],
                    "labour_cost": items["labour_cost"],
                    "material_cost_aed": items["material_cost_aed"],
                    "status": "mapped",
                    "cedex_code": cedex_code,
                    "job_description": items["job_description"],
                }
            )

    return result
