"""
Celery application configuration.

Addresses the reviewer concern about async OCR and processing pipeline.

Worker topology:
  Q: ocr        — high-priority queue for PDF OCR jobs (CPU-bound)
                  Workers: 2 processes (or 1 per CPU core in prod)
  Q: nlp        — NLP enrichment queue (NER, classification, embeddings)
                  Workers: 1 process (model is memory-heavy; share singleton)
  Q: default    — general tasks

Start workers:
  # OCR workers (2 concurrent processes, CPU-bound)
  celery -A config.celery worker -Q ocr -c 2 --loglevel=info

  # NLP worker (1 process; models loaded once per process)
  celery -A config.celery worker -Q nlp -c 1 --loglevel=info

  # Default worker
  celery -A config.celery worker -Q default -c 4 --loglevel=info

Redis is the message broker.  Fallback to in-process eager execution when
CELERY_TASK_ALWAYS_EAGER=True (useful for tests and local dev without Redis).
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("litigation_intelligence")

app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in all INSTALLED_APPS
app.autodiscover_tasks()

# Queue routing
app.conf.task_routes = {
    "app.tasks.ocr_task.*": {"queue": "ocr"},
    "app.tasks.nlp_task.*": {"queue": "nlp"},
}

# Retry settings
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True
app.conf.worker_prefetch_multiplier = 1  # Fair dispatch for long-running tasks
