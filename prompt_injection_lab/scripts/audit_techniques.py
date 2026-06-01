#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from prompt_injection_lab.prompt_builder import supported_technique_tags  # noqa: E402
from prompt_injection_lab.technique_runtime import supported_profile_tags  # noqa: E402


def main() -> int:
    tech = json.loads((LAB_ROOT / "taxonomy" / "injection_techniques.json").read_text(encoding="utf-8"))
    catalog = json.loads(
        (LAB_ROOT / "taxonomy" / "injection_techniques_catalog.json").read_text(encoding="utf-8")
    )
    profiles = json.loads((LAB_ROOT / "taxonomy" / "technique_profiles.json").read_text(encoding="utf-8"))

    taxonomy_tags = {entry["tag"] for entry in tech["tags"]}
    builder_tags = set(supported_technique_tags())
    profile_tags = set(supported_profile_tags())

    catalog_entries = {}
    for sec in ("classic", "recent_powerful", "all_tags"):
        for row in catalog.get(sec, []):
            catalog_entries[row["tag"]] = row

    errors: list[str] = []

    missing_in_builder = sorted(taxonomy_tags - builder_tags)
    if missing_in_builder:
        errors.append(f"Missing in prompt_builder: {missing_in_builder}")

    missing_in_profiles = sorted(taxonomy_tags - profile_tags)
    if missing_in_profiles:
        errors.append(f"Missing in technique_profiles runtime: {missing_in_profiles}")

    missing_in_catalog = sorted(taxonomy_tags - set(catalog_entries.keys()))
    if missing_in_catalog:
        errors.append(f"Missing in catalog entries: {missing_in_catalog}")

    for tag in sorted(taxonomy_tags):
        if tag not in profiles["profiles"]:
            continue
        src_ids = profiles["profiles"][tag].get("source_ids", [])
        if not src_ids:
            errors.append(f"{tag}: no source_ids in technique_profiles")
            continue
        for source_id in src_ids:
            if source_id not in profiles["sources"]:
                errors.append(f"{tag}: source_id missing in technique_profiles.sources: {source_id}")
            if source_id not in catalog.get("sources", {}):
                errors.append(f"{tag}: source_id missing in catalog.sources: {source_id}")
        cat_src = catalog_entries.get(tag, {}).get("source_ids", [])
        if set(cat_src) != set(src_ids):
            errors.append(f"{tag}: catalog source_ids mismatch vs technique_profiles")

    if errors:
        print("Technique audit failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"Technique audit passed for {len(taxonomy_tags)} tags.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
