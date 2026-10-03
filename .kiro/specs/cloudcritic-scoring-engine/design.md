# Design Document: CloudCritic Scoring Engine

## Overview

The CloudCritic Scoring Engine is a deterministic, pure-Python library that ingests a structured AWS architecture description (JSON or YAML) and produces an `EvaluationReport` capturing per-pillar scores, a weighted aggregate score, and a prioritised list of remediation findings — all derived exclusively from the input and the versioned Rule Catalog.

### Goals

- **Determinism first**: identical inputs must yield byte-identical reports across invocations, Python processes, and time.
- **Clean public API**: a single `score()` entry-point, typed return values, and importable exception hierarchy.
- **Extensible rule catalog**: rules are independently versioned, pillar-scoped, and self-contained so new checks can be added without touching evaluation logic.
- **CI/CD friendly**: no side-effects at import time, no network calls, no global state, thread-safe.

### Non-Goals

- The engine does not fetch live AWS account data; it evaluates only what is described in the input document.
- The engine does not provide a UI or CLI (consumers build those on top of the public API).
- The engine does not store evaluation history or compare across runs (consumers are responsible for persistence).

---

## Architecture

The engine is composed of five layers that interact in a strict one-way dependency direction:

```
┌──────────────────────────────────────────────────────┐
│                   Public API Layer                   │
│         score(architecture_description, config)      │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│                  Orchestrator                        │
│  EvaluationEngine — coordinates the evaluation flow  │
└──────┬──────────┬──────────────────┬─────────────────┘
       │          │                  │
┌──────▼──┐  ┌────▼──────┐  ┌───────▼──────────────────┐
│ Parser  │  │  Rule     │  │   Scorer / Reporter      │
│ Layer   │  │  Catalog  │  │   (score + findings)     │
└──────┬──┘  └────┬──────┘  └───────┬──────────────────┘
       │          │                  │
┌──────▼──────────▼──────────────────▼──────────────────┐
│                   Domain Models                       │
│  ArchitectureDescription · RuleResult · Finding       │
│  PillarScore · EvaluationReport · ScoringConfig       │
└───────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Schema validation library | `pydantic` v2 | Runtime type validation with clear error messages; generates JSON schema for documentation |
| YAML parsing | `PyYAML` (`safe_load`) | Standard library complement; `safe_load` prevents arbitrary code execution |
| Rule storage | Python dataclasses in a versioned catalog module | No external DB dependency; easy to diff/audit in VCS |
| Scoring arithmetic | Integer-safe round-half-up via `floor(x + 0.5)` | Matches requirement spec exactly; no floating-point ambiguity |
| Concurrency | Stateless functions + thread-local evaluation context | Thread-safety without locks; supports concurrent `score()` calls |
| Property-based testing | `hypothesis` | Mature Python PBT library, integrates with `pytest` |

---

## Components and Interfaces

### 2.1 Public API (`scoring_engine/__init__.py`)

```python
def score(
    architecture_description: str,
    config: Optional[ScoringConfig] = None,
) -> EvaluationReport:
    """
    Parse, validate, evaluate, and score an AWS architecture description.

    Raises:
        ValidationError  – input exceeds size limit or fails schema validation
        ParseError       – input is syntactically malformed JSON/YAML
        ConfigurationError – ScoringConfig contains invalid weights or pillar names
        EvaluationError  – unrecoverable internal failure (rule catalog unavailable)
    """
```

Exported symbols (all importable from `scoring_engine`):
`score`, `EvaluationReport`, `Finding`, `PillarScore`, `ScoringConfig`,
`CloudCriticError`, `ParseError`, `ValidationError`, `ConfigurationError`, `EvaluationError`

### 2.2 Parser (`scoring_engine/parser.py`)

Responsible for:
1. UTF-8 size gate (raises `ValidationError` if > 10 MiB)
2. Format detection (JSON first, then YAML fallback)
3. Syntactic parse — catches `json.JSONDecodeError` / `yaml.YAMLError`, converts to `ParseError` with line/column/message
4. Schema validation — Pydantic model validates required top-level fields, produces `ValidationError` listing missing fields
5. Pretty-printer — `PrettyPrinter.to_json(obj)` serializes with sorted keys and 2-space indent

```python
class Parser:
    def parse(self, raw: str) -> ArchitectureDescription: ...

