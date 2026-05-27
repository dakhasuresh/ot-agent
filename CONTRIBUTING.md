# Contributing to ot-agent

Contributions are welcome — particularly:

- New IEC 62443 control mappings for additional device categories
- Additional threat-actor patterns beyond the current 14
- Support for supplementary standards (NIST 800-82, NERC CIP, IEC 61511)
- Improved LLM prompts for classification or control generation
- Bug fixes and test coverage improvements

---

## Getting started

```bash
git clone https://github.com/dakhasuresh/ot-agent.git
cd ot-agent
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Adding device-category controls (Tier 2)

Open `agent/tools.py` and find `_CATEGORY_CONTROLS`.  Add a new entry:

```python
AssetCategory.MY_DEVICE: [
    {
        "clause": "IEC 62443-3-3 SR X.X",
        "text": "Specific actionable control for this device type.",
        "priority": 1,           # 1=mandatory  2=recommended  3=best-practice
        "source": "category_static",
    },
],
```

Add a test in `tests/test_pipeline.py` covering the new category.

---

## Code style

- Python 3.9+ type hints throughout
- `ruff` for linting (`ruff check .`)
- Pydantic v2 models for all I/O
- Async-first (`async def`) for all tool functions
- No external network calls — everything on localhost

---

## Pull request checklist

- [ ] Tests pass: `pytest tests/ -v`
- [ ] Linter clean: `ruff check .`
- [ ] New controls reference real IEC 62443 clauses
- [ ] Existing tests not broken
- [ ] README updated if behaviour changes

---

## Licence

By contributing, you agree your contributions are licensed under MIT.
