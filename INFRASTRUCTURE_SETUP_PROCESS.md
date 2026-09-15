# Process Document: Infrastructure Setup

## Purpose

This document records the process used to build the AWS infrastructure and networking foundation for the S3-to-Redshift ETL pipeline, and to validate it end to end using a dummy dataset before real FHIR data was introduced. It is a retrospective record of completed work, kept as a repeatable reference for rebuilding this infrastructure or for similar AWS pipeline projects.

For the process covering FHIR ingestion, Glue ETL extension, and EventBridge automation built on top of this foundation, see `PIPELINE_EXPANSION_PROCESS.md`.

## Revision History

| Date       | Phase   | Change                                                                                                                                        |
| ---------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-09-08 | —       | Initial document created, covering completed infrastructure setup                                                                             |
| 2026-09-15 | 3, 4, 7 | Added notes about incurring costs for Redshift, secrets, and Interface VPC endpoints, and about the Glue Connection's reusability across jobs |

## Phase Overview

| Phase | Goal                                                                   |
| ----- | ---------------------------------------------------------------------- |
| 1     | Networking foundation: VPC, security group, S3 Gateway endpoint        |
| 2     | IAM setup: boto3 user and Glue service role                            |
| 3     | Redshift Serverless: namespace, workgroup, admin credentials           |
| 4     | Additional VPC endpoints required for Glue-to-AWS-service connectivity |
| 5     | Storage lifecycle: staging prefix expiration                           |
| 6     | Glue Data Catalog: database and Crawler, tested against dummy data     |
| 7     | Glue Connection to Redshift, and connectivity validation               |
| 8     | Glue ETL job: dummy data spike, source to target                       |

---

## Phase 1: Networking Foundation

**Goal:** Establish a VPC-based network path that lets Glue and Redshift communicate privately, and lets Glue reach S3 without a NAT Gateway.

**Steps:**

1. Confirmed the account's default VPC (no custom VPC created — default subnets and routing were sufficient for this project's scale).
2. Created a security group (`glue-redshift-sg`) scoped to the default VPC.
3. Added a self-referencing inbound rule: TCP port 5439, source set to the security group itself — chosen specifically because Glue's ENIs receive dynamically assigned IPs on each run, so an IP-based rule would not remain valid.
4. Created an S3 Gateway VPC endpoint (free, route-table-based) and associated it with the default VPC's route table, giving VPC-bound resources a private path to S3 without a NAT Gateway.

**Outcome confirmed:** security group and S3 endpoint exist and are ready to attach to Glue and Redshift resources in later phases.

---

## Phase 2: IAM Setup

**Goal:** Create least-privilege identities for local (boto3) and service (Glue) access, scoped to only the resources each needs.

**Steps:**

1. Created the bronze S3 bucket first, so IAM policies could reference a real bucket ARN.
2. Created an IAM user (`synthea-boto3-local`) for local script access, with a custom policy (not an AWS-managed policy, which would have been overly broad) granting `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` scoped to the bronze bucket's ARN and its `/*` object path.
3. Created an IAM role (`glue-synthea-etl-role`) with a trust policy allowing the AWS Glue service to assume it.
4. Attached the AWS-managed `AWSGlueServiceRole` policy for baseline Glue service permissions (logging, core Glue API access).
5. Created and attached a custom policy granting S3 read on the bronze bucket and read/write/delete on the `/staging` prefix.
6. Created and attached a custom policy granting `secretsmanager:GetSecretValue`, scoped to the Redshift-managed admin secret using a wildcard suffix (`redshift!<workgroup-name>-admin*`) rather than a pinned ARN, since Redshift generates a new random suffix each time the secret is recreated.
7. Created an IAM role for Redshift itself (separate from the Glue role), trusted by the Redshift service, granting S3 read access on the bronze bucket's `/staging` prefix — required for Redshift's `COPY` command to read staged files. Associated this role with the Redshift namespace.

**Outcome confirmed:** all three identities (boto3 user, Glue role, Redshift namespace role) created with least-privilege, bucket/prefix-scoped policies.

---

## Phase 3: Redshift Serverless Setup

**Goal:** Stand up the target data warehouse.

**Steps:**

