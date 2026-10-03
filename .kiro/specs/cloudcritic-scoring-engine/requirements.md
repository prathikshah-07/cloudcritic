# Requirements Document

## Introduction

The CloudCritic Scoring Engine is a deterministic Python module that evaluates an AWS architecture description against the six pillars of the AWS Well-Architected Framework (Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability). Given a structured architecture description, the engine produces a score from 0 to 100 for each pillar, an aggregate weighted score, and a prioritized list of concrete remediation recommendations for identified gaps.

The engine must be deterministic: identical inputs always produce identical outputs, enabling reproducible scoring in CI/CD pipelines and audit workflows.

## Glossary

- **Scoring_Engine**: The Python module that accepts an architecture description and returns a scored evaluation result.
- **Architecture_Description**: A structured input document (JSON or YAML) that describes an AWS architecture's components, configurations, and relationships.
- **Pillar**: One of the six AWS Well-Architected Framework pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability.
- **Pillar_Score**: A numeric value between 0 and 100 (inclusive) representing how well the architecture satisfies the criteria for a given Pillar.
- **Aggregate_Score**: A single numeric value between 0 and 100 (inclusive) derived from a weighted combination of all Pillar_Scores.
- **Rule**: A discrete, evaluable criterion derived from AWS Well-Architected best practices that maps to one Pillar.
- **Rule_Result**: The outcome of evaluating one Rule against an Architecture_Description, containing a pass/fail status and an evidence snippet.
- **Finding**: A gap identified when a Rule fails, containing the Pillar, severity, impacted component(s), and a concrete remediation recommendation.
- **Evaluation_Report**: The complete output of the Scoring_Engine, containing all Pillar_Scores, the Aggregate_Score, and the list of Findings.
- **Severity**: A classification of a Finding's impact, one of: CRITICAL, HIGH, MEDIUM, or LOW.
- **Determinism**: The property that identical Architecture_Description inputs always produce identical Evaluation_Reports.
- **Rule_Catalog**: The versioned collection of all Rules used by the Scoring_Engine.
- **Pretty_Printer**: A component that serializes an Evaluation_Report back to a canonical JSON or YAML string.

---

## Requirements

### Requirement 1: Architecture Description Parsing

**User Story:** As a developer, I want to provide an AWS architecture description in JSON or YAML format, so that the Scoring_Engine can evaluate it without requiring manual format conversion.

#### Acceptance Criteria

1. WHEN a valid JSON Architecture_Description is provided, THE Scoring_Engine SHALL parse it into an internal representation preserving all field names, field values, and structural nesting present in the input.
2. WHEN a valid YAML Architecture_Description is provided, THE Scoring_Engine SHALL parse it into an internal representation preserving all field names, field values, and structural nesting present in the input.
3. WHEN an Architecture_Description contains fields not defined in the Architecture_Description schema, THE Scoring_Engine SHALL ignore those fields and continue parsing the remaining recognized fields.
4. IF an Architecture_Description is syntactically invalid (malformed JSON or YAML), THEN THE Scoring_Engine SHALL return a structured parse error that includes the line number, column number, and a description of the syntax violation, without producing a partial internal representation.
5. IF an Architecture_Description is syntactically valid but fails schema validation (missing required top-level fields), THEN THE Scoring_Engine SHALL return a structured validation error listing each missing or invalid field by name, without producing a partial internal representation.
6. THE Pretty_Printer SHALL serialize any successfully parsed Architecture_Description back to canonical JSON preserving all field names, field values, and structural nesting present in the parsed internal representation.
7. WHEN a valid Architecture_Description is parsed, then serialized by the Pretty_Printer, then re-parsed, THE Scoring_Engine SHALL produce an internal representation where every field name, field value, and structural nesting level is identical to the result of the original parse.

---

### Requirement 2: Rule-Based Evaluation Against Well-Architected Pillars