class PrettyPrinter:
    @staticmethod
    def to_json(obj: Any) -> str: ...   # sorted keys, 2-space indent
```

### 2.3 Rule Catalog (`scoring_engine/catalog/`)

```
catalog/
  __init__.py        ← exports RuleCatalog, CATALOG_VERSION
  version.py         ← CATALOG_VERSION = "1.0.0"
  rules/
    operational_excellence.py
    security.py
    reliability.py
    performance_efficiency.py
    cost_optimization.py
    sustainability.py
```

Each pillar module exports a list of `Rule` instances. `RuleCatalog` aggregates them:

```python
@dataclass(frozen=True)
class Rule:
    rule_id: str          # e.g. "SEC-001"
    pillar: Pillar        # enum member
    severity: Severity    # CRITICAL | HIGH | MEDIUM | LOW
    description: str
    remediation: str      # may be empty string → engine uses fallback text
    evaluate: Callable[[ArchitectureDescription], RuleResult]

class RuleCatalog:
    version: str          # semver from version.py
    rules: tuple[Rule, ...] = field(init=False)  # immutable, ordered

    def rules_for_pillar(self, pillar: Pillar) -> tuple[Rule, ...]: ...
    def get_rule(self, rule_id: str) -> Rule: ...
```

The `evaluate` callable is a pure function — given an `ArchitectureDescription`, it returns a `RuleResult` (pass/fail + evidence snippet). Pure functions are the backbone of determinism.

### 2.4 Evaluation Engine (`scoring_engine/engine.py`)

```python
class EvaluationEngine:
    def __init__(self, catalog: RuleCatalog) -> None: ...

    def evaluate(
        self,
        arch: ArchitectureDescription,
        config: ScoringConfig,
    ) -> EvaluationReport:
        """
        Runs all rules, aggregates scores, builds findings.
        Each rule is evaluated independently; exceptions are caught,
        logged at ERROR, and added to error_rules — evaluation continues.
        """
```

Evaluation flow (all within a single call, no shared mutable state):

```
validate config
  → for each pillar:
      for each rule in catalog:
          try: result = rule.evaluate(arch)
          except Exception: log ERROR, append to error_rules, continue
      pillar_score = _compute_pillar_score(results)
  → aggregate_score = _compute_aggregate(pillar_scores, config)
  → findings = _generate_findings(failed_results)
  → sort findings (CRITICAL→HIGH→MEDIUM→LOW, ties by pillar name asc)
  → return EvaluationReport(...)
```

### 2.5 Scorer (`scoring_engine/scorer.py`)

Stateless functions for score arithmetic:

```python
def compute_pillar_score(passing: int, total: int) -> int:
    """floor((passing / total) * 100 + 0.5) — round-half-up."""

def compute_aggregate_score(
    pillar_scores: dict[Pillar, int],
    weights: dict[Pillar, float],
) -> int:
    """Weighted average with proportional weight redistribution for excluded pillars."""
```

### 2.6 Finding Generator (`scoring_engine/findings.py`)

```python
def generate_findings(
    rule_results: Sequence[RuleResult],
    catalog: RuleCatalog,
) -> list[Finding]:
    """
    One Finding per failed RuleResult.
    Fallback remediation: "No remediation guidance available for rule {rule_id}"
    """
