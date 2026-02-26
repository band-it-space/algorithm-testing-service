# AGENTS.md - StockFishers trading algorithms

> **For AI Agents:** This file is your technical source of truth. Read this before any coding task.

## Scoped Instructions

---

## 1. Project Overview

**What is this?**  
Kenshoo Social is a **Java-based multi-module Maven monorepo** for social media advertising management. It includes backend services, batch processing, API clients, and E2E testing infrastructure using Playwright.

**Tech Stack:**

- **Language:** Java 11
- **Build System:** Maven (primary), Gradle (secondary for some modules)
- **Framework:** Spring Framework 4.3.25, Spring Boot 1.5.22
- **ORM:** Hibernate 4.3.11
- **Database:** MySQL 8.0
- **Messaging:** Apache Kafka 2.4.0, ActiveMQ
- **Caching:** Redis (Redisson 3.52.0), Caffeine
- **Testing:** JUnit 4.13.1, Mockito 5.20.0, Cucumber (E2E), Playwright (UI E2E)
- **Code Quality:** Lombok, JaCoCo for coverage
- **Cloud:** AWS (SQS, S3), Azure Storage

**Architecture:**

- **Multi-module Maven structure:** ~70+ modules
- **Core modules:** `social/`, `common/`, `platform/`, `service-facade/`
- **API clients:** `api-http-clients/`, `ks-client/`, `facebookclient/`
- **Batch processing:** `common-batch/`, `jobprocessing/`, `kjobster/`
- **Testing:** `socialtests/`, `api-tests/`, `playwright/`

---

## 2. Operational Commands

**Critical:** Always use these exact commands. Do not guess alternatives.

### Setup

```bash
# Install dependencies
mvn clean install -DskipTests

# Install with tests
mvn clean install
```

### Development

```bash
# Build specific module
mvn clean install -pl {module-name} -am -DskipTests

# Build with all dependencies
mvn clean install -pl {module-name} -am

# Example: Build social module
mvn clean install -pl social -am -DskipTests
```

### Testing

```bash
# Run all unit tests
mvn test

# Run tests for specific module
mvn test -pl {module-name}

# Run integration tests
mvn verify -pl {module-name}

# Run tests with coverage
mvn test jacoco:report

# Skip tests during build
mvn clean install -DskipTests
# OR
mvn clean install -Dskip.tests=true
```

### Playwright E2E Tests

```bash
# Navigate to playwright directory
cd playwright/src

# Install dependencies
npm install

# Run E2E tests
npm run test:e2e

# Run tests with UI mode
npm run test:ui

# Run tests headed (visible browser)
npm run test:headed

# Run tests in debug mode
npm run test:debug
```

### Database

```bash
# Run Liquibase migrations
mvn liquibase:update -pl db

# Generate Liquibase diff
mvn liquibase:diff -pl db
```

### Code Quality

```bash
# Run checkstyle
mvn checkstyle:check

# Run SonarQube analysis
mvn sonar:sonar
```

---

## 3. Development Rules

**Critical rules that build tools CANNOT catch. Follow these strictly.**

### File & Directory Naming

- **Modules:** `kebab-case` (e.g., `api-http-clients`, `common-batch`)
- **Java packages:** `com.kenshoo.social.{module}.{subpackage}`
- **Java classes:** PascalCase (e.g., `CampaignService`, `FacebookClient`)
- **Test classes:** `{ClassName}Test.java` or `{ClassName}IT.java` (integration tests)
- **Resources:** lowercase with hyphens (e.g., `application-context.xml`)
- **SQL scripts:** lowercase with underscores (e.g., `create_table.sql`)

### Module Organization

- **`/src/main/java`** - Production Java code
- **`/src/main/resources`** - Configuration files, SQL, XML
- **`/src/test/java`** - Unit tests
- **`/src/test/resources`** - Test resources and fixtures

### Code Architecture Patterns

