import json
import time
from google import genai
from dotenv import load_dotenv
from google.genai import types
from schemas import DescriptionBreakdowns

load_dotenv()
client = genai.Client()


def process_normal_jobs(job_description: list):

    job_data_json = json.dumps(job_description)
    # time.sleep(5)
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            job_data_json,
            """
                        Process each input job description as ONE record.

                        Do not split a job description into multiple records, even if
                        multiple components, actions, or activities are mentioned.

                        For each input description, extract:
                        - Location
                        - Component
                        - Repair
                        - Damage

                        Rules:

                        GENERAL:
                        - Preserve the relationship between the extracted fields and the
                        original job description.
                        - Do not invent information.
                        - If a field cannot be determined, return an empty string.

                        COMPONENT:
                        - Return ONLY the main component being repaired or worked on.
                        - Keep Component SHORT: preferably 1–4 words.
                        - Do not copy the entire phrase or sentence from the job description.
                        - Remove unnecessary words such as "repair", "damaged", "work on",
                        "for", "with", "assembly", or other filler words when they are not
                        part of the component name.
                        - Do not include the repair action, damage description, measurements,
                        quantities, materials, or instructions in Component.
                        - Use the simplest specific component name supported by the description.
                        - Examples:
                        "Corner Cast repair" → "Corner Cast"
                        "damaged rail assembly" → "Rail"
                        "repair to manlid spill box" → "Manlid Spill Box"
                        "PRV valve replacement" → "PRV"
                        "tank shell interior cleaning" → "Tank Shell Interior"

                        REPAIR — STRICT RULE: Return ONLY the PRIMARY repair action. Repair must normally contain ONE action word. Maximum: TWO words. Valid examples: - Renew - Replace - Straighten - Weld - Clean - Repair - Install - Remove - Refit - Reseal - Insert INVALID: - "Insert 150x100x300mm+Gusset plate straighten" - "straighten for this work walkway remove refix" - "renew nut bolt" - Any sentence or instruction Remove ALL: - measurements - dimensions - quantities - material names - part sizes - technical instructions - explanations - secondary repair actions If multiple repair actions are mentioned, select ONLY the PRIMARY repair action most directly associated with the main component. Do not combine multiple repair actions. Never return a phrase containing technical instructions.

                        DAMAGE:
                        - Describe ONLY the physical condition or problem.
                        - Do not include the repair action.
                        - Do not include unnecessary details or instructions.

                        LOCATION:
                        - Return ONLY the relevant location.
                        - Do not include the component, repair action, or damage description.
                        """,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DescriptionBreakdowns,
            temperature=0.0,
        ),
    )
    structured_data = DescriptionBreakdowns.model_validate_json(
        response.text
    ).descriptions
    normal_job_json = [job.model_dump() for job in structured_data]



    return normal_job_json
