# Implementation Plan: CloudCritic Scoring Engine

## Overview

Implement a deterministic, pure-Python library that ingests a structured AWS architecture description (JSON or YAML) and produces an `EvaluationReport` capturing per-pillar scores, a weighted aggregate score, and a prioritised list of remediation findings. The implementation follows a bottom-up order: domain models → exceptions → parser → catalog → scorer → findings → engine → public API → tests.

## Tasks

- [ ] 1. Set up project structure, package scaffold, and dependencies
  - Create `scoring_engine/` package directory with `__init__.py`, `models.py`, `exceptions.py`, `parser.py`, `scorer.py`, `findings.py`, `engine.py`
  - Create `scoring_engine/catalog/` sub-package with `__init__.py`, `version.py`, and six pillar rule modules under `catalog/rules/`
  - Create `tests/` directory with `conftest.py`, `strategies.py`, `unit/` and `property/` sub-directories (each with `__init__.py`)
  - Create `pyproject.toml` (or `setup.cfg`) declaring runtime dependencies: `pydantic>=2.0`, `PyYAML`, `hypothesis`; dev dependencies: `pytest`, `pytest-cov`
  - _Requirements: 10.1, 10.2, 10.3_

- [ ] 2. Implement domain models (`scoring_engine/models.py`)
  - [ ] 2.1 Define `Pillar` and `Severity` enums with `sort_key()` on `Severity`
    - `Pillar(str, Enum)` with all six Well-Architected pillars as string values
    - `Severity(str, Enum)` with CRITICAL=0, HIGH=1, MEDIUM=2, LOW=3 via `sort_key()`
    - _Requirements: 2.1, 4.1, 6.2, 6.5_
  - [ ] 2.2 Define frozen dataclasses: `Component`, `ArchitectureDescription`, `RuleResult`, `Finding`, `PillarScore`, `ScoringConfig`, `EvaluationReport`
    - `Component` uses `frozenset[tuple[str, Any]]` for properties
    - `ArchitectureDescription` uses `tuple[Component, ...]` and `frozenset` extras
    - `EvaluationReport.to_dict()` must return a plain dict serializable by `json.dumps()` with no custom encoders
    - _Requirements: 2.2, 4.1, 6.1, 7.1, 7.2, 7.3_
  - [ ]* 2.3 Write unit tests for domain models
    - Test enum ordering (`Severity.sort_key()`)
    - Test `EvaluationReport.to_dict()` is JSON-serializable with `json.dumps()`
    - _Requirements: 6.5, 7.1_

- [ ] 3. Implement exceptions (`scoring_engine/exceptions.py`)
  - [ ] 3.1 Define `CloudCriticError` base class and four subtypes
    - `CloudCriticError(RuntimeError)` as the common base
    - `ParseError(line, column, message)`, `ValidationError(errors: list[str])`, `ConfigurationError(pillar, value, reason)`, `EvaluationError(message)`
    - _Requirements: 9.1_
  - [ ]* 3.2 Write unit tests for exception hierarchy
    - Assert each subtype is a subclass of `CloudCriticError`
    - Assert fields are set correctly on each exception
    - _Requirements: 9.1_

- [ ] 4. Implement the parser (`scoring_engine/parser.py`)
  - [ ] 4.1 Implement UTF-8 size gate and format detection
    - Raise `ValidationError` if input exceeds 10,485,760 bytes (10 MiB) before parsing
    - Attempt JSON first (`json.loads`), fall back to YAML (`yaml.safe_load`)
    - _Requirements: 1.1, 1.2, 9.5_
  - [ ] 4.2 Implement syntactic error handling (JSON/YAML → `ParseError`)
    - Catch `json.JSONDecodeError` and `yaml.YAMLError`; surface line, column, message as `ParseError`
    - _Requirements: 1.4_
  - [ ] 4.3 Implement Pydantic v2 schema validation → `ValidationError`
    - Define a Pydantic model for the required top-level fields (`name`, `description`, `components`)
    - On validation failure, collect all missing/invalid field names and raise `ValidationError(errors=[...])`
    - _Requirements: 1.5_
  - [ ] 4.4 Implement `Parser.parse()` returning `ArchitectureDescription`
    - Extra fields are ignored (Requirement 1.3); build frozen `ArchitectureDescription` from validated data
    - _Requirements: 1.1, 1.2, 1.3_
  - [ ] 4.5 Implement `PrettyPrinter.to_json()` static method
    - Serialize with `json.dumps(obj, sort_keys=True, indent=2)`
    - _Requirements: 1.6, 7.4_
  - [ ]* 4.6 Write unit tests for `Parser` and `PrettyPrinter`
    - Test valid JSON parse, valid YAML parse, extra-field tolerance
    - Test `ParseError` fields (line, column) for malformed JSON/YAML
    - Test `ValidationError` field names for missing required fields
    - Test size boundary: exactly 10 MiB passes, 10 MiB + 1 byte raises `ValidationError`
    - _Requirements: 1.1–1.7, 9.5_

