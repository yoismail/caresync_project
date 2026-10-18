
TL;DR
CareSync is a quality-gated ELT platform that turns unreliable weekly clinic file deliveries into a trusted reporting database. Files are sensed, validated, loaded, transformed, and verified with SLA monitoring, quarantine, cascade-skip logic, and full stakeholder notifications.
Stack: Python 3.11, Google Drive API, GitHub Actions, Snowflake, dbt, Slack/Email alerts
Runtime: 3 to 5 minutes end-to-end pipeline, scheduled weekly at 11:00 AM UK time on Fridays
Scale: 6 CSVs, approximately 114K total rows, schema-enforced with per-file row bounds and value validation
Author: Yomi Ismail, Data Engineer (Suffolk, UK)
Table of Contents

• Project Summary

• Business Context

• Project Purpose

• Expected Outcomes

• Project Objectives

• In Scope

• Out of Scope

• The Problem

• Stack Overview

• Business Impact

• Architecture

• Data Model and Schemas

• Data Quality Story

• Engineering Decisions

• How to Reproduce

• Repository Structure

• Honest Limits

• About the Author

• Connect

• License
Project Summary

CareSync is a quality-gated ELT platform that turns unreliable weekly clinic file deliveries into a trusted reporting database. Every week, a third-party agent drops six CSV exports into Google Drive. The pipeline senses each file under a one-hour SLA, runs it through a pre-validation gate before ingestion, loads validated files into Snowflake, transforms them with dbt into a single-fact star schema, and then runs a post-validation gate that verifies the reporting layer satisfies business requirements. Files that fail pre-validation are quarantined and their processing tasks are skipped, not failed, while stakeholders are notified automatically via Slack and email.

The project is delivered in two tooling stages. Everything is first built and proven with Python pandas validation orchestrated by GitHub Actions, then productionized by replacing every pandas check with Great Expectations suites and replacing GitHub Actions with Airflow. All data is synthetic, generated with Synthea.
Business Context

Nexora's partner clinics do not deliver data directly. A third-party data aggregation agent consolidates each clinic's weekly export and delivers six CSV files into a shared Google Drive folder on a contractual schedule. Clinic operations reviews, provider workload planning, and payer reconciliation all run off the weekly CareSync reports, so the timeliness and correctness of these files directly affect operational decisions across the clinic network.

Because a third party sits in the delivery chain, Nexora controls neither when files arrive nor what condition they arrive in. Delivery times drift, export formats change when clinic systems are upgraded, and files can arrive truncated or malformed.

Because this project is intended for development and testing, Nexora uses synthetic healthcare data generated with Synthea, an open-source synthetic patient generator. This provides realistic healthcare records with no exposure of sensitive patient information.
Project Purpose

To deliver trustworthy weekly clinic reporting by ensuring that only validated data enters the warehouse, only verified data reaches stakeholders, and every quality event including late file, rejected file, failed business check, or successful run, is communicated to stakeholders automatically.
Expected Outcomes

By the end of the project:

• Every incoming file is validated before ingestion; no unvalidated data can reach Snowflake.

• A failed file is quarantined and its processing is skipped, with the skip cascading to dependent datasets, while all healthy files load normally.

• Stakeholders receive Slack and email notifications for SLA misses, validation failures, task errors, and successful runs, each traceable by run ID.

• The production reporting layer is verified against business requirements on every run before it is treated as trusted.

• File arrival is monitored against a one-hour SLA, creating an audit trail of third-party delivery performance.

• The full pipeline exists in both forms: the pandas plus GitHub Actions testing build, and the Great Expectations plus Airflow production build.

• A complete audit trail including run logs, validation results, quarantined files, and notification history supports every weekly run.
Project Objectives

• File sensing with SLA: Detect each expected weekly file in Google Drive; if a file has not arrived within one hour of its scheduled delivery time, alert stakeholders via Slack and email.

• Pre-validation: Before ingestion, run every file through a validation pipeline including schema compliance, mandatory field checks, identifier format, value ranges, date chronology, duplicate detection, and row-count sanity bounds.

• Skip, do not fail: A file that fails validation is quarantined and its downstream tasks are skipped, with skip status propagating to dependent datasets. All unaffected files continue processing normally.

