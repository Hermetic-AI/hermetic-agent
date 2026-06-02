---
name: architecture-enforcement
description: Enforce layered architecture rules (Controller→Service→Repository→Model) using importlinter and ArchUnit. Use when the user asks to check architectural compliance, validate layer dependencies, or prevent circular imports.
risk: safe
source: C:\WorkSpace\Coding\Herness Engerneering\harness-rules\importlinter.toml, archunit.java
date_added: 2026-06-01
---

# Architecture Enforcement — Agent Skill Guide

Enforce architectural boundaries and layered architecture rules across Python and Java projects.

---

## 1. Architecture Principles

### Dependency Flow Rules

```
Dependencies can ONLY flow downward:

Controller → Service → Repository → Model/Config
                    ↓
                  Events (same-level calls via events only)

FORBIDDEN patterns:
  Service → Controller  ❌
  Controller → Repository (direct)  ❌
  Repository → Service  ❌
  Model → Service  ❌
```

### Layer Definitions

| Layer | Can Import From | Purpose |
|-------|-----------------|---------|
| `controllers` | services, models, schemas, utils, config, events, middleware | HTTP request handling |
| `services` | repositories, models, schemas, utils, config, events, middleware | Business logic |
| `repositories` | models, config, utils | Data access |
| `models` | config, utils | Data entities |
| `schemas` | models, config, utils | Data validation |
| `utils` | config, models | Shared utilities |
| `events` | models, config, utils, schemas | Event handling |
| `config` | (nothing — lowest level) | Configuration |
| `middleware` | models, config, utils, schemas | Cross-cutting concerns |

---

## 2. Python: ImportLinter

### Configuration (importlinter.toml)

```toml
[importlinter]
root_package = src

[[importlinter.rules.type]]
name = "dependency-flow"
type = "layered"

layers = [
    {name = "controllers", can_import_from = ["services", "models", "schemas", "utils", "config", "events", "middleware"]},
    {name = "services", can_import_from = ["repositories", "models", "schemas", "utils", "config", "events", "middleware"]},
    {name = "repositories", can_import_from = ["models", "config", "utils"]},
    {name = "models", can_import_from = ["config", "utils"]},
    {name = "schemas", can_import_from = ["models", "config", "utils"]},
    {name = "utils", can_import_from = ["config", "models"]},
    {name = "events", can_import_from = ["models", "config", "utils", "schemas"]},
    {name = "config", can_import_from = []},
    {name = "middleware", can_import_from = ["models", "config", "utils", "schemas"]},
]
```

### Custom Rules

```toml
[importlinter.rules.type]
name = "forbidden-direct-service-to-controller"
type = "custom"
error_message = """
Service layer must NOT import Controller layer.

Architectural Violation:
  Service → Controller is STRICTLY FORBIDDEN

This breaks the dependency direction. Business logic should NOT depend on HTTP concerns.

Solution:
  - Keep controllers thin (request/response only)
  - Services should be framework-agnostic
  - If service needs to communicate with controller, use events/interfaces
"""

[importlinter.rules.type]
name = "no-cross-layer-direct-calls"
type = "custom"
error_message = """
Cross-layer direct calls are not allowed.

Cross-layer calls detected. All calls between layers must go through proper interfaces.

Allowed patterns:
  Controller → Service (via interface/abstract)
  Service → Repository (via interface/abstract)

Forbidden patterns:
  Controller → Repository (direct)
  Service → Service (same layer calls via events only)
"""

[[importlinter.rules.type]]
name = "no-utils-abuse"
type = "custom"
error_message = """
Utils module misused: function used in fewer than 3 places.

Util extraction rule: Functions in utils/ MUST be reused in at least 3 different modules.

If a function is only used in 1-2 places, keep it in the original module.
If you need to extract it to utils, find a third usage first.
"""
```

### Agent Commands

```bash
# Install
pip install importlinter

# Run all architecture checks
lint_imports

# Run specific rule
lint_imports --config importlinter.toml

# Check specific package
lint_imports --root-package src.services

# Output formats
lint_imports --output-format=text  # default
lint_imports --output-format=json
lint_imports --output-format=sarif
```

---

## 3. Java: ArchUnit

### Test Class (ArchitectureTest.java)

