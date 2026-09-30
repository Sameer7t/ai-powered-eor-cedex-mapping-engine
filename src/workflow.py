from typing import TypedDict
import pandas as pd
import json
import os
import glob
import uuid
from custom_maping_by_human import learn_from_human, read_mapping_file, write_mapping_file
from pdf_extractor import pdf_extractor, validate_cost_hour, classify_jobs, process_estimate
from process_normal_jobs import process_normal_jobs
from process_special_jobs import process_special_jobs
from categorize import categorize_list
from cedex_mapping import cedex_mapping
from arranging_by_job_id import arranging_by_id
from custom_maping_by_human import learn_from_human
from build_invoice import build_invoice
from excel_report import generate_excel_report
from dry_processing import dry_processing_node
from excel_extractor import excel_extractor
from translation_cache import translate_job_description
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
import os
import sys
import glob

# 1. Define paths globally
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUCCESS_PATH = os.path.join(BASE_DIR, "..", "data", "output", "MASTER_SUCCESS_COMBINED.xlsx")
FAILED_PATH = os.path.join(BASE_DIR, "..", "data", "output", "MASTER_FAILED_DLQ.xlsx")


# =====================================================================
# 3. Rest of your script continues below (Graph building, LLM setup, etc.)
# =====================================================================

# ... existing paths ...

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MAPPING_DIR = os.path.join(BASE_DIR, "mappings")
MAPPING_DIR = os.environ.get("MAPPING_DIR", DEFAULT_MAPPING_DIR)
DAMAGE_FILE = os.path.join(MAPPING_DIR, "human_damage_mapping.json")

# Add the new storage path for container types
CONTAINER_TYPE_FILE = os.path.join(MAPPING_DIR, "human_container_type_mapping.json")

LOCATION_FILE = os.path.join(MAPPING_DIR, "human_location_mapping.json")
COMPONENT_FILE = os.path.join(MAPPING_DIR, "human_component_mapping.json")
REPAIR_FILE = os.path.join(MAPPING_DIR, "human_repair_mapping.json")
DAMAGE_FILE = os.path.join(MAPPING_DIR, "human_damage_mapping.json")

SAMPLES_DIR = "samples"
# Container routing definitions
TANK_TYPES = {
    "IMO 1",
    "IMO 2",
    "IMO 3",
    "22K1",
}

DRY_TYPES = {
    "22G1",
    "42G1",
    "45G1",
}

def enforce_file_locks():
    """Halt the entire script immediately if output files are locked by the OS."""
    for filepath in [SUCCESS_PATH, FAILED_PATH]:
        if os.path.exists(filepath):
            try:
                # Attempting to open in append mode instantly triggers OS permission denial if Excel is open
                with open(filepath, 'a'):
                    pass
            except PermissionError:
                print("\n" + "="*70)
                print("🛑 CRITICAL ERROR: YOUR EXCEL FILE IS CURRENTLY OPEN! 🛑")
                print(f"File locked: {os.path.basename(filepath)}")
                print("You must completely close Microsoft Excel before running this pipeline.")
                print("="*70 + "\n")
                sys.exit(1)  # Instantly kill the Python process with an error code

# 2. EXECUTE THE CHECK IMMEDIATELY
enforce_file_locks()

def route_container(container_type: str) -> str:
    if not container_type:
        return "human_review"

    container_type = container_type.strip().upper()

    # 1. Check hardcoded definitions first
    if container_type in {t.upper() for t in TANK_TYPES}:
        return "tank"

    if container_type in {t.upper() for t in DRY_TYPES}:
        return "dry"

    # 2. Check the historical human-reviewed data
    learned_types = read_mapping_file(CONTAINER_TYPE_FILE)
    if container_type in learned_types:
        print(f"Route found in memory: {container_type} -> {learned_types[container_type]}")
        return learned_types[container_type]

    # 3. If completely unknown, send to the LangGraph interrupt
    return "human_review"