**User Story:** As a cloud architect, I want each pillar evaluated by discrete, versioned rules, so that scoring is traceable, auditable, and updatable independently per pillar.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL evaluate the Architecture_Description against the Rule_Catalog for all six Pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability.
2. THE Scoring_Engine SHALL produce exactly one Rule_Result per Rule per evaluation run, where each Rule_Result contains the Rule identifier, Pillar name, pass/fail status, and the evidence snippet extracted from the Architecture_Description that determined the result.
3. THE Rule_Catalog SHALL carry a version identifier in the format MAJOR.MINOR.PATCH, and THE Scoring_Engine SHALL include the Rule_Catalog version identifier in every Evaluation_Report.
4. WHEN the Rule_Catalog version changes, THE Scoring_Engine SHALL produce Evaluation_Reports that reflect the updated rules without requiring changes to the Architecture_Description input format.
5. THE Scoring_Engine SHALL evaluate each Rule independently so that the failure of one Rule does not prevent evaluation of remaining Rules.
6. IF a Rule evaluation produces no matching evidence in the Architecture_Description, THEN THE Scoring_Engine SHALL record the Rule_Result with a fail status and an evidence snippet value indicating no evidence was found.
7. IF the Rule_Catalog is unavailable or fails to load, THEN THE Scoring_Engine SHALL halt evaluation and produce an error report indicating the Rule_Catalog could not be accessed, without producing any partial Evaluation_Report.

---

### Requirement 3: Deterministic Scoring

**User Story:** As a DevOps engineer, I want identical architecture inputs to always produce identical scores, so that I can use the engine reliably in CI/CD pipelines and track genuine changes over time.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL produce an Evaluation_Report with identical Pillar_Scores, Aggregate_Score, and Findings for the same Architecture_Description input across multiple invocations using the same Rule_Catalog version.
2. THE Scoring_Engine SHALL derive all scoring computations from the Architecture_Description and Rule_Catalog alone, with no dependence on external state, timestamps, random number generation, or network calls.
3. WHEN two Architecture_Description inputs are semantically equivalent but differ only in key ordering or whitespace, THE Scoring_Engine SHALL produce identical Pillar_Scores and Aggregate_Score for both inputs.
4. IF the Rule_Catalog version used during scoring differs from the version recorded in a previously generated Evaluation_Report for the same Architecture_Description, THEN THE Scoring_Engine SHALL include an indication in the Evaluation_Report that the Rule_Catalog version has changed.
5. WHEN the Scoring_Engine completes evaluation, THE Scoring_Engine SHALL record the Rule_Catalog version identifier in the Evaluation_Report so that score comparisons across invocations can be validated against a consistent Rule_Catalog version.

---

### Requirement 4: Pillar Score Calculation

**User Story:** As a cloud architect, I want a numeric score per pillar, so that I can see where my architecture is strongest and weakest across the Well-Architected dimensions.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL calculate a Pillar_Score for each of the six Pillars as a value between 0 and 100 inclusive, rounded to the nearest integer using round-half-up rounding.
2. THE Scoring_Engine SHALL derive each Pillar_Score as: floor((passing_rules / total_evaluated_rules) * 100 + 0.5), where total_evaluated_rules includes all Rules in the Rule_Catalog assigned to that Pillar that completed evaluation (pass or fail), excluding Rules that produced an internal evaluation error.
3. WHEN all Rules for a Pillar pass, THE Scoring_Engine SHALL assign that Pillar a Pillar_Score of 100.
4. WHEN no Rules for a Pillar pass, THE Scoring_Engine SHALL assign that Pillar a Pillar_Score of 0.
5. WHEN a Pillar has no applicable Rules in the Rule_Catalog, THE Scoring_Engine SHALL exclude that Pillar from scoring and include a field in the Evaluation_Report that lists all excluded Pillar names and the reason "no applicable rules".
6. WHEN a Rule produces an internal evaluation error for a Pillar, THE Scoring_Engine SHALL exclude that Rule from the Pillar_Score calculation and include the errored Rule identifier in the Evaluation_Report's error list.

