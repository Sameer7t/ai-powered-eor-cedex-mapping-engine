import pdfplumber
from google import genai
from google.genai import types
import json
import pandas as pd
from schemas import DepotSchema, JobCategoryList, MultipleEstimates
from dotenv import load_dotenv

df = pd.read_excel(".\\data\\CEDEX Master.xlsx", sheet_name="TN")


load_dotenv()  #
client = genai.Client()


# def pdf_extractor(pdf) -> str:
#     text = ""
#     with pdfplumber.open(pdf) as pdf:
#         for page in pdf.pages:
#             if page.extract_text() != None:
#                 text = text + page.extract_text()
#     # print(text)
#     return text
###########################################################################################

# def pdf_extractor(pdf) -> str:
#     full_text = ""

#     with pdfplumber.open(pdf) as pdf_file:
#         for page_number, page in enumerate(pdf_file.pages, start=1):
#             full_text += f"\n--- PAGE {page_number} ---\n"

#             # layout=True keeps columns/spacing closer to how they visually appear
#             page_text = page.extract_text(layout=True)
#             if page_text:
#                 full_text += page_text + "\n"

#             # also try to pull out any actual tables on this page
#             tables = page.extract_tables()
#             for table_index, table in enumerate(tables, start=1):
#                 full_text += f"\n[TABLE {table_index} on page {page_number}]\n"
#                 for row in table:
#                     # replace None cells with empty string, join with a clear separator
#                     clean_row = [str(cell) if cell is not None else "" for cell in row]
#                     full_text += " | ".join(clean_row) + "\n"

#     return full_text

###########################################################################################

import pdfplumber


def pdf_extractor(pdf_path: str) -> str:
    """
    Extract structured text from a PDF while preserving:
    - page boundaries
    - reading order
    - line structure
    - table-like spacing
    - word order

    Returns:
        str: Structured text suitable for LLM processing.
    """

    pages_output = []

    with pdfplumber.open(pdf_path) as pdf:

        for page_number, page in enumerate(pdf.pages, start=1):

            page_output = []
            page_output.append(f"=== PAGE {page_number} ===")

            # ---------------------------------------------------------
            # 1. Try extracting tables first
            # ---------------------------------------------------------
            tables = page.extract_tables()

            if tables:
                page_output.append("=== TABLE DATA ===")

                for table_number, table in enumerate(tables, start=1):

                    page_output.append(f"--- TABLE {table_number} ---")

                    for row in table:

                        if not row:
                            continue

                        cleaned_row = [cell.strip() if cell else "" for cell in row]

                        # Ignore completely empty rows
                        if not any(cleaned_row):
                            continue

                        page_output.append(" | ".join(cleaned_row))

                page_output.append("=== END TABLE DATA ===")

            # ---------------------------------------------------------
            # 2. Extract individual words with coordinates
            # ---------------------------------------------------------
            words = page.extract_words(
                x_tolerance=3, y_tolerance=3, keep_blank_chars=False
            )

            # If nothing was extracted, continue to next page
            if not words:
                pages_output.append("\n".join(page_output))
                continue

            # ---------------------------------------------------------
            # 3. Group words into visual lines
            # ---------------------------------------------------------
            lines = []

            for word in words:

                word_top = word["top"]

                matched_line = None

                for line in lines:

                    if abs(word_top - line["top"]) <= 3:
                        matched_line = line
                        break

                if matched_line:

                    matched_line["words"].append(word)

                else:

                    lines.append({"top": word_top, "words": [word]})

            # ---------------------------------------------------------
            # 4. Sort lines vertically
            # ---------------------------------------------------------
            lines.sort(key=lambda line: line["top"])

            # ---------------------------------------------------------
            # 5. Sort words horizontally inside each line
            # ---------------------------------------------------------
            page_output.append("=== PAGE TEXT ===")

            for line in lines:

                line["words"].sort(key=lambda word: word["x0"])

                line_text = " ".join(word["text"] for word in line["words"])

                line_text = line_text.strip()

                if line_text:
                    page_output.append(line_text)

            page_output.append("=== END PAGE ===")

            pages_output.append("\n".join(page_output))

    # -------------------------------------------------------------
    # 6. Combine all pages
    # -------------------------------------------------------------
    return "\n\n".join(pages_output)




