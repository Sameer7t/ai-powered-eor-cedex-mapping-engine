from typing import Annotated
from enum import Enum
from pydantic import BaseModel, Field, StringConstraints

from models.enums import JobCategory


# ============================================================
# CONSTRAINTS
# ============================================================

ID_PATTERN = r"^[A-Z]{4}[0-9]{7}$"

strict_container_ID = Annotated[
    str,
    StringConstraints(
        pattern=ID_PATTERN,
        min_length=11,
        max_length=11
    )
]

ShortRepair = Annotated[
    str,
    StringConstraints(max_length=20)
]


# ============================================================
# JOB CLASSIFICATION SCHEMA
# ============================================================

class JobCategories(BaseModel):
    job_id: int = Field(
        description=(
            "The unique identifier of the input job. "
            "Return the exact job_id provided in the input. "
            "Do not create, modify, renumber, or infer job IDs."
        )
    )

    job_categories: JobCategory = Field(
        description=(
            "Classify the job using ONLY one of the allowed JobCategory enum values. "
            "Select the category that best represents the entire job description. "
            "Do not create new categories and do not return multiple categories."
        )
    )


class JobCategoryList(BaseModel):
    job: list[JobCategories] = Field(
        description=(
            "A list containing exactly one classification record for every input job. "
            "Preserve the original job_id for each record. "
            "Do not omit, duplicate, merge, split, or reorder jobs."
        )
    )


# ============================================================
# JOB DESCRIPTION BREAKDOWN SCHEMA
# ============================================================

class DescriptionBreakdown(BaseModel):

    job_id: int = Field(
        description=(
            "The unique identifier of the input job. "
            "Copy the job_id exactly as supplied. "
            "Do not create, modify, renumber, or infer this value."
        )
    )

    location: str = Field(
        default="",
        description=(
            "Extract only the physical location where the repair is performed. "
            "Examples include: Front, Rear, Top, Bottom, LHS, RHS, "
            "Front Top, Rear RHS, Rear RHS Corner, Door End, Side Wall. "
            "Keep meaningful directional qualifiers when explicitly stated. "
            "Do not include the component name in this field. "
            "Do not infer or invent a location. "
            "Return an empty string if no location is explicitly stated."
        )
    )

    component: str = Field(
        default="",
        description=(
            "Extract the primary physical component or part receiving the repair. "
            "Return a short, specific component name only. "
            "Remove location words, damage descriptions, repair instructions, "
            "dimensions, quantities, measurements, and unrelated filler text. "
            "Examples: Rail, Corner Cast, Pressure Gauge, Manlid Gasket, "
            "Spill Box, Panel, Shell. "
            "Do not include repair actions in this field. "
            "Do not invent a component. "
            "Return an empty string if the component cannot be identified."
        )
    )

    repair: ShortRepair = Field(
        default="",
        description=(
            "Extract the primary repair action performed on the component. "
            "Return a concise repair action, normally one to four words. "
            "Examples: Repair, Renew, Replace, Straighten, Weld, Insert, "
            "Clean, Water Wash, Patch, Paint, Leak Test. "
            "Do not include dimensions, quantities, tools, instructions, "
            "locations, damage descriptions, or unrelated additional work. "
            "If the description contains multiple actions, select the primary "
            "action directly applied to the main component. "
            "Do not invent a repair action. "
            "Return an empty string if no repair action can be determined."
        )
    )

    damage: str = Field(
        default="",
        description=(
            "Extract the physical damage, defect, or condition affecting the component. "
            "Examples include: Dented, Deformed, Bent, Broken, Cracked, "
            "Corroded, Loose, Hole, Scratched, Dirty, Leaking, Missing. "
            "Do not infer damage from the repair action. "
            "Do not include repair actions, locations, measurements, "
            "or unrelated instructions. "
            "Return an empty string if no damage or defect is explicitly stated."
        )
    )

    manhour: float | None = Field(
        default=None,
        description=(
            "The labour time assigned to this specific job, expressed in hours. "
            "Extract the value only when it is explicitly available in the input job data. "
            "Convert minutes to hours when necessary. "
            "Examples: 30 minutes = 0.5, 90 minutes = 1.5, 2 hours = 2.0. "
            "Do not estimate, calculate, or invent labour time. "
            "Return null if no labour time is provided."
        )
    )

    labour_cost: float | None = Field(
        default=None,
        description=(
            "The labour cost assigned specifically to this job. "
            "Return only the numeric monetary value when explicitly provided. "
            "Do not include material cost or total job cost. "
            "Do not calculate or estimate this value. "
            "Return null if the labour cost is not provided."
        )
    )

    material_cost_aed: float | None = Field(
        default=None,
        description=(
            "The material or parts cost assigned specifically to this job, "
            "expressed in AED. "
            "Return only the numeric value. "
            "Do not include labour cost or total job cost. "
            "Do not estimate or calculate material cost. "
            "Return null if no material cost is provided."
        )
    )

    job_description: str = Field(
        description=(
            "Copy the complete original repair job description for this job. "
            "Preserve all meaningful information, including repair wording, "
            "component references, location references, dimensions, quantities, "
            "technical specifications, and relevant instructions. "
            "Do not summarize, shorten, normalize, categorize, or map the "
            "description to CEDEX terminology or codes. "
            "Do not remove technical details. "
            "Do not invent information. "
            "The output must represent one complete original job description."
        )
    )


