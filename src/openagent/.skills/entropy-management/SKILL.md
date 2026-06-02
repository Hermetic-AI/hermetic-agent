---
name: entropy-management
description: Track and manage technical debt, code quality decay, file health, duplicate code, documentation freshness, and log hygiene. Use during sprint retrospectives, bi-weekly maintenance, or when addressing technical debt.
risk: safe
source: C:\WorkSpace\Coding\Herness Engerneering\harness-rules\entropy-checklist.md, file-limits.json
date_added: 2026-06-01
---

# Entropy Management — Agent Skill Guide

Track and manage technical debt, code quality decay, documentation freshness, and logging hygiene across the codebase.

---

## 1. File Health Monitor

### Thresholds

| Status | Lines | Action |
|--------|-------|--------|
| 🟢 Healthy | < 200 | No action needed |
| 🟡 Warning | 200 - 300 | Review and plan split |
| 🔴 Critical | > 300 | Must split immediately |

### Check File Sizes

```bash
# Python: find files exceeding limits
find src -name "*.py" -exec wc -l {} \; | awk '{if($1 > 300) print $2 ": " $1 " lines - EXCEEDS 300"}'

# TypeScript: find files exceeding 500 lines
find src -name "*.ts" -o -name "*.tsx" | xargs wc -l | awk '{if($1 > 500) print $2 ": " $1 " lines - EXCEEDS 500"}'

# Java: find classes exceeding 300 lines
find src/main -name "*.java" -exec wc -l {} \; | awk '{if($1 > 300) print $2 ": " $1 " lines - EXCEEDS 300"}'
```

### Split Trigger Actions

When a file exceeds its limit:
1. Create a ticket/issue for the split
2. Identify logical separation points (class responsibilities)
3. Extract to new module with proper imports
4. Update all calling sites
5. Verify tests still pass

---

## 2. Duplicate Code Registry

### Detection Tools

```bash
# Python: PMD CPD
flake8 --select=C4  # comprehend for duplicated comprehension patterns
pip install pmd
mvn pmd:cpd

# Python: flake8-cognitive
pip install flake8-cognitive
flake8 --select=CognitiveCC src/

# Java
mvn pmd:cpd

# TypeScript
npm install --save-dev jscpd
npx jscpd src/
```

### Threshold Rules

| Language | Threshold | CI Action |
|----------|-----------|-----------|
| Python | > 5% duplication | CI failure |
| Java | > 3% duplication | CI failure |
| TypeScript | > 5% duplication | CI failure |

### Actions on Duplication Found

1. [ ] Run duplication detector: `mvn pmd:cpd` or `flake8 --select=C4`
2. [ ] Identify the duplicated logic blocks
3. [ ] Extract to shared utility or base class
4. [ ] Update all calling sites
5. [ ] Verify tests still pass

---

## 3. Util Module Audit

### Rule: Utils Functions Must Have ≥ 3 Callers

```bash
# List all functions in utils/
find src -name "utils*" -o -name "helpers*" | xargs grep -rh "def \|function "

# Count unique modules using each function
for func in $(grep -roh "def \w+" src/utils/*.py | sort -u | cut -d' ' -f2); do
  count=$(grep -r "$func" src/ --include="*.py" | grep -v "def $func" | cut -d: -f1 | sort -u | wc -l)
  echo "$func: $count modules"
done
```

### Functions with < 3 Usages

| Status | Action |
|--------|--------|
| 🟡 Low usage | Find more usages, or merge back to original module |
| 🔴 Single usage | Inline back to original module |
| 🔴 Two usages | Evaluate if extraction was premature |

### Decision Tree for Utils Functions

```
Does function have ≥ 3 callers across different modules?
├── YES → Keep in utils/ ✓
└── NO
    ├── 1-2 callers → Keep in original module (extraction was premature)
    └── Documented special case → Keep in utils with @deprecated notice
```

---

## 4. Documentation Freshness

### Checkpoints

- [ ] Run `docs/PROGRESS.md` vs `git log` comparison
- [ ] New modules have ARCHITECTURE.md entries
- [ ] API endpoints match API.md documentation
- [ ] No "TODO" older than 30 days without explanation

### Doc-Gardening Actions

```bash
# Find stale TODOs (older than 30 days)
grep -r "TODO" src/ --include="*.py" --include="*.java" --include="*.ts" | xargs -I{} git log -1 --format="%ai %s" -- {}

# Check for undocumented public APIs
grep -r "def \|public \|export " src/ --include="*.py" --include="*.java" --include="*.ts" | grep -v "^\s*#\|^\s*//" | head -50

# Run documentation generator
python -m pdoc src/ --output-dir docs/
mvn doclint
```

### Documentation Standards

| Document | Update Frequency | Owner |
|----------|-----------------|-------|
| ARCHITECTURE.md | On architectural changes | Tech Lead |
| API.md | On API changes | API Owner |
| PROGRESS.md | Weekly | Team |
| README.md | Monthly | All |

