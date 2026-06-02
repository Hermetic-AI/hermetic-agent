---
name: code-quality
description: Enforce code quality standards via linting (flake8, ESLint), complexity limits, and style consistency. Use when the user asks to lint code, fix style issues, check complexity, or enforce coding standards.
risk: safe
source: C:\WorkSpace\Coding\Herness Engerneering\harness-rules\.flake8, eslint-boundaries.json
date_added: 2026-06-01
---

# Code Quality — Agent Skill Guide

Enforce consistent code quality standards across Python and TypeScript/React projects using configurable linting rules.

---

## 1. Python Linting (Flake8)

### Configuration (.flake8)

```ini
[flake8]
max-line-length = 120
max-complexity = 10
exclude =
    .git,__pycache__,venv,.venv,env,.env,build,dist,*.egg-info,.pytest_cache,.mypy_cache,.tox
per-file-ignores =
    __init__.py:F401,F824
    tests/*:F401,F811
extend-select = C4,B,Q,W
ignore = E203,E501,W503,Q000,Q001
format = %(row)d:%(col)d: %(code)s: %(text)s
```

### Rules Enabled

| Rule Set | Description |
|----------|-------------|
| `C4` | Comprehensions — best practices for list/set/dict comprehensions |
| `B` | Bugbear — common bugs and stylistic issues |
| `Q` | Quotes — consistent quote style |
| `W` | Warnings — pycodestyle warnings |

### Agent Commands

```bash
# Lint Python source
flake8 src/ --exclude venv,.venv,tests \
  --max-line-length=120 \
  --extend-select=C4,B \
  --ignore=E203,W503

# Check specific file
flake8 src/module/file.py

# List all violations
flake8 src/ --output-format=json | jq '.[].message'

# Auto-fix safe issues (if using flake8-safe-fixes)
flake8 src/ --select=F401 --extend-select=F
```

### Complexity Check

```bash
# Check cyclomatic complexity
flake8 --select=C901 --max-complexity=10 src/

# Find overly complex functions
flake8 --select=C901 src/ | awk -F: '{print $1}' | xargs -I{} grep -n "def " {}
```

---

## 2. TypeScript/React Linting (ESLint + Boundaries)

### ESLint Boundaries Configuration

```json
{
  "plugins": ["boundaries"],
  "rules": {
    "boundaries/element-types": ["error", {
      "default": "nestable",
      "rules": [
        {"from": ["pages"], "allow": ["components", "hooks", "services", "stores", "types", "constants", "utils", "config", "assets"]},
        {"from": ["components"], "allow": ["hooks", "types", "constants", "utils", "assets", "components"]},
        {"from": ["hooks"], "allow": ["utils", "types", "constants", "services", "stores"]},
        {"from": ["services"], "allow": ["types", "constants", "utils", "config", "stores"]},
        {"from": ["stores"], "allow": ["types", "constants", "utils"]},
        {"from": ["utils"], "allow": ["types", "constants", "config"]}
      ]
    }],
    "boundaries/no-absolute-imports": "error",
    "boundaries/no-cycle": "error",
    "boundaries/no-restricted-paths": ["error", {
      "rules": [
        {"from": ["components", "pages"], "forbidden": [{"path": "services"}]},
        {"from": ["utils"], "forbidden": [{"path": "hooks"}, {"path": "stores"}, {"path": "components"}]},
        {"from": ["stores"], "forbidden": [{"path": "services"}]}
      ]
    }]
  }
}
```

### Layer Access Rules

| From Layer | Allowed To |
|------------|------------|
| `pages` | `components`, `hooks`, `services`, `stores`, `types`, `constants`, `utils`, `config`, `assets` |
| `components` | `hooks`, `types`, `constants`, `utils`, `assets`, `components` |
| `hooks` | `utils`, `types`, `constants`, `services`, `stores` |
| `services` | `types`, `constants`, `utils`, `config`, `stores` |
| `stores` | `types`, `constants`, `utils` |
| `utils` | `types`, `constants`, `config` |

### Forbidden Patterns

```json
// React components CANNOT import services directly
{"from": ["components", "pages"], "forbidden": [{"path": "services"}]}

// Utils cannot depend on hooks/stores/components
{"from": ["utils"], "forbidden": [{"path": "hooks"}, {"path": "stores"}, {"path": "components"}]}

// Stores cannot depend on services
{"from": ["stores"], "forbidden": [{"path": "services"}]}
```

### Agent Commands

```bash
# Run ESLint
npm run lint

# Check specific file
npx eslint src/components/MyComponent.tsx

# Check boundaries only
npx eslint --rule 'boundaries/element-types: error' src/

# Auto-fix
npm run lint -- --fix
```

---

## 3. File Complexity Limits

### Per-Module Limits

| Module Type | Max Lines | Max Function Length | Max Arguments |
|-------------|-----------|---------------------|---------------|
| `*.controller` | 300 | 30 | 7 |
| `*.service` | 300 | 50 | 5 |
| `*.repository` | 300 | 40 | 5 |

### Check File Lengths

```bash
# Python: find files exceeding 300 lines
find src -name "*.py" -exec wc -l {} \; | awk '{if($1 > 300) print $2 ": " $1 " lines"}'

# TypeScript: find files exceeding 500 lines
find src -name "*.ts" -o -name "*.tsx" | xargs wc -l | awk '{if($1 > 500) print $2 ": " $1 " lines"}'
```

---

## 4. Usage in Different Languages

### Python Project

```bash
# Full quality check
flake8 src/ --exclude venv,.venv,tests \
  --max-line-length=120 \
  --extend-select=C4,B \
  --ignore=E203,W503

# With complexity check
flake8 src/ --select=C901 --max-complexity=10
```

### TypeScript/React Project

```bash
# Full lint with boundaries
npm run lint

# Type check
npx tsc --noEmit

# Combined check
npm run lint && npx tsc --noEmit
```

---

## 5. Integration with CI/CD

Add to `.github/workflows/lint.yml`:

```yaml
- name: Run Flake8
  run: flake8 src/ --exclude venv --max-line-length=120 --extend-select=C4,B

- name: Run ESLint
  run: npm run lint

- name: Check file sizes
  run: find src -name "*.py" -exec wc -l {} \; | awk '{if($1 > 300) exit 1}'
```

---

## 6. Quick Fix Commands

```bash
# Fix Python import order
isort src/

# Fix Python formatting
black src/

# Fix ESLint issues
npm run lint -- --fix

# Fix TypeScript issues
npx tsc --noEmit --fix
```

---

## 7. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Linting violations found |
| 2 | Configuration error |

---

## 8. When to Use This Skill

- User asks to "lint code" or "check code style"
- User asks to "fix lint errors" or "address flake8/eslint warnings"
- User asks to "enforce code quality standards"
- User asks to "check complexity" or "reduce cyclomatic complexity"
- User asks to "fix import order" or "organize imports"
- Before committing code or creating a PR