```

### 2.7 Exceptions (`scoring_engine/exceptions.py`)

```
CloudCriticError (base, RuntimeError)
├── ParseError          – syntax failures (line, column, message)
├── ValidationError     – schema failures (list of field errors) or size limit
├── ConfigurationError  – invalid ScoringConfig (pillar name, weight value)
└── EvaluationError     – catalog load failure
```

### 2.8 Logging

All logging uses Python's standard `logging` module. The engine obtains `logger = logging.getLogger("scoring_engine")` and does **not** attach any handlers or modify the root logger — handlers are the caller's responsibility.

| Level | When |
|---|---|
| `DEBUG` | Per-rule evaluation result (rule_id, pass/fail, evidence) |
| `INFO` | Evaluation lifecycle: start, complete (aggregate_score, catalog_version, duration_ms) |
| `WARNING` | Non-fatal issues: excluded pillars, missing remediation text |
| `ERROR` | Rule evaluation exception (rule_id, exception message) |

---

## Data Models

All models live in `scoring_engine/models.py` and use Python `dataclasses` (stdlib) for internal representation. Pydantic is used only at the parser boundary to validate incoming JSON/YAML against the `ArchitectureDescription` schema.

### Pillar (Enum)

```python
class Pillar(str, Enum):
    OPERATIONAL_EXCELLENCE = "Operational Excellence"
    SECURITY               = "Security"
    RELIABILITY            = "Reliability"
    PERFORMANCE_EFFICIENCY = "Performance Efficiency"
    COST_OPTIMIZATION      = "Cost Optimization"
    SUSTAINABILITY         = "Sustainability"
```

### Severity (Enum)

```python
class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"

    # Ordering for sort: CRITICAL=0, HIGH=1, MEDIUM=2, LOW=3
    def sort_key(self) -> int: ...
```

### ArchitectureDescription

```python
@dataclass(frozen=True)
class ArchitectureDescription:
    # Required top-level fields (validated by Pydantic at parse time)
    name: str
    description: str
    components: tuple[Component, ...]
    # Any extra fields captured during parsing are preserved in extras
    extras: frozenset[tuple[str, Any]] = field(default_factory=frozenset)
```

### Component

```python
@dataclass(frozen=True)
class Component:
    id: str
    type: str                          # e.g. "aws::s3::bucket"
    name: str
    properties: frozenset[tuple[str, Any]]  # immutable key-value pairs
```

### RuleResult

```python
@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    pillar: Pillar
    passed: bool
    evidence: str   # snippet from ArchitectureDescription; "no evidence found" sentinel when empty
```

### Finding

```python
@dataclass(frozen=True)
class Finding:
    pillar: Pillar
    rule_id: str
    severity: Severity
    impacted_components: tuple[str, ...]  # at least one component name
    description: str                      # ≥10 words
    remediation: str                      # includes AWS service name or WAF best practice ref
```

### PillarScore (public export)

```python
@dataclass(frozen=True)
class PillarScore:
    pillar: Pillar
    score: int           # 0–100 inclusive
    passing_rules: int
    total_rules: int
```

### ScoringConfig

```python
@dataclass
class ScoringConfig:
    weights: dict[Pillar, float] = field(default_factory=dict)
    # Empty dict → all weights default to 1.0
```

### EvaluationReport

```python
@dataclass(frozen=True)
class EvaluationReport:
    rule_catalog_version: str                  # semver
    schema_version: str                        # semver of report format
    pillar_scores: dict[str, int]              # Pillar.value → score int
    aggregate_score: int                       # 0–100
    total_rules: int
    passing_rules: int
    failing_rules: int
    excluded_pillars: list[dict[str, str]]     # [{"pillar": ..., "reason": ...}]
    error_rules: list[str]                     # rule_ids that errored
    findings: list[Finding]                    # sorted by severity then pillar name

    def to_dict(self) -> dict[str, Any]:
        """Returns a plain dict serializable by Python's standard json.dumps()."""
