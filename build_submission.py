"""Builds the submission zip(s) from output/.

`output/` is produced by `python main.py` with config.CATEGORY_NAME_LANGUAGE
= "pt", i.e. product_context.category_names holds the raw
products.product_category_name value.

README §6 only ever shows the placeholder "<category_name>", so whether the
grader expects the Portuguese source value or the English value from
product_category_name_translation.csv is genuinely underspecified. Rather
than guess once and burn a submission, this script emits BOTH variants:

    output.zip              -> categories as-is in output/ (Portuguese)
    output_en_categories.zip -> same 50 cases, categories translated

category_names never passes through the LLM, and the pt->en mapping is 1:1
over every category present in these 50 cases (verified: no two Portuguese
categories collapse to one English name), so the translated variant is an
exact transform of the same run — no second Groq run is needed and no other
field changes.

Usage:
    python build_submission.py
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from src.config import OUTPUT_DIR, REPO_ROOT
from src.data.loader import load_data_store

EXPECTED = [f"EC_{i:03d}.json" for i in range(1, 51)]


def _read_outputs() -> list[tuple[str, dict]]:
    files = sorted(OUTPUT_DIR.glob("EC_*.json"))
    names = [f.name for f in files]
    if names != EXPECTED:
        raise SystemExit(f"expected exactly {EXPECTED[0]}..{EXPECTED[-1]}, found {len(names)}")
    return [(f.name, json.loads(f.read_text(encoding="utf-8"))) for f in files]


def _write_zip(path: Path, docs: list[tuple[str, dict]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("output/"), b"")
        for name, doc in docs:
            z.writestr(f"output/{name}", json.dumps(doc, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(path) as z:
        entries = [n for n in z.namelist() if n != "output/"]
        assert entries == [f"output/{n}" for n in EXPECTED], f"{path.name}: unexpected entries"
        assert z.testzip() is None, f"{path.name}: crc failure"
    print(f"{path.name}: 50 JSON, verified")


def main() -> None:
    docs = _read_outputs()
    _write_zip(REPO_ROOT / "output.zip", docs)

    ds = load_data_store(REPO_ROOT / "data")
    translated: list[tuple[str, dict]] = []
    for name, doc in docs:
        doc = json.loads(json.dumps(doc))  # deep copy
        names = doc["product_context"]["category_names"]
        mapped = [ds.translate_category(n) or n for n in names]
        if len(set(mapped)) != len(set(names)):
            raise SystemExit(f"{name}: pt->en collapses categories, transform unsafe")
        doc["product_context"]["category_names"] = mapped
        translated.append((name, doc))
    _write_zip(REPO_ROOT / "output_en_categories.zip", translated)


if __name__ == "__main__":
    main()