class State(TypedDict):
    # Removed pdf_path and extracted_text. State now tracks a single estimate.
    file_name: str
    data: dict
    classification: list
    sorted_jobs: dict
    invoice: dict
    container_route: str


def validate_cost_hours(state: State):
    data = state["data"]
    validate_cost_hour(data)
    return {}


def container_router_node(state: State):
    container_type = state["data"].get("container_type")
    route = route_container(container_type)
    return {"container_route": route}

def container_type_review_node(state: State):
    container_type = state["data"].get("container_type", "")

    message = (
        f"Unrecognized container type: '{container_type}'.\n"
        "Please type 'tank' or 'dry' to route this container manually."
    )

    while True:
        human_answer = interrupt({"message": message})
        answer_clean = human_answer.strip().lower()

        if answer_clean in ("tank", "dry"):
            # If the LLM extracted a string, save the human's decision for the future
            if container_type:
                learned_types = read_mapping_file(CONTAINER_TYPE_FILE)
                # Map the exact extracted string to the human's route decision
                learned_types[container_type.strip().upper()] = answer_clean
                write_mapping_file(CONTAINER_TYPE_FILE, learned_types)
                print(f"Saved new container type mapping: {container_type.upper()} -> {answer_clean}")

            return {"container_route": answer_clean}

        message = "Invalid entry. Please type exactly 'tank' or 'dry'."

def decide_container_route(state: State):
    return state["container_route"]


def classification(state: State):
    data = state["data"]

    # Check if forced injection is necessary in production
    if not data.get("container_type"):
        data["container_type"] = "22K1"

    classification_data = classify_jobs(data)

    return {
        "classification": classification_data,
        "data": data
    }

def process_jobs(state: State):
    jobs_data = state["data"]["job_description"]
    classification_data = state["classification"]
    jobs = categorize_list(jobs_data, classification_data)

    # Extract the route from state
    route = state.get("container_route", "tank")

    n_jobs = process_normal_jobs(jobs["normal_jobs"])
    s_jobs = process_special_jobs(jobs["special_jobs"])

    # Pass the route to the updated mapping function, removing df1
    f_n_s_jobs = cedex_mapping(n_jobs, route)

    sorted_jobs = arranging_by_id(f_n_s_jobs, s_jobs)

    return {"sorted_jobs": sorted_jobs}

def confidence_node(state: State):
    jobs = state["sorted_jobs"]
    score = 1.0

    for job in jobs:
        if not job.get("component"):
            score -= 0.25
        if not job.get("repair"):
            score -= 0.25
        if not job.get("location"):
            score -= 0.25
        if not job.get("damage"):
            score -= 0.25

    confidence = "high" if score >= 0.8 else "low"

    return {
        "confidence_score": score,
        "confidence": confidence
    }


memory = MemorySaver()


def human_review_node(state: State):
    jobs = state["sorted_jobs"]
    confidence = state.get("confidence")
    route = state.get("container_route", "tank")
    for job in jobs:
        needs_human = False

        if confidence == "low" or job.get("status") == "unmapped":
            needs_human = True

        if needs_human:
            print("This job needs human review:", job.get("job_id"))

            # Display-only translation - job["job_description"] itself is
            # left untouched, so Excel output and any re-classification
            # still use the original text. Glossary -> cache -> Gemini,
            # in that order, so repeat phrases never re-hit the API.
            display_description = translate_job_description(job.get("job_description"))

            message = (
                f"Job ID: {job.get('job_id')}\n"
                f"Location: {job.get('location')}\n"
                f"Component: {job.get('component')}\n"
                f"Repair: {job.get('repair')}\n"
                f"Damage: {job.get('damage')}\n"
                f"Manhour: {job.get('manhour')}\n"
                f"Labour Cost: {job.get('labour_cost')}\n"
                f"JOB DESCRIPTION: {display_description}\n"
                "\nPlease enter code as: LOCATION COMPONENT REPAIR DAMAGE\n"
                "Example: AFXX YXT AX DY\n"
                "Type 'skip' to skip only this job\n"
                "Type 'exit' to skip this and all remaining jobs"
            )

            skip_everything = False

            while True:
                human_answer = interrupt({
                    "message": message,
                    "job": job,
                })

                print("Human entered:", human_answer)
                answer_clean = human_answer.strip().lower()

                if answer_clean == "skip":
                    print("Skipping only this job:", job.get("job_id"))
                    job["status"] = "skipped"
                    break

                if answer_clean == "exit":
                    print("Skipping this job and all remaining jobs.")
                    job["status"] = "skipped"
                    skip_everything = True
                    break

                success = learn_from_human(job, human_answer, route)

                if success:
                    job["status"] = "reviewed"
                    break
                else:
                    message = "That combination was not found in CEDEX Master. Please enter again."

            if skip_everything:
                break

    return {"sorted_jobs": jobs}