class DescriptionBreakdowns(BaseModel):
    descriptions: list[DescriptionBreakdown] = Field(
        description=(
            "A list containing exactly one breakdown record for each input job. "
            "Preserve job IDs and do not split one job into multiple records."
        )
    )


# ============================================================
# INITIAL PDF JOB EXTRACTION
# ============================================================

class JobDescription(BaseModel):

    job_description: str = Field(
        description=(
            "Extract one complete container repair job description from the estimate. "
            "Copy the job description as faithfully as possible. "
            "Preserve technical details, dimensions, quantities, component names, "
            "repair instructions, and relevant wording. "
            "Do not split one line item into multiple jobs. "
            "Do not summarize, normalize, categorize, or map the job to CEDEX. "
            "Do not invent missing information."
        )
    )

    manhour: float = Field(
        default= 0 ,
        description=(
            "Extract the labour time associated with this specific job, "
            "expressed in hours. "
            "Return only the numeric value. "
            "Do not estimate or invent a value. "
            "Return null when labour time is not available."
        )
    )

    labour_cost: float = Field(
        default= 0 ,
        description=(
            "Extract the labour or service cost for this specific repair line item. "
            "Use the value shown under the LAB / SER COST column. "
            "Do not confuse this value with Labour HRS or Material Cost. "
            "Return only the numeric monetary value."
        )
    )

    cleaning_cost: float = Field(
        default= 0 ,
        description=(
            "Extract the flat cleaning fee for this specific line item, if present. "
            "Use the value strictly shown under the 'Cleaning' column. "
            "Return only the numeric monetary value. Return 0 if blank."
        )
    )

    material_cost_aed: float = Field(
        default= 0 ,
        description=(
            "Extract the material or parts cost associated with this specific job "
            "in AED. "
            "Return only the numeric value. "
            "Do not include labour cost. "
            "Do not estimate or invent a value. "
            "Return null when material cost is not available."
        )
    )


# ============================================================
# COMPLETE ESTIMATE / DEPOT SCHEMA
# ============================================================