def process_estimate(text: str) -> list[dict]:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            text,
            """
            Extract all relevant information from this container repair estimate document.

            The document may contain one or more separate repair estimates. Each estimate
            may belong to a different container. Treat each container estimate as an
            independent record.

            DOCUMENT STRUCTURE:
            First identify where each individual container estimate begins and ends.
            Do not mix header information, repair jobs, labour values, material costs,
            or totals between different container estimates.

            For EACH distinct container estimate, extract the following:

            HEADER METADATA:
            - Depot or repair facility name
            - Container ID
            - Container type
            - Estimate date
            - Any other required estimate-level metadata defined in the output schema

            REPAIR JOBS:
            Extract every distinct repair line item belonging to that container estimate.

            For each repair job, preserve the relationship between:
            - Job description
            - Manhours
            - Labour cost
            - Material cost

            CRITICAL ROW ASSOCIATION RULE:
            Costs and labour values must remain associated with the correct repair job.
            Do not assign a value from one repair row to another row. Do not use the
            nearest numerical value unless it belongs to the same logical repair line.

            MULTIPLE-ESTIMATE RULE:
            If the document contains multiple containers, create separate estimate
            records for each container. Never combine repair jobs from different
            containers into a single estimate.

            HEADER ASSOCIATION RULE:
            Apply header metadata only to the repair jobs belonging to that specific
            estimate section. If a new container ID or clearly separate estimate header
            appears, treat it as the start of a new estimate unless the document clearly
            indicates otherwise.

            EXTRACTION RULES:
            - Extract information from the document; do not invent missing values.
            - Do not guess values based on similar estimates.
            - Preserve numerical values accurately.
            - Do not calculate costs unless explicitly required by the output schema.
            - Do not merge multiple repair jobs into one job.
            - Do not split one logical repair job into multiple jobs unless the document
            clearly presents them as separate repair line items.
            - Preserve technical information in job descriptions, including dimensions,
            quantities, component details, and repair specifications.
            - Ignore unrelated information such as terms and conditions, general notes,
            signatures, and administrative text unless required by the schema.

            MISSING OR UNCERTAIN DATA:
            If a required value is missing, unreadable, or cannot be confidently
            associated with the correct estimate or repair job, follow the schema's
            missing-value requirements. Never guess or transfer information from another
            container or repair line.

            PRIORITY:
            Correct separation and association are more important than filling every
            field. The extracted output must accurately preserve the document hierarchy:

            CONTAINER ESTIMATE
                -> HEADER METADATA
                -> REPAIR JOBS
                    -> DESCRIPTION
                    -> MANHOURS
                    -> LABOUR COST
                    -> MATERIAL COST
            """,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MultipleEstimates,  # Updated schema
            temperature=0.0,
        ),
    )

    # Validate and dump the list of estimates
    structured_data = MultipleEstimates.model_validate_json(response.text).model_dump()

    return structured_data["estimates"]


# def process_estimate(text: str) -> DepotSchema:

#     response = client.models.generate_content(
#         model="gemini-3.5-flash-lite",
#         contents=[
#             text,
#             "Extract all container repair line items, costs, and header metadata from this estimate document.",
#         ],
#         config=types.GenerateContentConfig(
#             # Force the model to output strict JSON
#             response_mime_type="application/json",
#             # Force the strict JSON to strictly align to your exact schema configuration
#             response_schema=DepotSchema,
#             temperature=0.0,  # Keep temperature low for deterministic data extraction
#         ),
#     )

#     structured_data = DepotSchema.model_validate_json(response.text).model_dump()

#     return structured_data


# def process_estimate(pdf_path: str) -> dict:
#     with open(pdf_path, "rb") as f:
#         pdf_bytes = f.read()

