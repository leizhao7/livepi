#!/usr/bin/env python3
"""Merge LivePI RAI metadata into a Dataverse Croissant export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_RAI_FIELDS = (
    "rai:dataLimitations",
    "rai:dataBiases",
    "rai:personalSensitiveInformation",
    "rai:dataUseCases",
    "rai:dataSocialImpact",
    "rai:hasSyntheticData",
    "prov:wasDerivedFrom",
    "prov:wasGeneratedBy",
)

CONTEXT_PATCH = {
    "cr": "http://mlcommons.org/croissant/",
    "dct": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "sc": "https://schema.org/",
}

RAI_SPEC = "http://mlcommons.org/croissant/RAI/1.0"
RELEASE_ARCHIVE_ID = "livepi_neurips_dataset.tar.gz"


def _field(field_id: str, name: str, data_type: str, description: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "@type": "cr:Field",
        "@id": field_id,
        "name": name,
        "dataType": data_type,
        "description": description,
        "source": source,
    }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _merge_context(doc: dict[str, Any], patch: dict[str, Any]) -> None:
    context = doc.get("@context")
    if context is None:
        doc["@context"] = dict(patch)
        return
    if isinstance(context, dict):
        for key, value in patch.items():
            context.setdefault(key, value)
        return
    if isinstance(context, list):
        existing_keys: set[str] = set()
        for item in context:
            if isinstance(item, dict):
                existing_keys.update(item.keys())
        missing = {k: v for k, v in patch.items() if k not in existing_keys}
        if missing:
            context.append(missing)
        return
    raise TypeError("@context must be an object, list, or absent")


def _ensure_conforms_to(doc: dict[str, Any], rai: dict[str, Any]) -> None:
    values: list[Any] = []
    for key in ("dct:conformsTo", "conformsTo"):
        raw = doc.get(key)
        if raw is None:
            continue
        if isinstance(raw, list):
            values.extend(raw)
        else:
            values.append(raw)
    raw_rai = rai.get("dct:conformsTo")
    if isinstance(raw_rai, list):
        values.extend(raw_rai)
    elif raw_rai:
        values.append(raw_rai)
    if RAI_SPEC not in values:
        values.append(RAI_SPEC)

    deduped: list[Any] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    doc["dct:conformsTo"] = deduped if len(deduped) > 1 else deduped[0]


def _ensure_livepi_structure(doc: dict[str, Any]) -> None:
    """Add lightweight structure metadata Dataverse does not infer for archives."""
    distribution = doc.setdefault("distribution", [])
    if isinstance(distribution, dict):
        distribution = [distribution]
        doc["distribution"] = distribution
    if not isinstance(distribution, list):
        raise TypeError("distribution must be an object, list, or absent")

    distribution_ids = {
        item.get("@id")
        for item in distribution
        if isinstance(item, dict)
    }
    archive_present = RELEASE_ARCHIVE_ID in distribution_ids
    file_sets = [
        {
            "@type": "cr:FileSet",
            "@id": "livepi_task_jsonl_files",
            "name": "LivePI task JSONL files",
            "description": "Executable benchmark task definitions inside the release archive.",
            "containedIn": {"@id": RELEASE_ARCHIVE_ID},
            "includes": "livepi_neurips_dataset/prompt_injection_lab/tasks/**/*.jsonl",
            "encodingFormat": "application/jsonlines",
        },
        {
            "@type": "cr:FileSet",
            "@id": "livepi_taxonomy_json_files",
            "name": "LivePI taxonomy JSON files",
            "description": "Surface, technique, objective, and case-matrix definitions inside the release archive.",
            "containedIn": {"@id": RELEASE_ARCHIVE_ID},
            "includes": "livepi_neurips_dataset/prompt_injection_lab/taxonomy/*.json",
            "encodingFormat": "application/json",
        },
    ]
    if archive_present:
        for file_set in file_sets:
            if file_set["@id"] not in distribution_ids:
                distribution.append(file_set)
                distribution_ids.add(file_set["@id"])

    record_sets = doc.setdefault("recordSet", [])
    if isinstance(record_sets, dict):
        record_sets = [record_sets]
        doc["recordSet"] = record_sets
    if not isinstance(record_sets, list):
        raise TypeError("recordSet must be an object, list, or absent")
    record_set_ids = {
        item.get("@id")
        for item in record_sets
        if isinstance(item, dict)
    }
    if "livepi_benchmark_cases" not in record_set_ids:
        task_source = lambda key: {
            "fileSet": {"@id": "livepi_task_jsonl_files"},
            "extract": {"jsonPath": f"$.{key}"},
        }
        record_sets.append({
            "@type": "cr:RecordSet",
            "@id": "livepi_benchmark_cases",
            "name": "LivePI benchmark cases",
            "description": (
                "Task-level records defining the input surface, injection technique, "
                "malicious objective, prompts, environment requirements, and verifier "
                "configuration for the paper-aligned benchmark matrix."
            ),
            "field": [
                _field("livepi_benchmark_cases/task_id", "task_id", "sc:Text", "Stable task identifier.", task_source("task_id")),
                _field("livepi_benchmark_cases/surface", "surface", "sc:Text", "Input surface or surface group.", task_source("surface")),
                _field("livepi_benchmark_cases/technique", "technique", "sc:Text", "Attack technique or rendering family.", task_source("technique")),
                _field("livepi_benchmark_cases/objective", "objective", "sc:Text", "Malicious objective evaluated by the task.", task_source("objective")),
                _field("livepi_benchmark_cases/prompt", "prompt", "sc:Text", "Benign user-facing task prompt or task setup text.", task_source("prompt")),
                _field("livepi_benchmark_cases/verifier", "verifier", "sc:Text", "Verifier configuration used to check the task outcome.", task_source("verifier")),
            ],
        })

    if "livepi_taxonomy" not in record_set_ids:
        taxonomy_source = lambda key: {
            "fileSet": {"@id": "livepi_taxonomy_json_files"},
            "extract": {"jsonPath": f"$.{key}"},
        }
        record_sets.append({
            "@type": "cr:RecordSet",
            "@id": "livepi_taxonomy",
            "name": "LivePI taxonomy",
            "description": (
                "Machine-readable definitions for benchmark surfaces, injection "
                "techniques, objectives, and the feasible case matrix."
            ),
            "field": [
                _field("livepi_taxonomy/name", "name", "sc:Text", "Surface, technique, objective, or case-matrix entry name.", taxonomy_source("name")),
                _field("livepi_taxonomy/id", "id", "sc:Text", "Machine-readable identifier when present.", taxonomy_source("id")),
                _field("livepi_taxonomy/description", "description", "sc:Text", "Human-readable definition or summary.", taxonomy_source("description")),
            ],
        })

    if "livepi_summary" not in record_set_ids:
        record_sets.append({
            "@type": "cr:RecordSet",
            "@id": "livepi_summary",
            "name": "LivePI benchmark summary",
            "description": "Constant summary fields for the released benchmark matrix.",
            "field": [
                {
                    "@type": "cr:Field",
                    "@id": "livepi_summary/cases_per_model",
                    "name": "cases_per_model",
                    "dataType": "sc:Integer",
                    "description": "Number of executable paper-aligned cases per evaluated model.",
                    "value": 169,
                },
                {
                    "@type": "cr:Field",
                    "@id": "livepi_summary/surface_count",
                    "name": "surface_count",
                    "dataType": "sc:Integer",
                    "description": "Number of benchmark input surfaces.",
                    "value": 7,
                },
                {
                    "@type": "cr:Field",
                    "@id": "livepi_summary/technique_family_count",
                    "name": "technique_family_count",
                    "dataType": "sc:Integer",
                    "description": "Number of attack-technique or rendering families.",
                    "value": 12,
                },
                {
                    "@type": "cr:Field",
                    "@id": "livepi_summary/objective_count",
                    "name": "objective_count",
                    "dataType": "sc:Integer",
                    "description": "Number of malicious objectives.",
                    "value": 5,
                },
            ],
        })


def merge_croissant_rai(croissant: dict[str, Any], rai: dict[str, Any]) -> dict[str, Any]:
    merged = dict(croissant)
    _merge_context(merged, CONTEXT_PATCH)
    _ensure_conforms_to(merged, rai)

    for field in REQUIRED_RAI_FIELDS:
        if field not in rai:
            raise KeyError(f"RAI metadata is missing required field: {field}")
        merged[field] = rai[field]

    for optional_field in (
        "rai:dataCollection",
        "rai:dataCollectionRawData",
        "rai:dataCollectionType",
        "rai:dataPreprocessingProtocol",
        "rai:dataAnnotationProtocol",
    ):
        if optional_field in rai:
            merged[optional_field] = rai[optional_field]

    _ensure_livepi_structure(merged)

    missing = [field for field in REQUIRED_RAI_FIELDS if field not in merged]
    if missing:
        raise RuntimeError(f"merged Croissant is missing required fields: {missing}")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Dataverse Croissant JSON export")
    parser.add_argument("--rai", required=True, type=Path, help="LivePI RAI metadata JSON")
    parser.add_argument("--output", required=True, type=Path, help="Merged Croissant JSON output")
    args = parser.parse_args()

    croissant = _load_json(args.input)
    rai = _load_json(args.rai)
    merged = merge_croissant_rai(croissant, rai)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote merged Croissant metadata to {args.output}")
    print("Required NeurIPS RAI fields present:")
    for field in REQUIRED_RAI_FIELDS:
        print(f"  - {field}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