---

### Requirement 5: Aggregate Score Calculation

**User Story:** As an engineering manager, I want a single overall score for the architecture, so that I can communicate its Well-Architected posture at a glance.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL calculate an Aggregate_Score as a weighted average of all included Pillar_Scores, with weights configurable per Pillar via a scoring configuration, where each individual weight must be a positive number greater than zero.
2. THE Scoring_Engine SHALL produce an Aggregate_Score between 0 and 100 inclusive, rounded to the nearest integer using round-half-up rounding.
3. WHEN all Pillar weights in the scoring configuration are equal, THE Scoring_Engine SHALL produce an Aggregate_Score equal to the arithmetic mean of all included Pillar_Scores, rounded using round-half-up rounding.
4. WHEN a Pillar is excluded from scoring (no applicable rules), THE Scoring_Engine SHALL redistribute its weight proportionally across the remaining included Pillars such that the sum of all included Pillar weights equals the original total weight.
5. IF a scoring configuration specifies any individual Pillar weight that is not a positive number greater than zero, THEN THE Scoring_Engine SHALL return a configuration validation error identifying the invalid Pillar name and weight value before performing any evaluation.

---

### Requirement 6: Finding Generation

**User Story:** As a cloud architect, I want concrete, actionable remediation guidance for each gap, so that I can prioritize and fix Well-Architected violations efficiently.

#### Acceptance Criteria

1. WHEN a Rule fails for a given Architecture_Description, THE Scoring_Engine SHALL generate a Finding that contains: the Pillar name, the Rule identifier, the Severity level, a list of one or more impacted component names from the Architecture_Description, a human-readable description of the gap of at least 10 words, and a remediation recommendation that includes at least one specific AWS service name or AWS Well-Architected best practice reference.
2. THE Scoring_Engine SHALL classify each Finding with a Severity of CRITICAL, HIGH, MEDIUM, or LOW based on the Rule's defined severity level in the Rule_Catalog.
3. THE Scoring_Engine SHALL produce Findings only for failed Rules; passing Rules SHALL NOT produce Findings.
4. THE Scoring_Engine SHALL include every Finding in the Evaluation_Report.
5. WHEN generating the Evaluation_Report, THE Scoring_Engine SHALL sort Findings by Severity in descending order (CRITICAL first, then HIGH, MEDIUM, LOW), with ties broken by Pillar name in ascending alphabetical order.
6. IF a Rule that fails does not have remediation text defined in the Rule_Catalog, THEN THE Scoring_Engine SHALL generate a Finding with a remediation recommendation field containing the text "No remediation guidance available for rule {rule_id}" where {rule_id} is the Rule identifier.

---

### Requirement 7: Evaluation Report Output

**User Story:** As a developer, I want a structured, machine-readable Evaluation_Report, so that I can integrate scoring results into dashboards, CI gates, and audit trails.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL return an Evaluation_Report as a Python object serializable to JSON using Python's standard `json` module without custom encoders.
2. THE Evaluation_Report SHALL contain the following fields: rule_catalog_version (string), schema_version (semver string), pillar_scores (mapping of Pillar name to Pillar_Score), aggregate_score (integer), total_rules (integer), passing_rules (integer), failing_rules (integer), excluded_pillars (list), error_rules (list), and findings (list of Finding objects).
3. THE Scoring_Engine SHALL include in the Evaluation_Report a schema_version field formatted as a semantic version string (MAJOR.MINOR.PATCH) so consumers can handle future format changes.
4. THE Pretty_Printer SHALL serialize any Evaluation_Report to a canonical JSON string with keys sorted in ascending alphabetical order and 2-space indentation.
5. WHEN a valid Evaluation_Report is serialized to JSON by the Pretty_Printer and then deserialized, THE resulting Python object SHALL have identical field names, field values, and field types to the original Evaluation_Report.

