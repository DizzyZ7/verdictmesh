# Evidence pipeline

VerdictMesh 0.5.0 adds an autonomous evidence collection layer before the forecast council.

Flow:

```text
market question
→ search query
→ GDELT article list
→ URL deduplication
→ authority and freshness scoring
→ evidence package
→ forecast request
→ forecast council
```

The collector is deterministic and stores the full package for later audit.