```java
package com.example;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.library.Architectures.*;

@AnalyzeClasses(
    packagesOf = com.example.Application.class,
    importOptions = {ImportOption.DoNotIncludeTests.class, ImportOption.DoNotIncludeJars.class}
)
public class ArchitectureTest {

    // Layered Architecture Rule
    @ArchTest
    static final ArchRule layerDependencies = layeredArchitecture()
        .consideringAllDependencies()
        .layer("Controller").definedBy("..controller..")
        .layer("Service").definedBy("..service..")
        .layer("Repository").definedBy("..repository..")
        .layer("Model").definedBy("..model..")
        .layer("Config").definedBy("..config..")
        .layer("Utils").definedBy("..utils..")
        .whereLayer("Controller").mayNotAccessAnyLayer()
        .whereLayer("Service").mayNotAccess("..controller..")
        .whereLayer("Repository").mayNotAccess("..service..", "..controller..")
        .whereLayer("Model").mayNotAccess("..service..", "..repository..", "..controller..")
        .whereLayer("Utils").mayNotAccess("..controller..", "..service..", "..repository..");

    // Naming Conventions
    @ArchTest
    static final ArchRule controllers_named = ArchRuleFactory.classes()
        .that().resideInPackage("..controller..")
        .should().haveNameMatching(".*Controller")
        .because("Controllers must end with 'Controller' suffix");

    @ArchTest
    static final ArchRule services_named = ArchRuleFactory.classes()
        .that().resideInPackage("..service..")
        .should().haveNameMatching(".*Service")
        .because("Services must end with 'Service' suffix");

    @ArchTest
    static final ArchRule repositories_named = ArchRuleFactory.classes()
        .that().resideInPackage("..repository..")
        .should().haveNameMatching(".*Repository")
        .because("Repositories must end with 'Repository' suffix");

    // Service Layer Constraints
    @ArchTest
    static final ArchRule services_should_not_use_request_or_response = ArchRuleFactory.classes()
        .that().resideInPackage("..service..")
        .should().notDependOnClassesThat().resideInPackage("..controller..")
        .andShould().notDependOnClassesThat().resideInPackage("..dto..")
        .because("Service layer must not depend on HTTP layer");

    @ArchTest
    static final ArchRule services_must_have_logger = ArchRuleFactory.methods()
        .that().arePublic()
        .and().areDeclaredInClassesThat().resideInPackage("..service..")
        .should().beAnnotatedWith(org.slf4j.Logger.class)
        .orShould().callMethod(org.slf4j.Logger.class, "info", org.slf4j.event.Level.ERROR)
        .because("All public service methods must have logger calls");

    // No Field Injection
    @ArchTest
    static final ArchRule no_field_injection = ArchRuleFactory.classes()
        .that().resideInPackage("..service..", "..repository..")
        .should().notBeAnnotatedWith(org.springframework.beans.factory.annotation.Autowired.class)
        .because("Use constructor injection instead of field injection");

    // Repository Layer Constraints
    @ArchTest
    static final ArchRule repositories_should_not_use_service = ArchRuleFactory.classes()
        .that().resideInPackage("..repository..")
        .should().notDependOnClassesThat().resideInPackage("..service..")
        .because("Repository layer must not depend on Service layer");

    // Documentation Rules
    @ArchTest
    static final ArchRule public_methods_should_have_javadoc = ArchRuleFactory.methods()
        .that().arePublic()
        .and().areDeclaredInClassesThat().resideInPackage("..service..", "..controller..", "..repository..")
        .should().beAnnotatedWith(org.springframework.doclet.common.*.class)
        .orShould().haveRawDescription(java.lang.String.class)
        .because("All public API methods must have Javadoc");
}
```

### Maven Dependency

```xml
<dependency>
    <groupId>com.tngtech.archunit</groupId>
    <artifactId>archunit-junit5</artifactId>
    <version>1.0.0</version>
    <scope>test</scope>
</dependency>
```

### Agent Commands

```bash
# Run ArchUnit tests
mvn test -Dtest=ArchitectureTest

# Run with full test suite
mvn test

# Generate HTML report
mvn test jacoco:report
```

---

## 4. Detecting Architecture Violations

### Python

```bash
# Check for forbidden imports
grep -r "from.*controller.*import" src/services/ --include="*.py"
grep -r "from.*services.*import" src/controllers/ --include="*.py"

# Check for direct cross-layer calls
grep -r "from.*repository.*import" src/services/ --include="*.py"
grep -r "from.*services.*import" src/repositories/ --include="*.py"

# Check for circular imports
python -c "import sys; sys.path.insert(0, 'src'); import importlib.util; print('Checking...')"

# Utils usage analysis
grep -r "from.*utils.*import" src/ --include="*.py" | cut -d: -f1 | sort -u | wc -l
```

### Java

```bash
# Check for forbidden dependencies
grep -r "import.*controller" src/main/java/**/service/ --include="*.java"
grep -r "import.*service" src/main/java/**/repository/ --include="*.java"

# Run full architecture test
mvn test -Dtest=ArchitectureTest

# Check naming conventions
find src -name "*Controller.java" | grep -v "Controller"
find src -name "*Service.java" | grep -v "Service"
```

---

## 5. Common Violations and Fixes

### Violation: Service imports Controller

```
ERROR: Service 'UserService' imports 'UserController'

Fix:
  - Remove controller reference from service
  - Use events/interfaces for communication
  - Keep controllers thin (only request/response)
```

### Violation: Cross-layer direct call

```
ERROR: Controller directly calling Repository

Fix:
  - Add service layer in between
  - Controller → Service → Repository
```

### Violation: Utils function used < 3 times

```
ERROR: 'format_date' in utils/ used only 2 times

Fix:
  - Keep function in original module if < 3 usages
  - Find more usage cases, or
  - Document why special case
```

### Violation: Circular dependency

```
ERROR: Circular import detected: A → B → C → A

Fix:
  - Use TYPE_CHECKING guard for type hints
  - Restructure imports to flow downward
  - Use interfaces/abstractions
```

---

## 6. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All architecture rules passed |
| 1 | Architecture violations detected |
| 2 | Configuration error |

---

## 7. When to Use This Skill

- User asks to "check architecture" or "validate layer dependencies"
- User asks to "prevent circular imports" or "fix circular dependency"
- User asks to "enforce layered architecture" or "check import rules"
- User asks to "validate that services don't import controllers"
- During PR review or before merging
- When restructuring code or adding new layers
