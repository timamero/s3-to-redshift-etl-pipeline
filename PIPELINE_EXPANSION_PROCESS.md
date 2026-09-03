# Process Document: FHIR Pipeline Expansion WIP

## Revision History

| Date       | Phase | Change                                                                                                                                                                                                                            |
| ---------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-28 | —     | Initial document created                                                                                                                                                                                                          |
| 2026-07-31 | 1     | Update steps                                                                                                                                                                                                                      |
| 2026-08-02 | 1     | Add error handling step to boto3 upload script                                                                                                                                                                                    |
| 2026-08-12 | 1     | Remove confirmation outcome to infer schema with Glue Crawler                                                                                                                                                                     |
| 2026-08-12 | 2     | Update steps to explicitly define schemas and flattening logic for each FHIR resource type                                                                                                                                        |
| 2026-08-27 | 2     | Update steps to include creation of inline policies for IAM roles                                                                                                                                                                 |
| 2026-08-27 | 3     | Update steps to include quality checks for nulls and duplicates in key fields, and to write each dataset to a separate staging location in S3                                                                                     |
| 2026-09-03 | 2, 3  | Update steps for setting and updating Redshift target nodes to use Direct data connection rather than Glue Data Catalog tables, based on the earlier finding that Catalog-routed writes can persist stale/incorrect type mappings |

## Purpose

This document records the process for expanding the S3-to-Redshift ETL pipeline from its current dummy-data validation state to a pipeline that ingests, transforms, and loads real synthetic FHIR data, with automated orchestration. It is intended to be a repeatable reference — for this project and as a template for similar AWS data pipeline work — so that configuration steps, service dependencies, and resolved issues are not lost between work sessions.

This is a living document. See **How to Maintain This Document** at the end for how to add to it as work proceeds.

## Starting Point

The pipeline currently consists of validated infrastructure and a working end-to-end connectivity spike using dummy data. This section summarizes what exists; a fully detailed account of how it was built is maintained separately.

**Detailed infrastructure setup process:** `[link placeholder — docs/infrastructure-setup-process.md]`

**Summary of current state:**

- Default VPC confirmed; self-referencing security group created for Glue/Redshift traffic on port 5439
- S3 Gateway VPC endpoint created for private S3 access; Interface VPC endpoints created for STS and Secrets Manager (required for Glue to assume its role and retrieve Redshift credentials from within the VPC)
- IAM user created for local boto3 access, scoped to the bronze S3 bucket
- IAM role created for Glue, with least-privilege access to S3 (bronze read, staging read/write/delete), the Glue Data Catalog, and Secrets Manager
- Redshift Serverless namespace and workgroup created, with admin credentials managed in Secrets Manager and an associated IAM role for S3 read access (required for `COPY`)
- S3 lifecycle rule configured to expire `/staging` objects after two days
- A Glue Connection to Redshift created and validated (`Test connection` successful)
- A Glue Crawler, Glue Data Catalog database/table, and a Glue ETL job successfully moved a dummy CSV from S3 through Glue into a Redshift target table, confirming the full path works end to end

**Known limitation of the current state:** the Glue ETL job's transformation logic is trivial (a type cast and a column rename) and does not yet reflect real-world data complexity. The phases below extend this same infrastructure to handle nested, multi-resource-type FHIR data.

## Phase Overview

| Phase      | Goal                                                                                         | Depends on                                   |
| ---------- | -------------------------------------------------------------------------------------------- | -------------------------------------------- |
| 1          | Ingest real Synthea FHIR data into the bronze bucket via a local boto3 script                | Starting point infrastructure                |
| 2          | Extend the Glue ETL job with FHIR-specific flattening logic                                  | Phase 1                                      |
| 3          | Expand Redshift schema to the full target model (Patient, Encounter, Condition, Observation) | Phase 2                                      |
| 4          | Validate the full pipeline end to end with real FHIR data                                    | Phases 1-3                                   |
| 5          | Automate the pipeline with EventBridge                                                       | Phase 4 must be successfully completed first |
| 6 (future) | Evolve ingestion from batch toward stream processing                                         | Phase 5                                      |