def builds_invoice(state: State):
    data = state["data"]
    sorted_jobs = state["sorted_jobs"]

    # Build the dictionary, but do not write to disk here
    invoice = build_invoice(data, sorted_jobs)

    return {"invoice": invoice}

# Build the state graph without extraction nodes
print("Building the Graph with Memory Checkpointing...")
graph_builder = StateGraph(State)

graph_builder.add_node("validater", validate_cost_hours)
graph_builder.add_node("container_router", container_router_node)
graph_builder.add_node("container_type_review", container_type_review_node)
graph_builder.add_node("classifier", classification)
graph_builder.add_node("jobs_processor", process_jobs)
graph_builder.add_node("dry_processor", dry_processing_node)
graph_builder.add_node("confidence", confidence_node)
graph_builder.add_node("human_review", human_review_node)
graph_builder.add_node("invoice_builder", builds_invoice)

graph_builder.add_edge(START, "validater")
graph_builder.add_edge("validater", "container_router")

graph_builder.add_conditional_edges(
    "container_router",
    decide_container_route,
    {
        "tank": "classifier",
        "dry": "dry_processor",
        "human_review": "container_type_review",
    },
)

graph_builder.add_conditional_edges(
    "container_type_review",
    decide_container_route,
    {
        "tank": "classifier",
        "dry": "dry_processor",
    },
)

# ---- tank pipeline ----
graph_builder.add_edge("classifier", "jobs_processor")
graph_builder.add_edge("jobs_processor", "confidence")

# ---- dry pipeline ----
graph_builder.add_edge("dry_processor", "confidence")

# ---- shared tail ----
graph_builder.add_edge("confidence", "human_review")
graph_builder.add_edge("human_review", "invoice_builder")
graph_builder.add_edge("invoice_builder", END)

