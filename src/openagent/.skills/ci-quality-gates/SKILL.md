---
name: ci-quality-gates
description: Configure and enforce CI/CD quality gates for Python, Java, and TypeScript projects. Use when setting up CI pipelines, configuring quality checks for pull requests, or troubleshooting CI failures.
risk: safe
source: C:\WorkSpace\Coding\Herness Engerneering\harness-rules\quality-gates.yml
date_added: 2026-06-01
---

# CI Quality Gates — Agent Skill Guide

Configure and enforce quality gates in CI/CD pipelines for consistent code quality across Python, Java, and TypeScript projects.

---

## 1. Quality Gates Overview

Quality gates are automated checks that must pass before code can be merged. Each gate enforces a specific quality dimension.

### Standard Gates

| Gate | Purpose | Blocking |
|------|---------|----------|
| Linting | Code style compliance | Yes |
| Type Checking | Type safety | Yes |
| Unit Tests | Functional correctness | Yes |
| Coverage | Test completeness | Yes |
| Security Scan | Vulnerability detection | Yes |
| Duplication | Code reuse | No |
| Complexity | Code maintainability | No |

---

## 2. Python Quality Gates

### GitHub Actions Configuration

```yaml
name: Quality Gates

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  python-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install flake8 interrogate pylint mypy pytest pytest-cov

      - name: Run Flake8
        run: |
          flake8 src/ --exclude venv,.venv,tests \
            --max-line-length=120 \
            --extend-select=C4,B \
            --ignore=E203,W503

      - name: Check file line counts
        run: |
          find src -name "*.py" -exec wc -l {} \; | \
          awk '{if($1 > 300) print $2 ":" $1 " lines - EXCEEDS 300"}'

      - name: Run interrogate (docstring coverage)
        run: |
          interrogate src/ -v --fail-under=80

      - name: Run mypy (type checking)
        run: |
          mypy src/ --ignore-missing-imports --disallow-untyped-defs

      - name: Run pytest with coverage
        run: |
          pytest tests/ -v --cov=src --cov-fail-under=70
```

### Gate Specifications

| Gate | Tool | Threshold | Command |
|------|------|-----------|---------|
| Linting | flake8 | 0 violations | `flake8 src/ --exclude venv --max-line-length=120` |
| Type Check | mypy | 0 errors | `mypy src/ --ignore-missing-imports` |
| Docstrings | interrogate | ≥ 80% | `interrogate src/ -v --fail-under=80` |
| Unit Tests | pytest | ≥ 70% | `pytest tests/ --cov=src --cov-fail-under=70` |
| Complexity | flake8 C901 | ≤ 10 | `flake8 --select=C901 --max-complexity=10` |

---

## 3. Java Quality Gates

### GitHub Actions Configuration

```yaml
name: Quality Gates

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  java-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'

      - name: Cache Maven
        uses: actions/cache@v3
        with:
          path: ~/.m2/repository
          key: ${{ runner.os }}-maven-${{ hashFiles('**/pom.xml') }}

      - name: Run Checkstyle
        run: mvn checkstyle:check

      - name: Run ArchUnit
        run: mvn test -Dtest=ArchitectureTest

      - name: Check class line counts
        run: |
          find src/main -name "*.java" -exec wc -l {} \; | \
          awk '{if($1 > 300) print $2 ":" $1 " lines - EXCEEDS 300"}'

      - name: Run PMD CPD (duplicate code)
        run: mvn pmd:cpd

      - name: Run tests with coverage
        run: mvn test jacoco:report
        env:
          JACOCO_THRESHOLD: 70
```

### Gate Specifications

| Gate | Tool | Threshold | Command |
|------|------|-----------|---------|
| Style | Checkstyle | 0 violations | `mvn checkstyle:check` |
| Architecture | ArchUnit | 0 failures | `mvn test -Dtest=ArchitectureTest` |
| Unit Tests | JUnit + JaCoCo | ≥ 70% | `mvn test jacoco:report` |
| Duplication | PMD CPD | < 3% | `mvn pmd:cpd` |

### JaCoCo Configuration (pom.xml)

```xml
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.10</version>
    <configuration>
        <rules>
            <rule>
                <element>BUNDLE</element>
                <limits>
                    <limit>
                        <counter>LINE</counter>
                        <value>COVEREDRATIO</value>
                        <minimum>0.70</minimum>
                    </limit>
                    <limit>
                        <counter>BRANCH</counter>
                        <value>COVEREDRATIO</value>
                        <minimum>0.70</minimum>
                    </limit>
                </limits>
            </rule>
        </rules>
    </configuration>
</plugin>
```

---

## 4. TypeScript/React Quality Gates

### GitHub Actions Configuration

```yaml
name: Quality Gates

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  typescript-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run ESLint
        run: npm run lint

      - name: Check file line counts
        run: |
          find src -name "*.ts" -o -name "*.tsx" | \
          xargs wc -l | awk '{if($1 > 500) print $2 ":" $1 " lines - EXCEEDS 500"}'

      - name: Run TypeScript compiler
        run: npx tsc --noEmit

      - name: Run Jest with coverage
        run: |
          npm test -- --coverage \
            --coverageThreshold='{"global":{"branches":70,"functions":70,"lines":70,"statements":70}}'
```

### Gate Specifications

