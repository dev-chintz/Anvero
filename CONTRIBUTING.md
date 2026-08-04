# Contributing to Anvero

Thank you for contributing to Anvero.

This project is developed using Git, GitHub and AI-assisted development. Every contribution should follow the workflow described below.

---

# Development Workflow

Every task follows the same process:

1. Understand the current sprint.
2. Read the relevant documentation.
3. Implement one logical change.
4. Review the code.
5. Update documentation if required.
6. Commit.
7. Push.

Never combine unrelated changes into one commit.

---

# Documentation

Before implementing new functionality, read:

- docs/AI_START_HERE.md
- docs/PROJECT_STATUS.md
- docs/PROJECT_RULES.md
- docs/ROADMAP.md
- docs/ARCHITECTURE.md

Documentation is the single source of truth.

---

# Git Workflow

Update repository:

```bash
git pull
```

Check changes:

```bash
git diff
```

Commit:

```bash
git add .
git commit -m "<type(scope): description>"
```

Push:

```bash
git push
```

---

# Commit Convention

Examples:

```text
feat(api): add health endpoint
feat(core): add application configuration
feat(db): configure SQLAlchemy

fix(api): fix validation error

refactor(core): simplify configuration

docs: update roadmap

test(api): add health endpoint tests

chore: update dependencies
```

---

# AI Workflow

Every AI assistant must:

1. Read `docs/AI_START_HERE.md`.
2. Read all referenced documentation.
3. Summarize the current state.
4. Implement only one task at a time.
5. Explain architectural decisions.
6. Wait for approval before large changes.
7. Suggest a commit message.

AI must not redesign the project without explicit approval.

---

# Code Standards

- Use Python type hints.
- Keep functions short.
- Prefer composition over inheritance.
- Avoid duplicated logic.
- Follow Clean Architecture.
- Write readable code.

---

# Pull Requests

Each pull request should:

- solve one problem,
- keep commits focused,
- not introduce unrelated changes,
- update documentation when needed.

---

# Project Philosophy

Anvero is designed as a long-term, production-quality project.

Priorities:

1. Simplicity
2. Readability
3. Modularity
4. Maintainability
5. Scalability
6. Automation

Quality is more important than speed.