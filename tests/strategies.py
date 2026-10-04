"""Hypothesis strategies for the CloudCritic scoring engine."""

from hypothesis import strategies as st

_AWS_KEYWORDS = [
    "encryption", "iam", "vpc", "waf", "kms", "multi-az", "backup",
    "failover", "cloudwatch", "autoscaling", "cache", "cdn", "load balancer",
    "reserved", "spot", "lifecycle", "monitoring", "logging", "alarm",
    "graviton", "serverless", "rightsizing",
]

# Arbitrary printable text, 1–2000 characters.
architecture_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=2000,
)

# Text guaranteed to contain at least one AWS keyword.
architecture_with_keywords = st.builds(
    lambda base, kw: base[:500] + " " + kw + " " + base[500:],
    base=architecture_text,
    kw=st.sampled_from(_AWS_KEYWORDS),
)
