# NeurIPS Dataset Hosting Checklist

This checklist is tailored for submitting LivePI through the NeurIPS
Evaluations & Datasets Track with Harvard Dataverse hosting.

## Before Upload

- Confirm the benchmark matrix still validates:

```bash
python3 prompt_injection_lab/scripts/audit_techniques.py
python3 prompt_injection_lab/scripts/audit_benchmark_matrix.py
python3 prompt_injection_lab/scripts/validate_tasks.py
```

- Confirm no local secrets or live traces are present:

```bash
rg -n "(s[k]-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|BEGIN [^-]*PRIVATE KEY)" .
```

- Build the clean release package:

```bash
python3 scripts/prepare_neurips_dataset_package.py --archive
```

## Harvard Dataverse

- Create a dataset in Harvard Dataverse.
- Fill Dataverse fields using `metadata/dataverse_metadata.md`.
- Upload the generated release archive from `dist/`.
- During review, make the dataset accessible through Dataverse Link Sharing or
  another reviewer-accessible URL.
- If accepted, make the dataset public by the camera-ready deadline.

## Croissant Metadata

- Export the Dataverse-generated Croissant metadata from the dataset page.
- Merge the NeurIPS Responsible AI fields:

```bash
python3 scripts/merge_croissant_rai.py \
  --input dataverse-croissant.json \
  --rai metadata/rai_metadata_livepi.json \
  --output livepi.croissant.json
```

- Validate `livepi.croissant.json` with the NeurIPS-linked Croissant
  validator.
- Upload the validated Croissant file to OpenReview.

## OpenReview Submission

NeurIPS requires both of the following for dataset submissions:

- A dataset URL accessible to reviewers.
- A validated Croissant metadata file containing core Croissant fields and the
  required Responsible AI fields.

## Final Manual Replacements

Before final public release, confirm these fields:

- `CITATION.cff`: final author list if anonymity is no longer required.
- `metadata/dataverse_metadata.md`: final author list and related publication
  if anonymity is no longer required.
- Dataverse record: title, author list, contact, description, keywords, license,
  related publication, and DOI.