- [ ] 5. Checkpoint — parser passes all tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement the Rule Catalog (`scoring_engine/catalog/`)
  - [ ] 6.1 Define `Rule` dataclass and `RuleCatalog` class
    - `Rule` is a frozen dataclass with fields: `rule_id`, `pillar`, `severity`, `description`, `remediation`, `evaluate: Callable`
    - `RuleCatalog` aggregates rules from all pillar modules into an immutable `tuple[Rule, ...]`; exposes `rules_for_pillar()` and `get_rule()`
    - Export `CATALOG_VERSION` from `catalog/version.py` in semver format
    - _Requirements: 2.2, 2.3, 2.4_
  - [ ] 6.2 Implement at least one representative rule per pillar (six pillar modules)
    - `catalog/rules/operational_excellence.py`, `security.py`, `reliability.py`, `performance_efficiency.py`, `cost_optimization.py`, `sustainability.py`
    - Each rule's `evaluate` callable is a pure function returning `RuleResult`; missing evidence → `RuleResult(passed=False, evidence="no evidence found")`
    - _Requirements: 2.1, 2.5, 2.6_
  - [ ]* 6.3 Write unit tests for `RuleCatalog`
    - Test all six pillars have at least one rule
    - Test `CATALOG_VERSION` matches semver regex `^\d+\.\d+\.\d+$`
    - Test each rule has non-empty `rule_id`, `description`, and a valid `severity`
    - Test `rules_for_pillar()` returns only rules for the requested pillar
    - _Requirements: 2.1, 2.3_

- [ ] 7. Implement the scorer (`scoring_engine/scorer.py`)
  - [ ] 7.1 Implement `compute_pillar_score(passing: int, total: int) -> int`
    - Formula: `floor((passing / total) * 100 + 0.5)` (round-half-up)
    - Edge cases: `passing == 0` → 0, `passing == total` → 100, `total == 0` → treat as excluded (caller responsibility)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [ ] 7.2 Implement `compute_aggregate_score(pillar_scores, weights) -> int`
    - Weighted average with proportional weight redistribution for excluded pillars
    - Apply round-half-up rounding to final result
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [ ]* 7.3 Write unit tests for scorer functions
    - Test 0/N → 0, N/N → 100, exact midpoint rounding (e.g. 1/2 → 50, 3/4 → 75)
    - Test equal-weight aggregate equals arithmetic mean (rounded)
    - Test weight redistribution when one pillar is excluded
    - _Requirements: 4.1–4.4, 5.1–5.4_

- [ ] 8. Implement finding generation (`scoring_engine/findings.py`)
  - [ ] 8.1 Implement `generate_findings(rule_results, catalog) -> list[Finding]`
    - One `Finding` per `RuleResult` with `passed == False`
    - Fallback remediation: `"No remediation guidance available for rule {rule_id}"` when `rule.remediation` is empty
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_
  - [ ] 8.2 Implement findings sort: CRITICAL → HIGH → MEDIUM → LOW, ties by pillar name ascending
    - Sort in-place or return sorted list; use `(severity.sort_key(), pillar.value)` as composite key
    - _Requirements: 6.5_
  - [ ]* 8.3 Write unit tests for finding generation and sort order
    - Test passing rule produces no finding
    - Test failing rule with no remediation text uses fallback
    - Test findings are sorted CRITICAL → LOW, alpha by pillar on ties
    - Test every finding has ≥1 impacted component and description ≥10 words
    - _Requirements: 6.1–6.6_

