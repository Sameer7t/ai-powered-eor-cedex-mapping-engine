# AI-Powered EOR Processing & CEDEX Mapping Engine

An AI-assisted logistics document-processing pipeline that extracts structured repair data from container Estimate of Repair (EOR) documents and standardizes it into CEDEX/ISO-aligned codes.

> **Portfolio edition:** This repository contains source code and non-confidential mapping resources only. Customer documents, API credentials, proprietary reference workbooks, caches, and generated reports are intentionally excluded.

## What it does

- Ingests container repair estimates in PDF and Excel formats.
- Uses the Gemini API and Pydantic schemas to turn unstructured repair information into validated records.
- Classifies normal and special repair jobs, including dry-container and tank-container workflows.
- Maps inconsistent damage, component, repair, and location descriptions to CEDEX/ISO codes.
- Supports human-in-the-loop correction and persists approved mapping decisions locally.
- Produces separate Excel reports for successfully mapped records and records requiring review.

## Workflow

```text
EOR PDF / Excel
       |
       v
Text extraction -> Gemini structured extraction -> validation
       |
       v
Job classification -> CEDEX/ISO mapping -> human review when needed
       |
       v
Success report (.xlsx) + review/DLQ report (.xlsx)
```

## Repository layout

```text
src/                 Application source code and canonical mapping files
src/models/          Pydantic-related enums and domain models
src/mappings/        CEDEX mapping rules and locally learned mappings
data/                Locally supplied reference workbooks and generated output
samples/             Local EOR inputs; use only synthetic or redacted files
tests/               Automated regression tests
```

## Tech stack

Python, Gemini API, Pydantic, LangGraph, Pandas, NumPy, pdfplumber, and Openpyxl.

## Setup

Prerequisites: Python 3.12+ and a Gemini API key.

```powershell
git clone https://github.com/Sameer7t/ai-powered-eor-cedex-mapping-engine.git
cd ai-powered-eor-cedex-mapping-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Add your API key to `.env`:

```env
GEMINI_API_KEY=your_key_here
```

## Running the pipeline

1. Place only authorized, redacted, or synthetic EOR documents in `samples/`.
2. Supply the required local reference workbooks described in [`data/README.md`](data/README.md).
3. Run:

```powershell
python src/workflow.py
```

Generated reports are written to `data/output/` and are excluded from Git.

## Testing

Run the included deterministic regression test with:

```powershell
python -m unittest discover -s tests -v
```

## Data and privacy

This project was validated with real-world data, but no customer, depot, container, commercial, or API-key data is published in this repository. Do not commit files from `samples/`, `data/`, or `.env` unless they are explicitly cleared for public release.