- **Use Spring DI** for all service/component wiring
- **Use Lombok** for boilerplate reduction (`@Data`, `@Builder`, `@Slf4j`)
- **DAO pattern** for database access
- **Service layer** for business logic
- **DTOs** for API request/response objects
- **Entities** for database models

### Standard Java Patterns

```java
// Standard service class structure
package com.kenshoo.social.module.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Service
@Slf4j
@RequiredArgsConstructor
public class MyService {
    private final MyRepository repository;
    private final AnotherService anotherService;

    public Result doSomething(Request request) {
        log.info("Processing request: {}", request);
        // Business logic
        return result;
    }
}
```

### Testing Requirements

- **Unit tests:** Use JUnit 4 + Mockito, mock all dependencies
- **Integration tests:** Use Spring Test, name with `*IT.java` suffix
- **E2E API tests:** Located in `api-tests/` module, use Cucumber/Karate
- **E2E UI tests:** Located in `playwright/src/e2e/`, use Playwright
- **Coverage:** Add/update tests when modifying behavior

### Database Changes

- **Always use Liquibase** for schema changes
- **Create changesets** in `db/` module
- **Never modify** production data directly
- **Include rollback** scripts when possible

### Performance & Security

- **No hardcoded secrets** - use Spring Vault or environment variables
- **Use connection pooling** (HikariCP)
- **Avoid N+1 queries** - use batch fetching
- **Use caching** where appropriate (Caffeine, Redis)

---

## 5. Quick Reference

### Repository Structure

```
social-master/
├── social/                    # Main social application (web, app, services)
├── common/                    # Shared utilities and components
├── platform/                  # Platform services
├── service-facade/            # Service facade layer
├── service-facade-entities/   # Service facade DTOs
├── api-http-clients/          # HTTP client implementations
│   ├── ad-fatigue-client/
│   ├── bitLy-client/
│   ├── http-client-common/
│   └── ...
├── facebookclient/            # Facebook API client
├── automated-actions/         # Automated actions engine
├── automated-actions-entities/
├── jobprocessing/             # Job processing framework
├── kafka-messaging/           # Kafka integration
├── persistence/               # Persistence layer
├── db/                        # Database migrations (Liquibase)
├── api-tests/                 # API integration tests
├── playwright/                # E2E UI tests (Playwright)
│   └── src/
│       ├── e2e/               # Test files
│       └── utils/             # Test utilities
├── socialtests/               # Legacy tests
└── docs/                      # Documentation
    └── playwright/            # Playwright documentation
```

### Key Modules by Domain

- **Core:** `social/`, `common/`, `platform/`
- **API Clients:** `api-http-clients/`, `facebookclient/`, `ks-client/`
- **Data:** `persistence/`, `db/`, `common-dao/`
- **Messaging:** `kafka-messaging/`, `notification-events/`, `notifications/`
- **Jobs:** `jobprocessing/`, `kjobster/`, `common-batch/`
- **Testing:** `api-tests/`, `playwright/`, `socialtests/`

### External Services

- **Facebook API:** Social media integration
- **Kafka:** Event streaming and messaging
- **MySQL:** Primary database
- **Redis:** Caching and session management
- **AWS:** SQS, S3 for cloud services
- **Vault:** Secret management

---

## 6. Environment Setup

Required configuration files:

### Maven Settings (`~/.m2/settings.xml`)

```xml
<settings>
  <servers>
    <server>
      <id>kenshoo-releases</id>
      <username>${env.MAVEN_USER}</username>
      <password>${env.MAVEN_PASSWORD}</password>
    </server>
  </servers>
</settings>
```

### Playwright E2E Tests (`.env.test`)

```bash
# Required for E2E tests
BASE_URL=<application-url>
TEST_USER=<test-username>
TEST_PASSWORD=<test-password>
```

### Local Development

- Java 11 JDK required
- Maven 3.6+ required
- MySQL 8.0 for local database
- Node.js 18+ for Playwright tests

---

**Last Updated:** February 2026  
**Maintained By:** Social Development Team  
**Questions?** Consult the [wiki](https://github.com/kenshoo/social/wiki).