Phase 5 is deliberately sequenced after Phase 4, not in parallel — automating a pipeline whose transformation logic isn't yet proven against real data risks automating a broken process. Confirm Phases 1-3 produce correct, validated data in Redshift before adding orchestration on top.

---

## Phase 1: FHIR Ingestion via boto3

**Goal:** Replace the dummy CSV with real Synthea FHIR Bundles, uploaded to the bronze bucket via a local Python script.

**Steps:**

1. Generate or download a small Synthea FHIR dataset (start with a handful of patients, matching the scale used in earlier prototyping — see the companion Databricks project for this same starting-small approach).
2. Install boto3 and configure AWS credentials.
3. Create a test boto3 script to upload a test file to the S3 bucket to ensure credentials are correctly configured and IAM user has the correct policies.
4. Write a boto3 script that uploads each Bundle file to the bronze bucket under a dedicated prefix (e.g., `raw/fhir/`), using the existing IAM user's credentials.
5. Confirm the existing bronze-read IAM policy (bucket-wide wildcard) covers the new prefix without modification.
6. Run the script and verify file counts in S3 match the source dataset.
7. Add error handling that will log any failed uploads and continue with the next file, so a single failure doesn't block the entire dataset.

**Outcome to confirm before moving to Phase 2:** raw FHIR Bundles are present in the bronze bucket.

---

## Phase 2: Glue ETL Extension for FHIR

**Goal:** Replace the trivial transform logic with real FHIR flattening, producing four clean datasets: Patient, Encounter, Condition, Observation.

**Deviation:** The Glue Crawler is not needed because the inferred schema would conflict across resource types. Use a defined schema in the Glue Job instead of the Crawler's schema.

**Steps:**

1. Add inline policy for `iam:PassRole` to the Glue job's IAM role, so it can pass itself to AWS Glue when running the job. This is required to guardrail the job's permissions and avoid using a broader role than necessary.
2. Create the Glue ETL job notebook.
3. In the Glue ETL job, add logic to:
   - Define the schemas for each `resourceType` (Patient, Encounter, Condition, Observation)
   - Filter/split by `resourceType`
   - Flatten nested fields per resource type (e.g., `name`, `address` for Patient)
   - Parse FHIR `reference` fields (e.g., `urn:uuid:abc-123`) into plain join keys
   - Resolve Observation's multi-shape value fields (`valueQuantity`, `valueString`, `valueCodeableConcept`) into a single value column
   - Check for unexpected nulls in key fields and duplicate IDs, logging the count of each to confirm data quality
   - Cast date and timestamp fields to the correct Redshift-compatible types, and log any parsing errors
   - Write each flattened dataset to a separate staging location in S3 (e.g., `staging/patient/`, `staging/encounter/`, etc.) in Parquet format, with a single file per dataset for simplicity
4. Run the job against a small sample first; confirm output before scaling to a larger dataset.

**Outcome to confirm before moving to Phase 3:** four flattened datasets are produced with correct types and no unresolved nulls in key fields.

---

## Phase 3: Redshift Schema Expansion

**Goal:** Expand the single dummy target table into four tables matching the flattened FHIR datasets.

**Steps:**

1. Drop the dummy `employees` table (or leave it in place under a clearly separate name, if still needed for reference).
2. Create `patients`, `encounters`, `conditions`, and `observations` tables via DDL, with explicit column types (not auto-generated) — see the companion Databricks project's Delta table schema for the target field list to mirror.
3. Set the Redshift target node(s) to use **Direct data connection** rather than Glue Data Catalog tables, based on the earlier finding that Catalog-routed writes can persist stale/incorrect type mappings.
4. Update the Glue ETL job's Redshift target nodes to point at the correct table per dataset.
5. Run the job and confirm data lands in all four tables with the expected row counts.

**Outcome to confirm before moving to Phase 4:** all four Redshift tables are populated and queryable.

---

## Phase 4: End-to-End Validation

