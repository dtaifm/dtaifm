# Pre-release checklist

Run through this list before tagging and publishing a release.

## 1. Test suite

```bash
pytest
```

All tests must pass. No `xfail` / skip without an explanation in the test docstring.

## 2. Lint

```bash
ruff check dtaifm tests
```

No findings. If a finding is intentional, add the rule to the `ignore` list in `pyproject.toml` with a comment.

## 3. Package build

```bash
rm -rf dist/ build/
python -m build --wheel --sdist
```

Both the wheel and sdist must build with no errors and no warnings about missing files.

Verify the wheel includes the demo fixtures:

```bash
python -c "
import zipfile
z = zipfile.ZipFile('dist/dtaifm-X.Y.Z-py3-none-any.whl')
names = z.namelist()
for needle in ('_demo/smart_home/constraints.yaml', '_demo/network_automation/state.json'):
    assert any(needle in n for n in names), f'missing: {needle}'
print('demo fixtures bundled OK')
"
```

## 4. Wheel smoke test

Install the wheel into a clean virtualenv and verify the CLI:

```bash
python -m venv /tmp/dtaifm-smoke
/tmp/dtaifm-smoke/bin/pip install dist/dtaifm-X.Y.Z-py3-none-any.whl
/tmp/dtaifm-smoke/bin/dtaifm --help
/tmp/dtaifm-smoke/bin/dtaifm teachers --json | python -c "
import json, sys
d = json.load(sys.stdin)
assert {'mock','anthropic','openai','ollama','lemonade'}.issubset({i['name'] for i in d})
print('teachers OK')
"
```

## 5. CLI demo smoke tests

Both built-in demos must run end to end from the installed wheel with no extra arguments:

```bash
/tmp/dtaifm-smoke/bin/dtaifm demo smart_home
/tmp/dtaifm-smoke/bin/dtaifm demo network_automation
```

Each output must end with `RESULT: PASSED`.

Programmatic check:

```bash
/tmp/dtaifm-smoke/bin/dtaifm demo smart_home --json \
  | python -c "import json, sys; d=json.load(sys.stdin); assert d['replay']['success']; print('demo replay OK')"
```

## 6. Docs links

Walk every link in `README.md` and every file under `docs/`. Confirm:

- All inter-doc links resolve.
- All example file paths exist (e.g. `examples/smart_rules/constraints.yaml`).
- All command examples copy-paste cleanly.

Quick manual scan:

```bash
grep -rEo "\(([^)]+\.(md|yaml|json|py))\)" docs/ README.md | sort -u
```

For each path printed, confirm the file exists.

## 7. Version numbers

Confirm the following all agree:

- `dtaifm/__init__.py` → `__version__ = "X.Y.Z"`
- `pyproject.toml` → `[project] version = "X.Y.Z"`
- `CHANGELOG.md` → top section header matches `X.Y.Z`
- The git tag you intend to create (`vX.Y.Z`)
- The wheel filename produced in step 3 (`dtaifm-X.Y.Z-py3-none-any.whl`)

## 8. Changelog entry

`CHANGELOG.md` must have a `## [X.Y.Z] — YYYY-MM-DD` section. Move "Unreleased" content into it; create a fresh `## [Unreleased]` block above for ongoing work.

Every public-surface change in the release should be mentioned.

## 9. Tag and push

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

## 10. Publish

```bash
python -m twine upload dist/*
```

For a pre-release / RC:

```bash
python -m twine upload --repository testpypi dist/*
```

## 11. Post-release

- Confirm `pip install dtaifm==X.Y.Z` works in a fresh environment.
- Run `dtaifm demo smart_home` from that fresh install one more time.
- Open the next-version planning issue with anything that was deferred from this release.