#     pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

#     response = client.models.generate_content(
#         model="gemini-3.5-flash-lite",
#         contents=[
#             pdf_part,
#             "Extract all container repair line items, costs, and header metadata from this estimate document.",
#         ],
#         config=types.GenerateContentConfig(
#             response_mime_type="application/json",
#             response_schema=DepotSchema,
#             temperature=0.0,
#         ),
#     )

#     structured_data = DepotSchema.model_validate_json(response.text).model_dump()

#     return structured_data


def classify_jobs(data):

    job_desc = data["job_description"]

    job_data = json.dumps(job_desc)

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            job_data,
            """
            Classify each job according to its PRIMARY purpose.

            package_cleaning:
            Use only when the primary job is cleaning as a package or
            standard/package cleaning service.

            leak_test:
            Use only when the primary job is performing a leak test.

            normal:
            Use when the description primarily describes a component repair,
            replacement, renewal, straightening, welding, or other repair work,
            even if the words "Package deal" or "leak test" also appear as
            additional information.

            Do not classify a job as special merely because the phrase
            "Package deal" appears in the description.
            """,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=JobCategoryList,
            temperature=0.0,
        ),
    )

    temp = JobCategoryList.model_validate_json(response.text).job
    job_cat_json = [item.model_dump() for item in temp]
    for item in job_cat_json:
        item["job_id"] = item["job_id"] + 1
    return job_cat_json

def validate_cost_hour(data: dict):
    if data:
        total_mat_cost = 0
        total_labour_cost = 0
        total_man_hour = 0
        jobs = data.get("job_description", [])

        for items in jobs:
            raw_mat_cost = items.get("material_cost_aed")
            job_mat_cost = float(raw_mat_cost) if raw_mat_cost is not None else 0.0

            raw_labour_cost = items.get("labour_cost")
            job_labour_cost = float(raw_labour_cost) if raw_labour_cost is not None else 0.0

            # 1. Extract the new cleaning cost the LLM found
            raw_cleaning_cost = items.get("cleaning_cost")
            job_cleaning_cost = float(raw_cleaning_cost) if raw_cleaning_cost is not None else 0.0

            # 2. Merge cleaning cost into labour cost for downstream processing
            combined_service_cost = job_labour_cost + job_cleaning_cost
            items["labour_cost"] = combined_service_cost

            raw_man_hour = items.get("manhour")
            job_man_hour = float(raw_man_hour) if raw_man_hour is not None else 0.0

            total_mat_cost += job_mat_cost
            total_labour_cost += combined_service_cost
            total_man_hour += job_man_hour

        # Safely extract header totals
        raw_total_man_hours = data.get("total_man_hours")
        total_man_hours = float(raw_total_man_hours) if raw_total_man_hours is not None else 0.0

        raw_total_amount = data.get("total_amount")
        total_amount = float(raw_total_amount) if raw_total_amount is not None else 0.0

        calculated_total_cost = total_mat_cost + total_labour_cost

        # Round to 2 decimal places to prevent floating point validation errors
        if round(calculated_total_cost, 2) == round(total_amount, 2):
            print("Amount Verified.")
            verification_status = "Verified"
        else:
            print(f"Amount Not verified: Calculated {round(calculated_total_cost, 2)} vs Stated {round(total_amount, 2)}")
            verification_status = "Unverified"

        if round(total_man_hour, 2) == round(total_man_hours, 2):
            print("Man hour Verified.")
            manhour_status = "Verified"
        else:
            print(f"Man hour Not verified: Calculated {round(total_man_hour, 2)} vs Stated {round(total_man_hours, 2)}")
            manhour_status = "Unverified"

        for items in jobs:
            items["cost_verification"] = verification_status
            items["manhour_verification"] = manhour_status

            # Clean up the dictionary so downstream files don't trip over the unexpected key
            if "cleaning_cost" in items:
                del items["cleaning_cost"]
    else:
        print("data is empty.")