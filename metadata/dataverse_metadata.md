# Suggested Harvard Dataverse Metadata

Use these values for the Harvard Dataverse dataset record during anonymous
review.

## Citation Metadata

- Title: Live Prompt Injection benchmark (LivePI)
- Author: LivePI Authors
- Contact: Use the contact address configured in the Dataverse record.
- Description: Live Prompt Injection benchmark (LivePI) is an executable
  prompt-injection benchmark for tool-using AI agents in production-like
  environments. The paper-aligned matrix contains 169 executable cases per
  evaluated model over seven input surfaces, twelve attack-technique or
  rendering families, and five malicious objectives.
- Subject: Computer and Information Science
- Keywords: prompt injection; AI agents; tool use; agent safety; benchmark;
  indirect prompt injection; OpenClaw
- Related publication: Anonymous submission.
- Language: English
- Version: 2026.05.05

## License And Terms

- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Terms note: The artifact is for controlled safety evaluation. Users should run
  it only with accounts, credentials, wallet balances, and infrastructure that
  they own or are authorized to test.

## Recommended Files To Upload

Upload the release archive produced by:

```bash
python3 scripts/prepare_neurips_dataset_package.py --archive
```

The archive should include the benchmark code, task JSONL files, taxonomies,
synthetic fixture metadata, setup script, dataset card, citation metadata,
license files, and NeurIPS checklist. It should not include `.env`,
`secrets.env`, live results, caches, OAuth tokens, SSH keys, or generated
gateway identities.

## Croissant Workflow

After uploading to Dataverse, export the Dataverse-generated Croissant metadata:

1. Open the Dataverse dataset page.
2. Click Metadata.
3. Click Export Metadata.
4. Select Croissant.

Then merge the required NeurIPS RAI fields:

```bash
python3 scripts/merge_croissant_rai.py \
  --input dataverse-croissant.json \
  --rai metadata/rai_metadata_livepi.json \
  --output livepi.croissant.json
```

Validate `livepi.croissant.json` with the NeurIPS-linked Croissant
validator before uploading it to OpenReview.
