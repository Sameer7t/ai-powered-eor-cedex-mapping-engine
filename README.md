# AI-Powered EOR Processing & CEDEX Mapping Engine

An AI-assisted logistics document-processing pipeline and web service that extracts structured repair data from container Estimate of Repair (EOR) documents and standardizes it into CEDEX/ISO-aligned industry codes (ISO 9897 / ISO 6346).

> **Live & Cloud Ready:** Features a modern interactive web dashboard, FastAPI REST API, LangGraph Human-in-the-Loop review, containerized Docker runtime, and turnkey Render cloud deployment.

---

## Highlights

- **Dual Container Routing:** Intelligently routes **Tank Containers (22K1, IMO 1/2/3)** through Gemini-powered classification and **Dry Cargo Containers (22G1, 42G1, 45G1, 40HC)** through a multilingual CEDEX rule-engine.
- **Multilingual Vocabulary Parsing:** Normalizes repair and damage terminology across English, Turkish, and Russian.
- **4-Tuple CEDEX Code Assembly:** Produces standardized `LOCATION` (LOCN), `COMPONENT` (CMP), `REPAIR` (RPR), and `DAMAGE` (DMG) tuples.
- **Human-in-the-Loop Active Learning:** Flags low-confidence or ambiguous repairs for manual human verification and persists approved mappings to route-specific memory JSON files.
- **Dual Excel Reporting:** Automatically generates clean `MASTER_SUCCESS_COMBINED.xlsx` workbooks and segregates unresolved rows into `MASTER_FAILED_DLQ.xlsx` (Dead Letter Queue).
- **Embedded Web UI & Cloud API:** Interactive browser interface with drag-and-drop file upload, live metrics, 1-click synthetic demo sandboxes, and FastAPI Swagger documentation.

---

## System Architecture

```text
               EOR Document (PDF / Excel)
                          │
                          ▼
            Text Extraction & Layout Parsing
            (pdfplumber / openpyxl / pandas)
                          │
                          ▼
               Gemini 3.5 LLM Parsing
            (Strict Pydantic JSON Schemas)
                          │
                          ▼
               Container Route Classifier
                     ┌────┴────┐
                     ▼         ▼
               Tank Pipeline  Dry Pipeline
               (Gemini + TN)  (Rule-Engine + GP)
                     └────┬────┘
                          ▼
             4-Tuple CEDEX Standardization
                          │
                          ▼
               Confidence Scoring Engine
                     ┌────┴────┐
                     ▼         ▼
                High (≥0.75)  Low / Unmapped
                     │         │
                     │         ▼
                     │    Human-in-the-Loop
                     │    (Active Memory Save)
                     └────┬────┘
                          ▼
        Standardized Container Invoices & Reports
     ┌────────────────────┴────────────────────┐
     ▼                                         ▼
Master Success Report (.xlsx)       Dead Letter Queue / Review (.xlsx)
```

---

## Tech Stack

- **Backend & AI:** Python 3.12, Google GenAI SDK (`gemini-3.5-flash-lite`), LangGraph, Pydantic v2.
- **Web API & Server:** FastAPI, Uvicorn, Python-Multipart.
- **Data & Documents:** Pandas, NumPy, OpenPyXL, pdfplumber.
- **Deployment & Cloud:** Docker, Render Blueprint (`render.yaml`), GitHub Actions ready.

---

## Getting Started Locally

### Prerequisites
- Python 3.12+
- Gemini API key (from [Google AI Studio](https://aistudio.google.com/))

### 1. Clone & Install Dependencies

```powershell
git clone https://github.com/Sameer7t/ai-powered-eor-cedex-mapping-engine.git
cd ai-powered-eor-cedex-mapping-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set your API key in `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
PORT=8000
```

### 2. Launch the Web Application

```powershell
python -m uvicorn src.server:app --reload --port 8000
```

Open your browser to:
- **Interactive Web Dashboard:** `http://localhost:8000`
- **Swagger API Docs:** `http://localhost:8000/docs`

### 3. Run Deterministic Test Suite

```powershell
python -m unittest discover -s tests -v
```

---

## Deploying to Render

This repository includes a production `Dockerfile` and a `render.yaml` Blueprint specification for zero-friction cloud deployment.

### Option A: 1-Click Blueprint Deploy (Recommended)
1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com/), click **New +** > **Blueprint**.
3. Connect your GitHub repository: `Sameer7t/ai-powered-eor-cedex-mapping-engine`.
4. Render automatically reads `render.yaml` and configures the Web Service.
5. In the environment variables prompt, enter your `GEMINI_API_KEY`.
6. Click **Apply** — Render builds the container and gives you a public HTTPS URL!

### Option B: Manual Web Service Deploy
1. Click **New +** > **Web Service**.
2. Select your repository.
3. Choose **Docker** as the runtime.
4. Set Environment Variables:
   - `PORT`: `8000`
   - `GEMINI_API_KEY`: `your_key_here`
5. Click **Create Web Service**.

---

## Docker Local Testing

To build and run the production container locally:

```bash
docker build -t eor-cedex-engine .
docker run -p 8000:8000 -e GEMINI_API_KEY=your_key_here eor-cedex-engine
```

---

## Repository Structure

```text
├── Dockerfile                  # Production container definition
├── render.yaml                 # Render Blueprint configuration
├── requirements.txt            # Python dependencies
├── src/
│   ├── server.py               # FastAPI web server and REST API
│   ├── engine_service.py       # High-level EOR processing pipeline
│   ├── data_loader.py          # Cross-platform data loader with fallback
│   ├── ai_client.py            # Lazy Gemini client helper
│   ├── workflow.py             # LangGraph batch pipeline
│   ├── cedex_mapping.py        # Tank CEDEX code mapper
│   ├── dry_processing.py       # Dry container rule engine
│   ├── cedex_converter.py      # Multilingual vocabulary parser
│   ├── custom_maping_by_human.py # Human active learning memory
│   ├── excel_report.py         # Formatted Excel report generator
│   ├── mappings/               # Learned mapping JSONs & reference cache
│   └── static/                 # Modern web dashboard (HTML, CSS, JS)
├── data/                       # Local operational workbooks and output
├── samples/                    # Redacted / synthetic test workbooks
└── tests/                      # Automated unit and API test suite
```

---

## Data & Privacy

Customer documents, API keys, operational workbooks, and generated customer reports are strictly excluded from source control via `.gitignore`. The repository includes synthetic test samples and bundled standard ISO/CEDEX definitions for seamless standalone execution.