- [ ] 9. Implement the evaluation engine (`scoring_engine/engine.py`)
  - [ ] 9.1 Implement `EvaluationEngine.__init__` accepting `RuleCatalog`
    - Store catalog reference; no side effects at construction time
    - _Requirements: 2.7, 10.3_
  - [ ] 9.2 Implement `EvaluationEngine.evaluate(arch, config) -> EvaluationReport`
    - Validate `ScoringConfig` (raise `ConfigurationError` for negative/zero weights or unrecognized pillar names)
    - Iterate pillars → rules; wrap each `rule.evaluate(arch)` in `try/except Exception`; log at ERROR; append to `error_rules` on failure
    - Exclude rules that errored from pillar score arithmetic (Requirement 4.6)
    - Detect pillars with zero applicable rules → add to `excluded_pillars` with reason "no applicable rules"; log at WARNING
    - Compute `PillarScore` per pillar using `compute_pillar_score`; compute `aggregate_score` using `compute_aggregate_score`
    - Call `generate_findings` then sort findings
    - Emit INFO log on completion with `aggregate_score`, `rule_catalog_version`, `duration_ms`
    - Emit DEBUG log per rule result
    - Build and return immutable `EvaluationReport`
    - _Requirements: 2.1, 2.2, 2.5, 2.7, 4.1–4.6, 5.1–5.4, 6.1–6.6, 7.1–7.5, 8.1–8.4, 9.2–9.4_
  - [ ] 9.3 Implement `ScoringConfig` validation logic
    - Empty/None config → default weight 1.0 for all pillars (Requirement 8.2)
    - Raise `ConfigurationError` for weight ≤ 0 identifying pillar name and value (Requirement 8.3)
    - Raise `ConfigurationError` for unrecognized pillar name (Requirement 8.4)
    - _Requirements: 8.1–8.4_
  - [ ]* 9.4 Write unit tests for `EvaluationEngine`
    - Test rule exception is caught, logged, added to `error_rules`, other rules still evaluated
    - Test excluded pillar appears in `excluded_pillars` list with correct reason
    - Test `ConfigurationError` on invalid weight
    - Test `ConfigurationError` on unrecognized pillar name
    - Test INFO log emitted after evaluation (use `caplog` or `logging.handlers`)
    - _Requirements: 2.5, 2.7, 4.5, 4.6, 8.2–8.4, 9.2–9.4_

- [ ] 10. Checkpoint — engine passes all unit tests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Wire up the public API (`scoring_engine/__init__.py`)
  - [ ] 11.1 Implement `score(architecture_description, config) -> EvaluationReport`
    - Instantiate `Parser`, call `parser.parse()` (raises `ParseError`/`ValidationError` on failure)
    - Instantiate `RuleCatalog` and `EvaluationEngine`; call `engine.evaluate(arch, config)`
    - Propagate all `CloudCriticError` subtypes unmodified; wrap unexpected exceptions as `EvaluationError`
    - _Requirements: 10.1_
  - [ ] 11.2 Export all required public symbols from `__init__.py`
    - `score`, `EvaluationReport`, `Finding`, `PillarScore`, `ScoringConfig`, `CloudCriticError`, `ParseError`, `ValidationError`, `ConfigurationError`, `EvaluationError`
    - _Requirements: 10.2_
  - [ ]* 11.3 Write unit tests for the public `score()` API
    - Test happy path: valid JSON input → `EvaluationReport` with correct types
    - Test valid YAML input → same result structure
    - Test `ParseError` raised for malformed input
    - Test `ValidationError` raised for missing required fields
    - Test `ConfigurationError` raised for bad `ScoringConfig`
    - Test import produces no side effects (no log handlers attached to root logger)
    - _Requirements: 10.1–10.3_

- [ ] 12. Write Hypothesis strategies (`tests/strategies.py`)
  - [ ] 12.1 Implement all custom Hypothesis strategies
    - `pillar_strategy()`, `severity_strategy()`, `component_strategy()`, `arch_description_strategy()`, `valid_weights_strategy()`
    - Match signatures and constraints from the design's Testing Strategy section
    - _Requirements: (underpins all property tests)_

