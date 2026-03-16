# Litigation Intelligence Prototype

Automated ingestion pipeline for U.S. court filings.

**Jurisdiction:** Southern District of New York (SDNY)  
**Data source:** [CourtListener](https://www.courtlistener.com/) REST API v3

---

## Architecture

```
CourtListener Poller (scripts/poll_courtlistener.py)
        ↓
  Docket Detection (app/ingestion/courtlistener.py)
        ↓
  PDF Download & Text Extraction (app/processing/pdf_extractor.py)
        ↓
  OCR Fallback — Tesseract (app/processing/pdf_extractor.py)
        ↓
  Entity Extraction (app/extraction/entities.py)
        ↓
  AI Summary — BART-large-CNN (app/summarization/summarizer.py)
        ↓
  PostgreSQL (app/storage/models.py)
        ↓
  Django REST API (app/api/)
```

The **poller runs as a separate process** from the Django API server.  
This separation keeps the API responsive and makes the workers trivially scalable.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| PostgreSQL | 14+ |
| Tesseract OCR | 5+ |
| Poppler (pdf2image) | System package |

### Install system dependencies

**macOS:**
```bash
brew install tesseract poppler
```

**Ubuntu / Debian:**
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

---

## Quickstart

### 1. Clone and set up virtual environment
```bash
git clone <repo-url>
cd litigation-intelligence
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
```

Edit `.env`:

```env
DJANGO_SECRET_KEY=your-secret-key-here
DB_NAME=litigation_db
DB_USER=litigation_user
DB_PASSWORD=litigation_pass
DB_HOST=localhost
DB_PORT=5432

# Get a free token at https://www.courtlistener.com/sign-in/
COURTLISTENER_API_TOKEN=your_token_here
TARGET_COURT=nysd       # SDNY code on CourtListener
POLL_INTERVAL_SECONDS=300
```

### 3. Set up the database
```bash
createdb litigation_db
createuser litigation_user
psql -c "ALTER USER litigation_user WITH PASSWORD 'litigation_pass';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE litigation_db TO litigation_user;"

python manage.py migrate
```

### 4. Start the Django API server
```bash
python manage.py runserver
```

The API is available at http://localhost:8000/api/

### 5. Start the poller worker (separate terminal)
```bash
python scripts/poll_courtlistener.py
```

---

## API Reference

### `GET /api/filings/latest`
Returns the most recently ingested filings.

**Query params:**  
`limit` — number of results (default 20, max 100)

**Example response:**
```json
[
  {
    "id": 1,
    "docket_id": "12345",
    "court": "nysd",
    "court_name": "S.D.N.Y.",
    "court_full_name": "District Court, Southern District of New York",
    "court_citation": "S.D.N.Y.",
    "case_name": "Smith v. Acme Corp",
    "plaintiff": "John Smith",
    "defendant": "Acme Corp",
    "summary": "Plaintiff alleges breach of an employment contract and seeks damages related to wrongful termination.",
    "pdf_path": "data/filings/12345.pdf",
    "date_filed": "2024-01-15",
    "created_at": "2024-01-15T14:32:00Z",
    "updated_at": "2024-01-15T14:32:00Z"
  }
]
```

### `GET /api/filings/<docket_id>/`
Returns a single filing by CourtListener docket ID.

### `GET /api/ingestion/logs/`
Returns recent ingestion log entries (success/error/skipped).

### `GET /api/health/`
Health check endpoint.

---

## Directory Structure

```
litigation-intelligence/
├── app/
│   ├── api/              # Django REST Framework views, serializers, URLs
│   ├── ingestion/        # CourtListener API client
│   ├── processing/       # PDF text extraction + OCR fallback
│   ├── extraction/       # Plaintiff/defendant entity extraction
│   ├── summarization/    # HuggingFace BART summarizer
│   └── storage/          # Django models, migrations, repository layer
├── config/               # Django settings and root URL config
├── data/
│   └── filings/          # Downloaded PDFs (gitignored)
├── scripts/
│   └── poll_courtlistener.py   # Standalone poller worker
├── .env.example
├── manage.py
├── requirements.txt
└── README.md
```

---

## Future Scalability

The architecture is designed to scale incrementally:

| Capability | Upgrade path |
|---|---|
| Multiple workers | Celery + Redis |
| Multi-jurisdiction | Add courts to TARGET_COURT env list |
| Semantic search | pgvector / Pinecone + embedding pipeline |
| Richer NLP | spaCy NER or fine-tuned legal NER model |
| Production DB | Managed PostgreSQL (AWS RDS / Supabase) |

---

## Notes on CourtListener API

- A **free API token** is required. Register at https://www.courtlistener.com/sign-in/
- The SDNY court code on CourtListener is **`nysd`**
- RECAP documents are only available for cases where the filing has been uploaded by RECAP users
- The API rate-limits unauthenticated requests; always use a token

---

## Example Demonstration Output

```
2024-01-15 14:32:01 [INFO] poller — Polling CourtListener for new nysd dockets…
2024-01-15 14:32:02 [INFO] poller — Found 1 docket(s).
2024-01-15 14:32:02 [INFO] poller — ────────────────────────────────────────────────────────────
2024-01-15 14:32:02 [INFO] poller — New Filing Detected
2024-01-15 14:32:02 [INFO] poller —   Court    : nysd
2024-01-15 14:32:02 [INFO] poller —   Case     : Smith v. Acme Corp
2024-01-15 14:32:02 [INFO] poller —   Docket ID: 12345
2024-01-15 14:32:04 [INFO] poller —   Plaintiff: John Smith
2024-01-15 14:32:04 [INFO] poller —   Defendant: Acme Corp
2024-01-15 14:32:06 [INFO] poller —   Summary  : Plaintiff alleges breach of an employment contract…
2024-01-15 14:32:06 [INFO] poller —   ✓ Saved to database.
```