app = graph_builder.compile(checkpointer=memory)
def process_single_document(file_path: str):
    print(f"\n===== Processing: {file_path} =====")
    file_name, file_extension = os.path.splitext(os.path.basename(file_path))
    file_extension = file_extension.lower()

    # 2. Dynamically route extraction based on file extension
    if file_extension == '.pdf':
        text = pdf_extractor(file_path)
    elif file_extension in ['.xlsx', '.xls']:
        text = excel_extractor(file_path)
    else:
        print(f"Error: Unsupported file format {file_extension}")
        return [], []

    if not text:
        print(f"Error: No text could be extracted from {file_path}")
        return [], []

    print("Text Extracted. Parsing estimates via LLM...")

    estimates = process_estimate(text)

    # [ADD THIS DIAGNOSTIC BLOCK]
    print("\n" + "="*50)
    print(f"[DEBUG 2] ESTIMATES RETURNED BY GEMINI (Count: {len(estimates)}):")
    import json
    for i, est in enumerate(estimates):
        print(f"--- Estimate {i} ---")
        # Using json.dumps to force dict printing safely
        print(json.dumps(est, indent=2, default=str))
    print("="*50 + "\n")





    if not estimates:
        print("Error: No valid estimates identified in the document.")
        return [], []

    print(f"Discovered {len(estimates)} estimate(s).")

    # Track successes and failures separately for this specific PDF
    success_invoices = []
    failed_invoices = []

    # 2. Iterate over each estimate and execute the graph
    for index, estimate_data in enumerate(estimates):
        container_id = estimate_data.get("container_id", f"UNKNOWN_{index}")
        print(f"\n--- Initiating Graph for Container: {container_id} ---")

        unique_run_id = uuid.uuid4().hex[:8]
        thread_id = f"invoice-{file_name}-{container_id}-{unique_run_id}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "pdf_name": file_name,
            "data": estimate_data
        }

        result = app.invoke(initial_state, config=config)

        # Handle HITL interrupts
        while "__interrupt__" in result:
            question = result["__interrupt__"][0].value["message"]
            print(question)

            answer = input("Your answer: ")
            result = app.invoke(Command(resume=answer), config=config)

        # Categorize the output
        if "invoice" in result:
            inv = result["invoice"]
            has_failures = any(
                job.get("status") in ["unmapped", "skipped"]
                for job in inv.get("jobs", [])
            )

            # [OVERWRITE WITH THIS DIAGNOSTIC BLOCK]
            if has_failures:
                print(f"\n[DEBUG 3] Container {container_id} FAILED ROUTING.")
                print("Reason: One or more jobs had 'unmapped' or 'skipped' status.")
                for job in inv.get("jobs", []):
                    print(f"  -> Job ID {job.get('job_id')}: Status = {job.get('status')} | CMP: {job.get('component')} | RPR: {job.get('repair')}")
                failed_invoices.append(inv)
            else:
                print(f"\n[DEBUG 3] Container {container_id} SUCCESS ROUTING.")
                print(f"  -> All {len(inv.get('jobs', []))} jobs mapped successfully.")
                success_invoices.append(inv)

    # Return raw data to the main batch loop. Do NOT write to Excel here.
    return success_invoices, failed_invoices



def main():
    pdf_files = glob.glob(os.path.join(SAMPLES_DIR, "*.pdf")) + glob.glob(os.path.join(SAMPLES_DIR, "*.PDF"))
    excel_files = (
        glob.glob(os.path.join(SAMPLES_DIR, "*.xlsx")) +
        glob.glob(os.path.join(SAMPLES_DIR, "*.XLSX")) +
        glob.glob(os.path.join(SAMPLES_DIR, "*.xls")) +
        glob.glob(os.path.join(SAMPLES_DIR, "*.XLS"))
    )

    # FIX: Remove duplicates caused by Windows case-insensitivity
    all_files = pdf_files + excel_files

    # 2. Mathematically remove duplicate file paths caused by case-insensitive OS globs
    all_files = list(set(all_files))

    # 3. Strip out any hidden ~$ ghost files created by Windows/Excel
    all_files = [f for f in all_files if not os.path.basename(f).startswith("~$")]


    if not all_files:
        print(f"No valid documents found in '{SAMPLES_DIR}' folder.")
        return

    print(f"Found {len(all_files)} document(s) in '{SAMPLES_DIR}':")
    for f in all_files:
        print(" -", f)

    # ... rest of main() remains the same ...

    global_success = []
    global_failed = []

    for file_path in all_files:
        success, failed = process_single_document(file_path)
        global_success.extend(success)
        global_failed.extend(failed)

    # ... (Excel generation logic remains the same)

    # 4. Generate the final Excel files AFTER all PDFs are processed
    if global_success:
        output_path = os.path.join(BASE_DIR, "..", "data", "output", "MASTER_SUCCESS_COMBINED.xlsx")
        generate_excel_report(global_success, output_path=output_path)
        print(f"\nSUCCESS: Generated master successful report at {output_path}")

    if global_failed:
        output_path = os.path.join(BASE_DIR, "..", "data", "output", "MASTER_FAILED_DLQ.xlsx")
        generate_excel_report(global_failed, output_path=output_path)
        print(f"\nWARNING: Generated master failure/DLQ report at {output_path}")

    print("\nAll files processed successfully!")
if __name__ == "__main__":
    main()