| Gate | Tool | Threshold | Command |
|------|------|-----------|---------|
| Linting | ESLint | 0 violations | `npm run lint` |
| Type Check | TypeScript | 0 errors | `npx tsc --noEmit` |
| Unit Tests | Jest | ≥ 70% | `npm test -- --coverage` |
| File Size | wc | < 500 lines | `find src -name "*.ts" -o -name "*.tsx"` |

---

## 5. Gate Failure Response

### When a Gate Fails

```
┌─────────────────────────────────────────────────────────────┐
│  QUALITY GATE FAILED: [Gate Name]                          │
├─────────────────────────────────────────────────────────────┤
│  Issue: [Description of what failed]                       │
│  Location: [File:Line or Module]                            │
│  Threshold: [Expected vs Actual]                            │
├─────────────────────────────────────────────────────────────┤
│  Actions:                                                   │
│  1. Fix the immediate issue                                 │
│  2. Check for similar issues in the same file/module        │
│  3. Run the full local test suite                           │
│  4. Push changes and verify CI passes                       │
└─────────────────────────────────────────────────────────────┘
```

### Quick Fix Commands

```bash
# Python: Auto-fix what can be auto-fixed
black src/           # Formatting
isort src/           # Import order
flake8 --fix src/    # Safe fixes

# Python: Check what needs manual intervention
flake8 src/ | grep -v "F401\|F811"  # Ignore unused imports for now

# Java: Auto-format
mvn spotless:apply

# TypeScript: Auto-fix
npm run lint -- --fix
```

---

## 6. Coverage Enforcement

### Per-Module Coverage Targets

| Module | Critical | Target |
|--------|----------|--------|
| `auth/**` | 🔴 | 90% |
| `payment/**` | 🔴 | 90% |
| `services/**` | 🟡 | 80% |
| `repositories/**` | 🟡 | 75% |
| `controllers/**` | 🟡 | 70% |
| `utils/**` | 🟢 | 60% |

### Coverage Reports

```bash
# Python HTML report
pytest tests/ --cov=src --cov-report=html --cov-report=term
# Open: htmlcov/index.html

# Java HTML report
mvn test jacoco:report
# Open: target/site/jacoco/index.html

# TypeScript HTML report
npm test -- --coverage --coverageReporters=lcov
# Open: coverage/lcov-report/index.html
```

---

## 7. PR Integration

### Required Status Checks

Configure these as required status checks in branch protection rules:

```yaml
# GitHub: Required checks (configured in Settings > Branches > Protection rules)
required_status_checks:
  strict: true
  contexts:
    - python-quality/lint
    - python-quality/type-check
    - python-quality/tests
    - java-quality/checkstyle
    - java-quality/archunit
    - java-quality/tests
    - typescript-quality/lint
    - typescript-quality/type-check
    - typescript-quality/tests
```

### PR Quality Report

```markdown
## Quality Gates Report

| Gate | Status | Details |
|------|--------|---------|
| Linting | ✅ Pass | 0 violations |
| Type Check | ✅ Pass | 0 errors |
| Unit Tests | ✅ Pass | 85% coverage |
| Architecture | ✅ Pass | All rules passed |

### Coverage by Module

| Module | Coverage | Status |
|--------|----------|--------|
| auth | 92% | ✅ |
| payment | 89% | ✅ |
| services | 82% | ✅ |
```

---

## 8. Customization

### Adjusting Thresholds

Edit `.github/workflows/quality-gates.yml` to adjust:

```yaml
# Change coverage threshold
--cov-fail-under=80  # Increase from 70 to 80

# Change line length
--max-line-length=100  # Stricter than 120

# Add more ESLint rules
--rule 'complexity: error'
--rule 'no-unused-vars: error'
```

### Adding New Gates

```yaml
# Example: Add security scan
- name: Run Bandit (Python security)
  run: pip install bandit && bandit -r src/

# Example: Add Trivy (container security)
- name: Run Trivy
  run: trivy fs --severity HIGH,CRITICAL .
```

---

## 9. Troubleshooting CI Failures

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError` | Missing dependency | Add to `requirements.txt` / `package.json` |
| Coverage dropped | New code without tests | Add tests for new code |
| Flake8 violations | Style changes needed | Run `black src/` |
| Timeout on tests | Slow tests | Use `pytest -x` to fail fast |
| `npm ci` fails | Lock file mismatch | Run `npm install` locally and commit |

### Debug Commands

```bash
# Replicate CI locally
docker run --rm -v $(pwd):/app ghcr.io/actions/checkout@v4
docker run --rm -v $(pwd):/app python:3.11 bash -c "pip install flake8 && flake8 src/"

# Run with verbose output
pytest tests/ -vv --tb=long
npm test -- --verbose --coverage

# Check specific failing gate
mvn test -Dtest=ArchitectureTest -X  # Maven debug
```

---

## 10. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All quality gates passed |
| 1 | One or more gates failed |
| 2 | Configuration error |

---

## 11. When to Use This Skill

- User asks to "set up CI quality gates" or "configure quality checks"
- User asks to "troubleshoot CI failure" or "fix failing checks"
- User asks to "add coverage enforcement" to CI
- User asks to "configure required PR checks"
- User asks to "run quality gates locally" before pushing
- When creating a new project and setting up CI/CD
