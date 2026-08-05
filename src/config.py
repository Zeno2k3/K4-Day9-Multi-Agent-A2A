"""Runtime configuration: model name, tolerances, and schema array limits.

Model name is declared here (in code) per README §9.4, and mirrored into
logging/metadata.json at the end of a run.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- LLM backend -----------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL_PARAM_SIZE = "8B"  # llama-3.1-8b-instant, satisfies README §9.1 (<=10B per agent)

LLM_TIMEOUT_SECONDS = 20
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY_SECONDS = 1.0
LLM_MIN_INTERVAL_SECONDS = 0.15  # light client-side pacing to avoid bursty 429s

# --- Business policy constants (EC_POLICY_V2, README §4) -------------------
POLICY_VERSION = "EC_POLICY_V2"
RECONCILE_TOLERANCE_BRL = 0.10
RECONCILE_TOLERANCE_CENTS = 10

# --- Output schema array limits (README §6) ---------------------------------
MAX_ORDER_IDS = 5
MAX_ITEM_IDS = 5
MAX_SELLER_IDS = 3
MAX_PAYMENT_IDS = 5
MAX_RELATED_ORDER_IDS = 5
MAX_PRODUCT_IDS = 5
MAX_CATEGORY_NAMES = 5
MAX_ROOT_CAUSES = 3
MAX_RESPONSIBLE_PARTIES = 3
MAX_EVIDENCE_IDS = 20
MAX_RESOLUTION_ACTIONS = 5

# --- Paths -------------------------------------------------------------------
DATA_DIR = REPO_ROOT / "data"
INPUT_DIR = REPO_ROOT / "input"
OUTPUT_DIR = REPO_ROOT / "output"
TRACE_PATH = REPO_ROOT / "logging" / "trace.jsonl"
METADATA_PATH = REPO_ROOT / "logging" / "metadata.json"