**Goal:** Confirm the full pipeline (S3 → Glue → Redshift) produces correct, joinable data before adding automation.

**Steps:**

1. Run referential integrity checks (e.g., every `encounter.patient_id` resolves to a row in `patients`) — expect 0 orphaned rows.
2. Run an analytical query joining across tables (e.g., condition counts by gender) to confirm the data is usable, not just present.
3. Document any data quality issues found and how they were resolved (see issue log format below).

**This phase is a gate, not a checkbox.** Do not proceed to Phase 5 until this validation passes cleanly.

---

## Phase 5: EventBridge Automation

**Goal:** Remove the manual Crawler → Job trigger step, so new data lands and processes automatically.

**Steps:**

1. Enable EventBridge notifications on the bronze S3 bucket.
2. Create an EventBridge rule matching S3 object-created events for the `raw/fhir/` prefix.
3. Configure that rule to trigger the Glue Crawler.
4. `[Confirm and record: the specific mechanism used to chain "Crawler completion" to "start the ETL job" — e.g., a second EventBridge rule matching a Glue Crawler state-change event, versus a Glue Workflow/trigger configured for "on Crawler success." Document whichever is implemented, including the exact event pattern used.]`
5. Create a failure-path rule: on Crawler or Job failure state, publish to an SNS topic (with a subscribed email or other endpoint) so failures surface without manual inspection.
6. Test by uploading a new file and confirming the full chain runs without manual intervention, including a deliberate failure test to confirm the SNS alert fires.

**Outcome to confirm:** new data uploaded to the bronze bucket triggers cataloging, transformation, and load with no manual steps, and failures generate a visible alert.

---

## Phase 6 (Future): Streaming Ingestion

**Goal:** Evolve ingestion from batch file uploads toward stream processing of incoming FHIR data.

`[This phase is intentionally undefined in detail at this stage. Before beginning, define: the source/trigger for a "stream" in this context (e.g., a continuous feed vs. simulated near-real-time batches), whether this uses Kinesis, a queue-based pattern, or another mechanism, and how it interacts with or replaces the EventBridge-triggered batch flow from Phase 5. Do not begin implementation until this scope is defined.]`

---

## Issue Log

Record issues here as they're encountered and resolved, using this format:

```
### [Short issue title]
**Phase:** [phase number]
**Symptom:** [what was observed]
**Root cause:** [what actually caused it]
**Resolution:** [what fixed it]
```

---

## How to Maintain This Document

This document should be updated as work proceeds, not written once and left static. Follow these conventions so additions stay consistent:

**Adding a new step to an existing phase:**
Insert it in the numbered list at the point it actually occurs, don't append to the end regardless of order. Renumber the list.

**Recording a resolved issue:**
Add an entry to the Issue Log using the format above. Keep each field to one or two sentences — this log is a quick-reference index, not a full narrative. If a fuller writeup already exists elsewhere (e.g., a detailed pipeline writeup), link to it rather than duplicating it here.

**Adding context that doesn't fit a numbered step:**
Use a `[bracketed note]` inline, directly after the step it clarifies. Remove the brackets once the note is confirmed and no longer speculative — brackets in this document always mean "unconfirmed, needs a decision or verification," never a completed callout.

**Marking a phase complete:**
Add a one-line **Result** note under that phase's "Outcome to confirm" line (e.g., "Result: confirmed 2026-08-02, 0 orphaned rows"). Do not delete the original outcome criteria — future readers should be able to see both what was expected and what was confirmed.

**Changing a decision made earlier (e.g., switching an approach):**
Don't silently edit past steps. Add a new step noting the change and why, and leave the original step in place with a brief note that it was superseded (e.g., "Superseded — see step X"). This preserves the reasoning trail, which matters more for a process document than a clean-looking final state.

**Scope discipline:**
Keep each phase's steps to the mechanics of that phase only. If a step reveals a need for something outside the current phase's scope (e.g., a new IAM permission needed only for Phase 5 work), note it briefly where it's discovered, then move the actual implementation detail to the relevant phase's section.