```

### JSON Serialization Contract

`EvaluationReport.to_dict()` produces a structure that `json.dumps()` can handle without custom encoders. `PrettyPrinter.to_json(report.to_dict())` outputs canonical JSON with sorted keys and 2-space indentation.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Architecture Description Parse–Serialize Round Trip

*For any* valid `ArchitectureDescription` object, serializing it to canonical JSON via the `PrettyPrinter` and then re-parsing the result SHALL produce an internal representation where every field name, field value, and structural nesting level is identical to the original.

**Validates: Requirements 1.6, 1.7**

---

### Property 2: Evaluation Report Serialize–Deserialize Round Trip

*For any* `EvaluationReport`, serializing it to canonical JSON via `PrettyPrinter.to_json()` and then deserializing with `json.loads()` SHALL produce a Python dict with identical field names, field values, and field types to the output of `report.to_dict()`.

**Validates: Requirements 7.4, 7.5**

---

### Property 3: Pillar Score Bounds Invariant

*For any* `ArchitectureDescription` and any `ScoringConfig` with valid positive weights, every `PillarScore.score` in the resulting `EvaluationReport` SHALL be an integer in the range [0, 100] inclusive.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

---

### Property 4: Aggregate Score Bounds Invariant

*For any* `ArchitectureDescription` and any `ScoringConfig` with valid positive weights, the `aggregate_score` in the resulting `EvaluationReport` SHALL be an integer in the range [0, 100] inclusive.

**Validates: Requirements 5.1, 5.2**

---

### Property 5: Determinism Under Semantic Equivalence

*For any* pair of `ArchitectureDescription` strings that are semantically equivalent (same fields and values, differing only in key ordering or whitespace), the `score()` function SHALL produce `EvaluationReport` objects with identical `pillar_scores`, `aggregate_score`, and `findings` (same length, same content).

**Validates: Requirements 3.1, 3.2, 3.3**

---

### Property 6: Findings Correspond Exclusively to Failed Rules

*For any* `ArchitectureDescription`, the set of `rule_id` values in `EvaluationReport.findings` SHALL be exactly the set of `rule_id` values from `RuleResult` objects with `passed == False`, with no `rule_id` from a passing `RuleResult` appearing in `findings`.

**Validates: Requirements 6.3, 6.4**

---

### Property 7: Findings Sort Order Invariant

*For any* `EvaluationReport`, the `findings` list SHALL be ordered such that no finding with a lower-priority severity (e.g. HIGH) appears before a finding with a higher-priority severity (e.g. CRITICAL), and among findings of equal severity, no finding with a lexicographically greater pillar name appears before one with a lexicographically smaller pillar name.

**Validates: Requirements 6.5**

---

### Property 8: Rule Independence — Failure Does Not Suppress Other Rules

*For any* `ArchitectureDescription` where exactly one rule raises an internal exception during evaluation, the `EvaluationReport` SHALL contain `Rule_Result` entries for all other rules (i.e., `total_rules - 1` results outside `error_rules`), and the errored rule's `rule_id` SHALL appear in `error_rules`.

**Validates: Requirements 2.5, 9.2**

---

### Property 9: Scoring Config Weight Redistribution

*For any* `ArchitectureDescription` where at least one pillar has no applicable rules (and is therefore excluded), the `aggregate_score` computed with default equal weights SHALL equal the arithmetic mean of the remaining included `pillar_scores`, rounded with round-half-up rounding.

**Validates: Requirements 5.3, 5.4**

---

### Property 10: Whitespace-Insensitive Parsing

*For any* valid architecture description JSON string, adding or removing whitespace (spaces, newlines, tabs) between tokens SHALL produce the same parsed `ArchitectureDescription` with identical field names, field values, and structural nesting.

**Validates: Requirements 1.1, 3.3**

---

## Error Handling

### Error Hierarchy

All errors derive from `CloudCriticError(RuntimeError)` so callers can catch the base class or specific subtypes:

```
CloudCriticError
├── ParseError(line: int, column: int, message: str)
├── ValidationError(errors: list[str])   # field names for schema errors; size for size limit
├── ConfigurationError(pillar: str, value: Any, reason: str)
└── EvaluationError(message: str)        # catalog load failure
```

### Error Decision Table

| Scenario | Error type raised | Partial output |
|---|---|---|
| Input > 10 MiB | `ValidationError` | None |
| Malformed JSON/YAML | `ParseError` | None |
| Missing required schema fields | `ValidationError` | None |
| Invalid pillar weight in ScoringConfig | `ConfigurationError` | None |
| Unrecognized pillar name in ScoringConfig | `ConfigurationError` | None |
| Rule Catalog unavailable | `EvaluationError` | None |
| Individual rule raises exception | logged at ERROR; rule added to `error_rules` | EvaluationReport with partial results |

### Internal Rule Errors

Internal rule errors are **non-fatal** by design. The engine catches `Exception` per rule, logs at `ERROR`, excludes the rule from pillar score arithmetic, and appends its `rule_id` to `error_rules`. This preserves the "evaluate independently" guarantee from Requirement 2.5.

---

## Testing Strategy

### Dual Testing Approach

The testing strategy combines **example-based unit tests** (specific scenarios, edge cases, integration points) with **property-based tests** (universal invariants using [Hypothesis](https://hypothesis.works/)) for comprehensive coverage.

### Property-Based Test Configuration

- Library: **Hypothesis** (`pip install hypothesis`)
- Minimum iterations: **100 per property** (Hypothesis default; can raise with `settings(max_examples=500)`)
- Each property test is tagged with a comment referencing the corresponding design property:

```python
# Feature: cloudcritic-scoring-engine, Property 1: Architecture Description Parse–Serialize Round Trip
@given(arch_description_strategy())
@settings(max_examples=200)
def test_parse_serialize_round_trip(arch: ArchitectureDescription) -> None:
    ...