class DepotSchema(BaseModel):

    Depot_Name: str = Field(
        description=(
        "Extract the depot, repair facility, workshop, or service location "
        "responsible for carrying out the container repair estimate. This field "
        "identifies the facility or organization where the repair work is being "
        "performed.\n\n"

        "SOURCE OF TRUTH:\n"
        "Extract the value from the document field explicitly labeled 'DEPOT', "
        "'DEPOT NAME', 'REPAIR DEPOT', 'REPAIR FACILITY', 'WORKSHOP', "
        "'SERVICE LOCATION', or another clearly equivalent label identifying "
        "the physical repair facility.\n\n"

        "PRIORITY RULE:\n"
        "When multiple company names, addresses, branches, or locations appear "
        "in the document, select only the name directly associated with the "
        "repair facility/depot field or the organization clearly identified as "
        "performing the repair work. Do not automatically select the largest, "
        "first, or most prominent company name.\n\n"

        "VISUAL ASSOCIATION RULE:\n"
        "In structured documents, identify the depot-related label first and "
        "extract only the value visually associated with that label. The value "
        "may appear beside, below, or in the same row as the label. Do not select "
        "a nearby address, customer name, or company name unless it is clearly "
        "associated with the depot/repair facility.\n\n"

        "EXACT EXTRACTION:\n"
        "Return the depot or repair facility name exactly as written in the "
        "source document. Preserve meaningful spelling, abbreviations, numbers, "
        "and identifiers. Do not translate, normalize, expand abbreviations, "
        "correct spelling, or rename the facility.\n\n"

        "DO NOT CONFUSE THE DEPOT WITH:\n"
        "- Customer name\n"
        "- Container owner or leasing company\n"
        "- Shipping line\n"
        "- Manufacturer\n"
        "- Billing company\n"
        "- Invoice recipient\n"
        "- Supplier\n"
        "- Inspector name\n"
        "- Contact person\n"
        "- Depot address\n"
        "- Customer address\n"
        "- Branch name unrelated to the repair facility\n"
        "- City or country alone unless it is explicitly used as the depot name.\n\n"

        "MULTIPLE FACILITIES RULE:\n"
        "If multiple depots, branches, workshops, or company locations are "
        "mentioned, select the facility directly associated with the current "
        "repair estimate or the facility explicitly identified as carrying out "
        "the repair work. Ignore unrelated branches, headquarters, billing "
        "offices, customer locations, and historical references.\n\n"

        "UNCERTAINTY RULE:\n"
        "If the depot or repair facility cannot be confidently identified from "
        "the document, return an empty string. Never infer or invent the depot "
        "name from the document address, city, customer information, container "
        "owner, or other contextual clues.\n\n"

        "Accuracy is more important than filling the field. Only return a depot "
        "name when it can be reliably associated with the repair facility "
        "responsible for the estimate."
        )
    )

    container_id: strict_container_ID = Field(
        description=(
            "Extract the container identification number. "
            "The value must contain exactly 11 characters: "
            "the first 4 characters must be uppercase letters and the final "
            "7 characters must be digits. "
            "Example: ABCD1234567. "
            "Do not modify, repair, guess, or invent the container ID."
        )
    )

    container_type: str = Field(
    description=(
        "Extract the container type used to determine which processing pipeline "
        "must handle this repair estimate. This value is a critical routing field "
        "and must be extracted accurately.\n\n"

        "SOURCE OF TRUTH:\n"
        "Extract the value ONLY from the document field explicitly labeled "
        "'TANK TYPE', 'CONTAINER TYPE', 'EQUIPMENT TYPE', or another clearly "
        "equivalent field that explicitly identifies the physical type of the "
        "container being repaired.\n\n"

        "PRIORITY RULE:\n"
        "If multiple possible type-related fields exist, prefer the value directly "
        "associated with the explicit container/tank/equipment type label. "
        "The value must belong to the same field, row, or visual label-value pair. "
        "Do not take a nearby value simply because it appears close to the label.\n\n"

        "EXACT EXTRACTION:\n"
        "Return the type exactly as written in the source document, preserving all "
        "meaningful letters, numbers, and spacing. Examples may include 'IMO 1', "
        "'22G1', '42G1', '45G1', '22K1', or other valid equipment-type codes. "
        "Do not normalize, translate, expand, shorten, correct, or guess the value.\n\n"

        "DO NOT CONFUSE CONTAINER TYPE WITH:\n"
        "- Container ID or container number\n"
        "- ISO container identification number\n"
        "- Order number\n"
        "- Receipt number\n"
        "- Estimate number\n"
        "- Job number\n"
        "- Cargo name or commodity\n"
        "- Customer name\n"
        "- Depot name\n"
        "- IMO hazard classification unless it is explicitly the value of the "
        "container/tank type field\n"
        "- UN number\n"
        "- Capacity or volume\n"
        "- Weight, tare weight, or gross weight\n"
        "- Date\n"
        "- Repair codes\n"
        "- CEDEX codes\n"
        "- Any other number or code appearing elsewhere in the document.\n\n"

        "VISUAL ASSOCIATION RULE:\n"
        "When reading a structured document, identify the label first and then "
        "extract only the value visually associated with that label. Do not select "
        "the first code that resembles a container type.\n\n"

        "MULTIPLE VALUES RULE:\n"
        "If multiple container or tank type values appear in the document, use the "
        "value associated with the container currently being repaired. Ignore "
        "historical references, examples, cargo classifications, and unrelated "
        "containers.\n\n"

        "UNCERTAINTY RULE:\n"
        "If the container type field is missing, empty, unreadable, ambiguous, or "
        "cannot be confidently associated with the correct label, return an empty "
        "string. Never infer the container type from the container number, repair "
        "description, dimensions, cargo, or other contextual clues.\n\n"

        "The reliability of the downstream Tank-versus-Dry processing route depends "
        "on this value. Accuracy is more important than filling the field. When in "
        "doubt, return an empty string rather than guessing."
    )
)

    estimate_date: str = Field(
        description=(
            "Extract the date on which the estimate was created or issued. "
            "Preserve the date as presented in the source when possible. "
            "Do not infer or invent a date."
        )
    )

    job_description: list[JobDescription] = Field(
        description=(
            "Extract every repair line item from the estimate as a separate job. "
            "Each source repair line must produce one JobDescription record. "
            "Do not merge separate jobs and do not split one job unless the "
            "source document clearly presents them as separate line items. "
            "Preserve the original job order."
        )
    )

    total_amount: float = Field(
        default= 0 ,
        description=(
            "Extract the total final amount of the estimate. "
            "Return only the numeric value. "
            "Do not calculate the total from individual jobs unless the document "
            "explicitly identifies that calculated value as the total amount. "
            "Do not include currency symbols."
        )
    )

    man_hour_rate: float = Field(
        default= 0 ,
        description=(
            "Extract the labour or man-hour rate stated in the estimate. "
            "Return only the numeric value. "
            "Do not guess the currency or assume a rate. "
            "Do not calculate the rate. "
            "Return null if no labour rate is explicitly provided."
        )
    )

    total_man_hours: float | None = Field(
        default=None,
        description=(
            "Extract the total labour hours for all repair jobs. "
            "Return the numeric value in hours. "
            "Do not calculate or estimate the total. "
            "Return null if the total labour hours are not explicitly provided."
        )
    )
# Add this below your DepotSchema definition

class MultipleEstimates(BaseModel):
    estimates: list[DepotSchema] = Field(
        description=(
            "A list of complete container repair estimates. "
            "If the document contains multiple estimates for different containers, "
            "extract each one as a separate DepotSchema object. "
            "Do not merge separate estimates into one."
        )
    )