• Notifications: Slack and email alerts for SLA misses, validation failures, task errors, post-validation results, and a consolidated success summary at the end of each run.

• Load and transform: Load clean data into Snowflake RAW layer; use dbt to build a PHI-minimized star schema in the reporting warehouse, removing direct identifiers from the analytics layer.

• Post-validation: Confirm final tables meet business requirements including row counts, key uniqueness, referential integrity, and record completeness.

• Dev-to-prod maturity path: Build and validate the pipeline locally with Python pandas and GitHub Actions; productionize by migrating validation suites to Great Expectations and orchestration to Apache Airflow.
In Scope

• Six standard Synthea HL7 datasets: patients, encounters also known as appointments, organizations, providers, payers, conditions

• Google Drive as the weekly delivery landing zone with one-hour arrival SLA monitoring

• Two-stage validation: pre-ingestion checks in Python, followed by business-rule post-validation in the data warehouse

• Quarantine store and cascade-skip logic for failed files

• Slack and email notification system covering all pipeline events

• Snowflake data warehouse architecture: RAW to STAGING to PROD

• dbt transformations producing a star schema: fct_appointments plus dimensions plus conditions detail table, with PHI minimization applied

• GitHub Actions orchestration for development and testing; Airflow DAG as production target architecture

• Run audit logging and persistent quarantine for rejected files

• SQL-based reporting and data-quality validation queries
Out of Scope

• Real patient data or live clinic system integration: all datasets are synthetic HL7 from the Synthea project

• Additional Synthea domains including observations, medications, claims, procedures, and immunizations are excluded from the current reporting boundary

• Real-time or streaming ingestion: pipeline operates on a scheduled weekly batch cadence

• BI dashboards: the data warehouse and marts layer is the delivery handoff point

• Advanced identity management or access governance: role-based access is assumed at the Snowflake account level

• Machine learning workloads or predictive analytics: descriptive reporting only
The Problem

Six standard HL7 CSV files are expected every week:
Dataset File Typical Rows Purpose 
Patients patients.csv Approximately 1,000 Demographics and patient profiles 
Encounters encounters.csv Approximately 60,000 Patient care visits and appointments 
Conditions conditions.csv Approximately 38,000 Diagnoses and clinical history 
Providers providers.csv Approximately 5,000 Healthcare practitioners 
Payers payers.csv 10 Insurance providers and financial metrics 
Organizations organizations.csv Approximately 1,100 Healthcare facilities and locations 

Files arrived inconsistently. Sometimes late, sometimes missing columns, sometimes with illogical values. No automated validation meant bad data reached downstream reports. No versioned history of file deliveries. No SLA awareness or alerts. Analysts manually verified every weekly drop before trusting the data.
Stack Overview
Layer Technology Purpose 
Orchestration Python Orchestrator plus GitHub Actions Sensor to Validate to Load to Transform to Notify 
Source Google Drive API Monitors target folder for 6 expected files 
Validation Python schema definitions Columns, mandatory fields, UUID formats, allowed values, row counts 
Storage Local runner or GitHub workspace data/landing/ for raw files, data/landing/quarantine/ for invalid files 
Data Warehouse Snowflake RAW, STAGING, PROD schemas 
Transformation dbt or Data Build Tool Star schema: fact table plus dimensions, PHI minimization 
Scheduling GitHub Actions Schedule Trigger Weekly Friday at 11:00 AM UK time with automatic DST adjustment 
Notifications Slack Webhook plus SMTP Email Pipeline success or failure alerts plus SLA breach warnings 
Language Python 3.11, SQL Sensor logic, config, validation, dbt models and tests 

Business Impact

Before this pipeline:

• Manual file check every Friday morning to confirm files arrived

• No consistent schema definition so it was unclear if a CSV had all required columns

• Bad data was silently loaded with no visibility into inconsistent values

• No timestamp record of when files actually arrived

• No automated notification system when loads failed

After this pipeline:

• Arrival confidence: Sensor confirms all 6 files present before processing begins

• SLA protection: One-hour delivery window monitored with immediate alerts for late files

• Schema enforcement: Missing columns, wrong types, or out-of-range values result in quarantine while pipeline continues

• Skip-not-fail semantics: One bad file does not block the entire weekly run