---

### Requirement 8: Configurable Pillar Weights

**User Story:** As an enterprise architect, I want to adjust the weight of each pillar in the Aggregate_Score calculation, so that I can align scoring with my organization's architectural priorities.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL accept an optional ScoringConfig object that specifies a weight for each of the six Pillars as a positive number greater than zero.
2. WHEN no ScoringConfig is provided or when an empty ScoringConfig is provided, THE Scoring_Engine SHALL apply a weight of 1.0 to all included Pillars.
3. IF a ScoringConfig specifies any individual Pillar weight that is not a positive number greater than zero, THEN THE Scoring_Engine SHALL raise a ConfigurationError identifying the invalid Pillar name and the invalid weight value before performing any evaluation.
4. IF a ScoringConfig specifies a weight for a Pillar name that is not one of the six recognized Pillar names, THEN THE Scoring_Engine SHALL raise a ConfigurationError identifying the unrecognized Pillar name before performing any evaluation.

---

### Requirement 9: Error Handling and Observability

**User Story:** As a developer integrating the engine, I want clear, structured errors and logging, so that I can diagnose failures quickly without inspecting internal state.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL raise a typed exception that is a subclass of a single CloudCriticError base exception class for each distinct error category: ParseError for syntax failures, ValidationError for schema failures, ConfigurationError for configuration failures, and EvaluationError for internal rule evaluation failures.
2. WHEN an internal evaluation error occurs during Rule evaluation, THE Scoring_Engine SHALL log the error at ERROR level with the Rule identifier and the exception message, then continue evaluating remaining Rules, and include the errored Rule identifier in the Evaluation_Report's error_rules list.
3. THE Scoring_Engine SHALL expose a structured log stream using Python's standard `logging` module, with DEBUG-level entries for individual Rule evaluation results, INFO-level entries for evaluation lifecycle events, WARNING-level entries for non-fatal issues such as excluded Pillars, and ERROR-level entries for Rule evaluation failures.
4. WHEN the Scoring_Engine completes an evaluation, THE Scoring_Engine SHALL emit an INFO-level log entry containing the Aggregate_Score as an integer, the Rule_Catalog version string, and the total evaluation duration in milliseconds as an integer.
5. IF an Architecture_Description string exceeds 10,485,760 bytes (10 MiB) in size when encoded as UTF-8, THEN THE Scoring_Engine SHALL raise a ValidationError before attempting to parse it, with a message indicating the actual size and the 10 MiB limit.

---

### Requirement 10: Public Python API

**User Story:** As a developer, I want a clean, importable Python API, so that I can call the scoring engine programmatically from other modules, scripts, and test suites without subprocess calls.

#### Acceptance Criteria

1. THE Scoring_Engine SHALL expose a primary entry-point function with the signature `score(architecture_description: str, config: Optional[ScoringConfig] = None) -> EvaluationReport` that accepts a raw JSON or YAML string and returns a typed EvaluationReport object, or raises a CloudCriticError subclass if the input is invalid.
2. THE Scoring_Engine SHALL expose the symbols `EvaluationReport`, `Finding`, `PillarScore`, `ScoringConfig`, `CloudCriticError`, `ParseError`, `ValidationError`, `ConfigurationError`, and `EvaluationError` as importable from the module's top-level `__init__.py`.
3. THE Scoring_Engine SHALL be importable without side effects — no file I/O, no network calls, no modifications to the root logger or any logging handler configuration — at import time.
4. WHEN the `score` function is called concurrently from N threads with N distinct Architecture_Description inputs, THE Scoring_Engine SHALL return N EvaluationReports where each report's Pillar_Scores, Aggregate_Score, and Findings correspond exclusively to the Architecture_Description passed by that thread, with no cross-contamination between threads.