- [ ] 13. Write property-based tests (`tests/property/`)
  - [ ]* 13.1 Property 1 & 10 — Parse–serialize round trip and whitespace insensitivity (`test_round_trips.py`)
    - **Property 1: Architecture Description Parse–Serialize Round Trip**
    - **Property 10: Whitespace-Insensitive Parsing**
    - **Validates: Requirements 1.6, 1.7, 1.1, 3.3**
  - [ ]* 13.2 Properties 3 & 4 — Pillar and aggregate score bounds invariant (`test_score_bounds.py`)
    - **Property 3: Pillar Score Bounds Invariant**
    - **Property 4: Aggregate Score Bounds Invariant**
    - **Validates: Requirements 4.1–4.4, 5.1, 5.2**
  - [ ]* 13.3 Property 2 — Evaluation Report serialize–deserialize round trip (`test_round_trips.py`)
    - **Property 2: Evaluation Report Serialize–Deserialize Round Trip**
    - **Validates: Requirements 7.4, 7.5**
  - [ ]* 13.4 Property 5 — Determinism under semantic equivalence (`test_determinism.py`)
    - **Property 5: Determinism Under Semantic Equivalence**
    - **Validates: Requirements 3.1, 3.2, 3.3**
  - [ ]* 13.5 Properties 6 & 7 — Findings correspondence and sort order (`test_findings_inv.py`)
    - **Property 6: Findings Correspond Exclusively to Failed Rules**
    - **Property 7: Findings Sort Order Invariant**
    - **Validates: Requirements 6.3, 6.4, 6.5**
  - [ ]* 13.6 Property 8 — Rule independence under failure (`test_rule_indep.py`)
    - **Property 8: Rule Independence — Failure Does Not Suppress Other Rules**
    - **Validates: Requirements 2.5, 9.2**
  - [ ]* 13.7 Property 9 — Scoring config weight redistribution (`test_weight_redist.py`)
    - **Property 9: Scoring Config Weight Redistribution**
    - **Validates: Requirements 5.3, 5.4**

- [ ] 14. Write concurrency and logging integration tests (`tests/unit/test_engine.py`, `tests/unit/test_api.py`)
  - [ ] 14.1 Write concurrency test: 8 threads × distinct inputs → no cross-contamination
    - Use `concurrent.futures.ThreadPoolExecutor` with 8 workers; assert each result matches its own input
    - _Requirements: 10.4_
  - [ ]* 14.2 Write logging integration tests
    - Assert INFO log entry after evaluation contains `aggregate_score`, `rule_catalog_version`, `duration_ms`
    - Assert `scoring_engine` logger has no handlers at import time
    - _Requirements: 9.3, 9.4, 10.3_

- [ ] 15. Final checkpoint — all tests pass
  - Ensure all tests pass (`pytest tests/ -v`), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery.
- Each task references specific requirements for traceability; consult `requirements.md` for full acceptance criteria.
- Checkpoints ensure incremental validation before proceeding to dependent layers.
- Property tests require Hypothesis (`pip install hypothesis`); each is tagged with its property number and the requirements clause it validates.
- Unit tests validate specific examples and edge cases; property tests validate universal invariants — both are complementary.
- The `scoring_engine` logger must never attach handlers or modify the root logger (Requirement 10.3).
- All scoring arithmetic uses integer-safe round-half-up: `floor(x + 0.5)` — no `round()` built-in (which uses banker's rounding).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "3.1"] },
    { "id": 1, "tasks": ["2.2", "3.2"] },
    { "id": 2, "tasks": ["2.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3"] },
    { "id": 4, "tasks": ["4.4", "4.5"] },
    { "id": 5, "tasks": ["4.6", "6.1"] },
    { "id": 6, "tasks": ["6.2", "7.1"] },
    { "id": 7, "tasks": ["6.3", "7.2"] },
    { "id": 8, "tasks": ["7.3", "8.1"] },
    { "id": 9, "tasks": ["8.2", "9.1"] },
    { "id": 10, "tasks": ["8.3", "9.2"] },
    { "id": 11, "tasks": ["9.3"] },
    { "id": 12, "tasks": ["9.4", "11.1"] },
    { "id": 13, "tasks": ["11.2", "12.1"] },
    { "id": 14, "tasks": ["11.3", "13.1", "13.2", "13.3", "13.4", "13.5", "13.6", "13.7"] },
    { "id": 15, "tasks": ["14.1", "14.2"] }
  ]
}
```