---

## 5. Log Health Check

### Log Patterns and Severity

| Pattern | Severity | Description | Action |
|---------|----------|-------------|--------|
| `print()` found | 🔴 High | Debug statement in code | Replace with logger |
| `logger.debug` without context | 🟡 Medium | Missing extra fields | Add contextual data |
| `ERROR` without follow-up | 🟡 Medium | No tracking mechanism | Create incident ticket |
| Empty catch block | 🔴 High | Silent failure | Add logging + handling |

### Search Commands

```bash
# Python: find print statements
grep -r "print(" src/ --include="*.py" | grep -v "logger\|print(" | head -20

# Python: find empty except blocks
grep -r "except.*:" src/ --include="*.py" -A 5 | grep -B1 "pass\|..." | head -30

# Java: find empty catch blocks
grep -r "catch.*}" src/ --include="*.java" | grep -v "logger\|throw" | head -20

# TypeScript: find console statements
grep -r "console\." src/ --include="*.ts" --include="*.tsx" | head -20
```

### Log Best Practices

```python
# BAD: No context
logger.debug("Processing request")

# GOOD: With context
logger.debug("Processing request", extra={"request_id": request_id, "user_id": user_id})

# BAD: Empty catch
try:
    do_something()
except Exception:
    pass

# GOOD: Log and handle
try:
    do_something()
except SpecificError as e:
    logger.error("Failed to do something", exc_info=True)
    raise
```

---

## 6. Test Coverage Decay

### Coverage Targets

| Module Type | Target | Minimum |
|-------------|--------|---------|
| Critical path (auth, payment) | 90% | 80% |
| Business logic (services) | 80% | 70% |
| Data access (repositories) | 75% | 60% |
| Utilities | 60% | 50% |

### Generate Coverage Reports

```bash
# Python
pytest tests/ -v --cov=src --cov-report=html --cov-fail-under=70

# Java
mvn test jacoco:report
# View: target/site/jacoco/index.html

# TypeScript
npm test -- --coverage --coverageThreshold='{"global":{"branches":70,"functions":70,"lines":70,"statements":70}}'
```

### Identify Low Coverage Modules

```bash
# Python: find modules below coverage target
coverage report --skip-covered | awk '{if($2 ~ /%/ && int($2) < 70) print}'

# Java: check jacoco
cat target/site/jacoco/index.html | grep -A2 "Total"
```

---

## 7. Dependency Audit

### Commands

```bash
# Python: check outdated packages
pip list --outdated
pip freeze > requirements.txt

# Python: security check
pip install safety
safety check

# Java: Maven dependency analysis
mvn dependency:analyze
mvn dependency:tree

# TypeScript: check outdated
npm outdated
npm audit
```

### Update Cadence

| Dependency Type | Update Frequency | Testing Required |
|-----------------|------------------|------------------|
| Patch versions | Monthly | Smoke test |
| Minor versions | Quarterly | Full regression |
| Major versions | 6-monthly | Full test suite + manual |

---

## 8. Technical Debt Backlog

### Severity Scale

| Severity | Description | Example |
|----------|-------------|---------|
| 🔴 High | Blocks features | Memory leak, security vulnerability |
| 🟡 Medium | Degrades DX | Slow tests, complex code |
| 🟢 Low | Nice to have | Code style, minor duplication |

### Tracking Format

| ID | Description | Severity | Impact | Est. Hours | Sprint |
|----|-------------|----------|--------|------------|--------|
| TD-001 | Auth module has 3000-line class | 🔴 High | Blocks new features | 8 | S-23 |
| TD-002 | Tests take 30 minutes | 🟡 Medium | Slow CI | 16 | Backlog |

---

## 9. Maintenance Schedule

| Cadence | Activity |
|---------|----------|
| Daily | Run full test suite |
| Weekly | Run lint + type checks |
| Bi-weekly | File health + duplicate code check |
| Sprint End | Full entropy audit + doc update |
| Monthly | Dependency audit + updates |

---

## 10. Quick Start Commands

### Python

```bash
# Full quality check
pytest tests/ -v --cov=src
flake8 src/ --exclude venv
mypy src/
interrogate src/ -v
```

### Java

```bash
# Full quality check
mvn test
mvn checkstyle:check
mvn pmd:cpd
mvn dependency:analyze
```

### TypeScript

```bash
# Full quality check
npm test -- --coverage
npm run lint
npx tsc --noEmit
npm audit
```

---

## 11. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Issues found (violations, coverage below threshold) |
| 2 | Configuration error |

---

## 12. When to Use This Skill

- During sprint retrospective or bi-weekly maintenance windows
- User asks to "check technical debt" or "run entropy audit"
- User asks to "find duplicate code" or "check code duplication"
- User asks to "review log hygiene" or "find empty catch blocks"
- User asks to "check documentation freshness" or "update stale docs"
- User asks to "run coverage report" or "identify untested code"
- User asks to "audit dependencies" or "check for outdated packages"