```

### Hypothesis Strategies

Custom strategies are defined in `tests/strategies.py`:

```python
from hypothesis import strategies as st

def pillar_strategy() -> st.SearchStrategy[Pillar]:
    return st.sampled_from(list(Pillar))

def severity_strategy() -> st.SearchStrategy[Severity]:
    return st.sampled_from(list(Severity))

def component_strategy() -> st.SearchStrategy[dict]:
    return st.fixed_dictionaries({
        "id":         st.text(min_size=1, max_size=50),
        "type":       st.text(min_size=1, max_size=100),
        "name":       st.text(min_size=1, max_size=100),
        "properties": st.dictionaries(st.text(min_size=1), st.one_of(st.text(), st.integers(), st.booleans())),
    })

def arch_description_strategy() -> st.SearchStrategy[dict]:
    return st.fixed_dictionaries({
        "name":        st.text(min_size=1, max_size=100),
        "description": st.text(min_size=1, max_size=500),
        "components":  st.lists(component_strategy(), min_size=1, max_size=20),
    })

def valid_weights_strategy() -> st.SearchStrategy[dict[str, float]]:
    return st.dictionaries(
        st.sampled_from([p.value for p in Pillar]),
        st.floats(min_value=0.001, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1,
    )
```

### Test Organisation

```
tests/
  strategies.py          ← Hypothesis strategies
  unit/
    test_parser.py        ← Parser, PrettyPrinter (unit + property tests)
    test_scorer.py        ← compute_pillar_score, compute_aggregate_score
    test_findings.py      ← generate_findings, sort order
    test_catalog.py       ← RuleCatalog load, version format
    test_engine.py        ← EvaluationEngine integration
    test_exceptions.py    ← exception hierarchy, error fields
    test_api.py           ← public score() function
  property/
    test_round_trips.py   ← Properties 1, 2, 10
    test_score_bounds.py  ← Properties 3, 4
    test_determinism.py   ← Property 5
    test_findings_inv.py  ← Properties 6, 7
    test_rule_indep.py    ← Property 8
    test_weight_redist.py ← Property 9
  conftest.py             ← shared fixtures, example architectures
```

### Example-Based Test Coverage

| Area | What to test |
|---|---|
| Parser | Valid JSON, valid YAML, extra fields ignored, parse error fields, schema error field list, size limit boundary (exactly 10 MiB, 10 MiB + 1 byte) |
| Rule Catalog | All six pillars have at least one rule, version format is semver, each rule has non-empty `rule_id`, `description`, `severity` |
| Scoring | 0 of N → score 0, N of N → score 100, k of N → exact formula, weight redistribution with one excluded pillar |
| Findings | Passing rule → no finding, failing rule with no remediation → fallback text, finding has ≥1 impacted component, description ≥10 words |
| Config | Empty ScoringConfig → all weights 1.0, negative weight → ConfigurationError, unknown pillar → ConfigurationError |
| Concurrency | 8 threads × distinct inputs → no cross-contamination (uses `threading.Thread` + `concurrent.futures`) |
| Logging | INFO entry contains aggregate_score, catalog_version, duration_ms after evaluation |