• Transparent flow: Every step is logged, timestamped, and summarized in one notification

• Analytics ready: dbt produces a clean, PHI-minimized star schema with built-in data tests
Architecture

Google Drive Folder containing 6 CSV files
|
v
Step 0: Sensor and SLA Check
Check folder for file presence and arrival time against SLA
|
+-- SLA Miss ------------------------------ Send Alert
|
v SLA OK and 6 files found
Step 1: Pre-Validation
Schema Check then Value and Row Check
|
+-- Fail -> Quarantine File -> Skip Dependent Files -> Send Notification
|
v Pass
Step 2: Load to Snowflake.RAW
|
v
Step 3: Transform with dbt
Staging then Dimensions and Fact Table then dbt Tests
|
v
Step 4: Post-Validation
Row counts, uniqueness, referential integrity, completeness
|
v
Step 5: Notify Stakeholders
Slack and Email: success or failure with full summary

Pipeline flow in detail:

SENSOR AND SLA CHECK
Scheduled: Friday 11:00 AM UK time
SLA window: 1 hour with deadline at 12:00 PM
File count: 6 expected then 6 found
Download CSVs to data/landing/

PRE-VALIDATION per file
Schema: all required columns present
Mandatory fields: no empty identifiers
Format: UUIDs and dates parse correctly
Values: coded fields within allowed sets
Chronology: start date is less than or equal to end date
Duplicates: no duplicate primary keys
Row sanity: count within expected bounds
PASS: Load to Snowflake.RAW
FAIL: Quarantine file and skip downstream tasks while other files continue

LOAD TO SNOWFLAKE
COPY INTO RAW.HL7.table_name

DBT BUILD
Staging models with PHI columns masked or dropped
Dimensions: patients, providers, payers, organizations
Fact table: fct_appointments plus conditions detail
Built-in data tests run automatically

POST-VALIDATION
Row count verification: RAW matches PROD
Key uniqueness: no duplicates in final tables
Referential integrity: all keys resolve correctly
Completeness: no unexpected nulls in critical fields

NOTIFY
Slack alerts for SLA miss, validation fail, pipeline success, post-validation result
Email summary with row counts, skipped files, and quarantine details

End-to-end runtime: 3 to 5 minutes. Cost: Free tier eligible.
Data Model and Schemas

Three conceptual layers in Snowflake:

• RAW.HL7: Landing tables that mirror CSV structure exactly. Source-of-truth archive.

• STAGING: Cleaned and standardized. PHI columns identified and prepared for exclusion.

• PROD: Star schema. Fact table fct_appointments linked to dimensions. Direct identifiers including names, SSNs, and document numbers are removed.

Folder structure:

caresync_project/
├── data/
│   ├── landing/                 # Sensor downloads CSVs here
│   └── landing/quarantine/      # Invalid files with timestamp and reason
└── sla_report.json              # Generated on each run
Data Quality Story

Two independent validation layers catch different failure modes:

Layer 1: Pre-Validation before Warehouse Ingestion

Every file is assessed before any data leaves the landing zone. Failures are specific including which file, which check, and which row. The file is quarantined rather than dropped. Other files proceed normally. Dependent files that reference a skipped file are also skipped through cascade logic, preventing foreign-key errors downstream.

Layer 2: Post-Validation after Transformation

Once the reporting schema is built, the pipeline verifies business outcomes rather than just technical validity. Are row counts stable across layers? Do all keys resolve? Is the fact table complete? These answers form the report-ready confirmation sent to stakeholders.
Engineering Decisions

1. Validate early, quarantine visibly, skip gracefully.
Bad data is cheapest to fix at the source. Reject before loading, keep the file for inspection, and skip only what depends on it. The rest of the pipeline delivers value. Tradeoff: some reports will be partial that week. Benefit: no silent data loss and bad data is preserved rather than erased.

2. SLA monitoring separate from file processing.
The sensor answers two questions independently: Did the files arrive? and Did they arrive on time? A late file can still be processed, but the SLA alert fires regardless. This separates operational discipline from data validity.

3. Two-phase validation: technical then business.
Pre-validation ensures the computer can read the file. Post-validation ensures the business can trust the output. Technical errors such as wrong delimiter fail immediately. Business questions such as whether zero encounters for a provider is plausible are answered after the full model is built.