1. Created a Redshift Serverless namespace (`redshift-synthea-namespace`) and workgroup (`redshift-synthea-workgroup`), with a database name matching the project.
2. Enabled **"Manage admin credentials in AWS Secrets Manager"** during namespace creation, so Redshift generates and stores its own admin credentials rather than requiring a manually-set password.
3. Left encryption on the default AWS-owned KMS key (no custom key needed for this project's scope).
4. Attached the default VPC, its subnets, and the `glue-redshift-sg` security group to the workgroup's network configuration — deselecting the account's default security group, so the workgroup's effective access is defined by exactly one, auditable security group.
5. Attached the IAM role created in Phase 2, Step 7, to the namespace.

**Outcome confirmed:** namespace and workgroup show as Available; admin secret exists in Secrets Manager.

**Note:** The secrets and Redshift namespace and workgroup incur a small hourly cost while active, and a per-GB data storage charge. When taking a pause from this project, consider pausing or deleting the secrets and namespace/workgroup to avoid ongoing charges, and recreate them later if/when the pipeline is rebuilt.

---

## Phase 4: Additional VPC Endpoints

**Goal:** Resolve service-reachability gaps discovered while testing the Glue-to-Redshift connection (see Issue Log). Not anticipated at initial VPC setup — added in response to connection failures during Phase 7 testing, and recorded here as part of the networking foundation for future rebuilds.

**Steps:**

1. Created an Interface VPC endpoint for STS (`com.amazonaws.<region>.sts`), required for Glue to assume its IAM role from within the VPC.
2. Created an Interface VPC endpoint for Secrets Manager (`com.amazonaws.<region>.secretsmanager`), required for Glue to retrieve the Redshift admin secret from within the VPC.
3. Both endpoints placed in the same subnets used by the Glue connection, with `glue-redshift-sg` extended to allow inbound HTTPS (port 443, self-referencing) to cover Interface endpoint traffic.

**Outcome confirmed:** Glue Connection creation succeeded after these endpoints were added (see Issue Log for the specific errors this resolved).

**Note for future rebuilds:** this phase should logically happen alongside Phase 1, not after Phase 7 — it's sequenced here to reflect the order it was actually discovered and built. If rebuilding this infrastructure from scratch, create all VPC endpoints (S3 Gateway, STS Interface, Secrets Manager Interface) together in one pass.

**Note:** The STS and Secrets Manager Interface endpoints are not free — they incur a small hourly cost and a per-GB data processing charge. The S3 Gateway endpoint is free. When taking a pause from this project, consider deleting the Interface endpoints to avoid ongoing charges, and recreate them later if/when the pipeline is rebuilt.

---

## Phase 5: Storage Lifecycle

**Goal:** Prevent unbounded growth of disposable staging files.

**Steps:**

1. Created an S3 lifecycle rule (`expire-staging-files`) scoped to the `staging/` prefix, expiring objects 2 days after creation.

**Outcome confirmed:** rule active on the bronze bucket's Management tab.

---

## Phase 6: Glue Data Catalog Setup

**Goal:** Register a dummy dataset in the Glue Data Catalog to validate the crawl-and-catalog step before building real transformation logic.

**Steps:**

1. Created a Glue database (e.g., `synthea_spike`) to hold Catalog tables for this project.
2. Uploaded a small, hand-built dummy CSV (20 well-typed rows, no nulls or nested structures) to the bronze bucket under a `raw/` prefix.
3. Created a Glue Crawler pointed at `s3://<bronze-bucket>/raw/`, using `glue-synthea-etl-role`, outputting to the `synthea_spike` database.
4. Ran the Crawler and confirmed it created a table automatically, with an inferred schema.

**Outcome confirmed:** table visible under the target database with a schema matching the dummy CSV's columns.

---

## Phase 7: Glue Connection to Redshift

**Goal:** Establish and validate a reusable connection object between Glue and Redshift, independent of any specific job.

**Steps:**

1. Manually created the target Redshift table (`public.employees`) via Query Editor v2, with explicit column types, rather than relying on auto-generated types later in the Glue job.
2. Created a Glue Connection (type: Amazon Redshift), specifying the workgroup endpoint, port 5439, database name, the Secrets Manager secret for credentials, and the default VPC/subnet/`glue-redshift-sg`.
3. Used **Test connection** to validate. This surfaced three sequential issues before succeeding — see Issue Log.

**Outcome confirmed:** Test connection succeeded.

**Notes:** Because the Glue Connection is a reusable object, it can be used in multiple Glue jobs. If the Redshift workgroup is ever deleted and recreated, the connection will need to be updated with the new Secrets Manager secret ARN.

---

## Phase 8: Glue ETL Job — Dummy Data Spike

**Goal:** Move the dummy dataset from S3 through Glue into Redshift, validating the full pipeline end to end.

**Steps:**

1. Created a Glue job with a single source: the Glue Data Catalog table from Phase 6 (not a direct S3 path — the Catalog already encodes the file location).
2. Added a SQL Query transform node to explicitly cast column types (`employee_id` to `INT`, `hire_date` to `DATE`, `salary` to `DECIMAL(10,2)`) and rename `salary` to `annual_salary`.
3. Configured the Redshift target node with **Direct data connection** (not Glue Data Catalog tables — see Issue Log for why), pointed at `public.employees`, using "use existing table" rather than drop-and-recreate.
4. Ran the job and confirmed all 20 rows landed correctly with the expected column names and types.

**Outcome confirmed:** `SELECT * FROM public.employees;` returns 20 correctly-typed rows with no unexpected columns or nulls.

---

## Issue Log

### Secrets Manager access denied on Glue Connection creation

**Phase:** 7
**Symptom:** `InvalidInputException: ... not authorized to perform: secretsmanager:GetSecretValue`
**Root cause:** the custom Secrets Manager policy attached to the Glue role either wasn't attached, or its resource ARN didn't match the actual secret name.
**Resolution:** verified policy attachment and corrected the resource ARN to match the real secret, then generalized it to a wildcard pattern to survive future secret recreation.

### Failed to assume role — VPC has no access to STS

**Phase:** 7
**Symptom:** `Failed to assume the customers role. Verify that your VPC has access to STS.`
**Root cause:** no VPC endpoint existed for STS; the S3 Gateway endpoint does not cover STS traffic, and Glue's VPC-bound ENIs had no path to the STS API.
**Resolution:** created an Interface VPC endpoint for STS (Phase 4), with `glue-redshift-sg` allowing inbound 443 self-referencing traffic.

### Unable to connect to Secrets Manager

**Phase:** 7
**Symptom:** `Unable to connect to secrets manager. Please check that your VPC configuration can connect to secrets manager.`
**Root cause:** same category of issue as the STS error — no VPC endpoint existed for Secrets Manager.
**Resolution:** created an Interface VPC endpoint for Secrets Manager (Phase 4).

### Failed to initialize connection pool

**Phase:** 7
**Symptom:** `Failed to initialize pool: The connection attempt failed.`
**Root cause:** the Glue Connection's configured subnet did not match the subnet(s) actually used by the Redshift Serverless workgroup.
**Resolution:** aligned the Glue Connection's subnet selection with the workgroup's actual subnet configuration.

### Redshift target created extra typed columns with null data

**Phase:** 8
**Symptom:** after a successful job run, the target table contained unexpected columns (`employee_id_long`, `hire_date_string`, `annual_salary_double`) alongside the original columns, which were null.
**Root cause:** the Redshift target node was set to route through a Glue Data Catalog table definition for the target, which had its own separately inferred (and looser) schema. Explicit casts applied earlier in the job did not reconcile against this stale Catalog-side definition.
**Resolution:** recreated the target table, and switched the Redshift target node to **Direct data connection**, which maps the job's actual output schema to the real Redshift table rather than routing through a separate Catalog schema.

---

## How to Maintain This Document

This document reflects completed work, but infrastructure occasionally changes (e.g., credential rotation, added endpoints, security group adjustments). Keep it accurate over time using these conventions:

**Adding a new step to an existing phase:**
Insert it in the numbered list at the point it actually occurred or would occur in a rebuild. Renumber the list.

**Recording a newly discovered issue:**
Add an entry to the Issue Log using the existing format (Phase, Symptom, Root cause, Resolution). Keep each field to one or two sentences.

**Recording an infrastructure change made after initial setup:**
Add a new phase (or a step within the relevant existing phase) rather than editing the original steps to look as if they were done differently from the start. Note the date and reason for the change. Add a corresponding row to the Revision History table.

**Changing a decision made earlier:**
Don't silently edit past steps. Add a new step noting the change and why, and mark the original step as superseded with a brief pointer to its replacement.

**Updating the Revision History:**
Add a row any time a phase is added, a step is materially changed, or an issue is logged — not for minor wording fixes. Use the date, the phase affected (or `—` for document-wide changes), and a one-line description.
