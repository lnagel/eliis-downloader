# CLAUDE.md - AI Agent Guidelines

This document provides essential guidelines for AI agents working on this codebase.

## Environment Setup

**ALWAYS run before any code quality checks:**

```bash
uv sync --dev
```

This installs all dependencies including dev extras (pytest, ruff, ty).

## Pre-Commit Checklist

**BEFORE committing any changes, run ALL of these checks in order:**

```bash
# 1. Run tests first - ensures code works correctly
uv run pytest

# 2. Format code with ruff (auto-fixes formatting issues)
uv run ruff format .

# 3. Lint with ruff (auto-fixes what it can)
uv run ruff check . --fix

# 4. Type check with ty
uv run ty check
```

**All checks must pass before committing.** CI will reject PRs that fail any of these.

## Testing Requirements

### Test Coverage
- **Overall**: 90% minimum (enforced in pyproject.toml and CI)
- **Core Modules**: 100% target, 98% minimum acceptable (critical control logic)

### Bug Fixes: Reproduce First
When fixing bugs:
1. **Write a failing test case first** that reproduces the bug
2. Verify the test fails as expected
3. Implement the fix
4. Verify the test now passes
5. Add any additional edge case tests

This ensures bugs don't regress and documents the expected behavior.

## Code Quality Standards

### Ruff Configuration
- Line length: 120 characters
- Target: Python 3.13+
- Select: ALL rules (with specific ignores, see pyproject.toml)
- Tests have relaxed rules for asserts, magic values, etc.

### Type Annotations
- Use type hints for all function signatures
- Run `uv run ty check` to verify

## Git Commit Practices

### Good Commit History
- **Each meaningful change deserves its own commit**
- Prefer new incremental commits over amending
- Write clear, descriptive commit messages
- Use conventional format: `Fix X`, `Add Y`, `Update Z`
- PRs are squash-merged, so we can have detailed commit history during development

## Common Pitfalls to Avoid

### 1. Forgetting `uv sync`
```bash
# WRONG - tools not installed
uv run pytest  # Error: pytest not found

# RIGHT
uv sync --dev
uv run pytest
```

### 2. Committing Without Full Check Cycle
```bash
# WRONG - only ran tests
uv run pytest
git commit

# RIGHT - full verification
uv run pytest && uv run ruff format . && uv run ruff check . --fix && uv run ty check
git commit
```

### 3. Fixing Bugs Without Tests
```python
# WRONG - Just fix the code
def download_photos(...):
    return fixed_value  # "trust me it works now"

# RIGHT - Write failing test first
def test_download_edge_case():
    # This test should fail before the fix
    assert download_result == expected
```

### 4. Running Commands with Paths Outside the Working Directory
Do not use `git -C`, `find /`, or similar flags that reference paths outside the
current working directory. They are unnecessary and cause permission check failures.
Prefer relative paths from the project root and avoid changing working directories
when possible.

## CI Workflows

The CI runs Unit tests with pytest, Ruff check, Ruff format, ty type check

All must pass for PR approval.