4. Dev-first architecture: Python to Great Expectations and GitHub Actions to Airflow.
Build and iterate fast with lightweight tools. Once the validation rules are proven in production, swap the implementation layer without rewriting the business logic. This separates what we check from how we run it.

5. PHI minimization at the staging boundary.
Direct identifiers are excluded before the data enters the final reporting schema. The RAW layer retains original data for troubleshooting while the PROD layer never exposes names, SSNs, or document numbers. This is a deliberate architectural boundary rather than a late transformation step.
How to Reproduce

Prerequisites

• Python 3.11 or newer

• Snowflake account

• Google Cloud service account with Drive API access

• GitHub repository with Actions enabled

Setup Steps

1. Fork the repository

2. Configure .env from .env.example including Google Drive folder ID, Snowflake credentials, notification endpoints, and SLA schedule

3. Service account access: grant your service account viewer permission on the Google Drive delivery folder

4. Snowflake schema setup: run DDL scripts to create RAW, STAGING, and PROD layers

5. dbt profile: configure profiles.yml with Snowflake target; run dbt deps then dbt build to test locally

6. GitHub Secrets: store all .env values as encrypted repository secrets

7. Enable workflow: the weekly schedule activates on merge to main; use the Run workflow button for manual tests
Repository Structure

caresync_project/
├── python/
│   ├── config.py                  # Paths, schemas, SLA schedule
│   ├── sensor.py                 # Google Drive API and SLA timing
│   ├── pre_validation.py         # Per-file validation rules
│   ├── post_validation.py        # Warehouse business checks
│   ├── snowflake_loader.py       # RAW layer ingestion
│   ├── dbt_runner.py             # dbt build orchestration
│   ├── notifications.py          # Slack and email delivery
│   └── orchestrator.py           # Step control and cascade skip logic
├── dbt/
│   ├── models/
│   │   ├── staging/              # PHI minimization applied here
│   │   └── marts/
│   │       ├── dim_*.sql         # De-identified dimensions
│   │       └── fct_appointments.sql  # Central fact table
│   ├── dbt_project.yml
│   └── packages.yml              # dbt_utils and codegen
├── .github/
│   └── workflows/
│       └── pipeline.yml          # Weekly schedule and manual dispatch
├── data/
│   ├── landing/                  # Sensor download location
│   └── landing/quarantine/       # Rejected files preserved here
├── .env.example                  # Configuration template
├── .gitignore                    # Secrets, data, and local environment files
├── requirements.txt              # Python dependencies
├── README.md                     # This file
└── LICENSE                       # MIT License
Honest Limits

1. Synthetic data only. All files come from the Synthea HL7 generator. Schema patterns and data issues reflect realistic healthcare data characteristics but contain no real patient information.

2. Weekly batch cadence only. Designed for a once-per-week delivery window. No incremental logic or change-data-capture pattern implemented. Full replacement loads on every run.

3. Dev stack current. Airflow and Great Expectations are target architecture only. The current implementation uses Python pandas validation and GitHub Actions. The production migration path is documented but not yet deployed in this repository.

4. Limited retry and backoff. File download and database operations have basic error handling but no exponential backoff or retry loops. Transient network issues may fail the run without automatic recovery.
About the Author

Yomi Ismail builds end-to-end data pipelines across cloud and on-premise stacks. This project grew from a need to standardize HL7 healthcare data delivery, moving from the simple question of Did the files arrive? to a repeatable, documented, and auditable data pipeline.

Related work in the same portfolio:

• National Hospital: Azure ELT pipeline using ADF orchestration, Databricks transformation, ADLS Gen2 storage, and Azure SQL Data Warehouse

• Nova Retail: On-premise medallion lakehouse using Docker Compose, Airflow, PySpark, and PostgreSQL

• World Football Insights: GCP serverless pipeline using Cloud Composer, Dataproc Serverless, GCS, and BigQuery

• FibbieBanks: PySpark ETL with surrogate key management and PostgreSQL star schema
Connect

• Portfolio: yoismail.github.io/portfolio

• LinkedIn: linkedin.com/in/yomi-ismail

• Email: ismailyomi@gmail.com
License

MIT License. See LICENSE file for details.
Built in Suffolk, England.