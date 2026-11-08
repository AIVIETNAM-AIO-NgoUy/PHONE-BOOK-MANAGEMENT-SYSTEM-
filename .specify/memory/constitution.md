# Phone Book Management System Constitution

## Core Principles

### I. Architectural Simplicity & Zero Overengineering
The Phone Book Management System is strictly architected as a Modular Monolith using Django 5.1+, PostgreSQL 16+, and HTMX 2.x.
- No microservices, distributed architectures, or asynchronous message brokers (e.g., Celery, RabbitMQ, Kafka) are permitted for core workflows.
- Dynamic frontend interactivity MUST be achieved via HTMX partial rendering and lightweight vanilla JavaScript rather than heavyweight Single Page Application (SPA) frameworks.
- Keep domain boundaries modular within Django apps (`accounts`, `contacts`, `groups`, `favorites`, `admin_panel`, `core`).

### II. Test-First & Automated Verification (NON-NEGOTIABLE)
Test-Driven Development (TDD) is non-negotiable:
- Contract tests and integration tests MUST be authored first and proven to fail before any domain logic or view implementation commences.
- Red-Green-Refactor development cycle is strictly enforced across all user stories.
- Minimum automated test coverage gate is `>= 85%` across all domain apps.
- All acceptance scenarios and edge cases (`EC-001` through `EC-010`) must have automated test coverage.

### III. Strict Multi-Tenant Data Isolation
Every user's personal contact directory, custom groups, and favorite lists are isolated with zero cross-tenant leakage:
- Every query mutating or retrieving contact records MUST be scoped strictly to the authenticated user's `ContactBook`.
- In compliance with FR-042, System Administrators have administrative governance over user accounts only (view non-sensitive metadata, lock/unlock accounts); administrators are strictly prohibited from viewing, searching, or mutating personal contacts, phone numbers, groups, or favorites belonging to other users.

### IV. Security & Credential Protection Baseline
Security is built-in by default across all tiers:
- Passwords MUST be cryptographically hashed using salted Argon2 (or PBKDF2 SHA-256 with 600,000+ iterations). Plaintext passwords must never be stored, logged, or exposed.
- All state-changing HTTP requests MUST enforce Django CSRF token protection.
- Session invalidation must be instantaneous: when an account is locked by an administrator or credentials change, active sessions must be immediately evicted from `django_session`.
- Sensitive credentials and keys must be managed via environment variables (`python-decouple`).

### V. Usability & Irreversible Action Safeguards
Destructive user actions require protection against accidental loss:
- The system MUST present an explicit modal confirmation dialog prior to executing irreversible actions (permanent deletion of individual contacts, batch deletion of contacts, or group deletion).
- Deleting a contact group MUST clean up membership junction records while strictly preserving all underlying contact entities (`FR-029`).
- Removing an item from favorites MUST never delete the referenced contact (`FR-022`).
- State modifications must provide immediate, dismissible user feedback alerts.

## Technology & Platform Constraints

- **Backend Runtime**: Python 3.11+
- **Framework**: Django 5.1+ (Modular Monolith architecture)
- **Database**: PostgreSQL 16+ utilizing `pg_trgm` extension for GIN trigram indexing
- **Frontend / Interactivity**: HTML5, Django Templates, CSS matching Figma design specifications, HTMX 2.x, vanilla JavaScript
- **Deployment Targets**: Standard Linux and Windows environments, Docker containerized PostgreSQL
- **Concurrency & Performance**: Gunicorn with multi-threaded workers (`gthread`), supporting 100 concurrent active users and sub-2.0s search across 10,000+ contacts.

## Development Workflow & Quality Gates

1. **Pre-Implementation Contract**: Every API/view endpoint must have a documented contract before writing view logic.
2. **Test-First Gate**: Test cases must be checked into the test suite and confirmed failing before task execution.
3. **Database Migration Standard**: Every schema modification must have a reversible migration with explicit foreign key constraints (`ON DELETE CASCADE` or `ON DELETE SET NULL`) and appropriate B-Tree / GIN indexes.
4. **Code Quality & Linting**: Black (line length 100), isort (django profile), and Flake8 compliance with zero warnings.
5. **Security Audit**: Bandit and Safety checks must pass cleanly with zero high/critical vulnerabilities.

## Governance

This Constitution supersedes all informal architectural decisions. Any structural amendment or exemption requires formal documentation, architectural rationale, and version update.

**Version**: 1.0.0 | **Ratified**: 2026-11-12 | **Last Amended**: 2026-11-12
