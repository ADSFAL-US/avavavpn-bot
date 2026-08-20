---
name: test-workflow
description: Comprehensive testing workflow for Avava VPN Bot. Runs test_runner.py in venv with dependencies from requirements-test.txt, then analyzes diffs for logic errors.
---

# Avava VPN Bot Testing Workflow

This skill defines a systematic testing workflow for the Avava VPN Bot project. Since Docker doesn't work in the sandbox environment, all testing must run in the local Python venv.

## Workflow Steps

### Phase 1: Environment Setup
1. **Activate the project venv** (`.venv/`)
2. **Install test dependencies** from `requirements-test.txt`
3. **Verify installation** of coverage, mutmut, ruff, pylint

### Phase 2: Run Test Suite
Execute `test_runner.py` with appropriate flags:
- **Default**: Run all phases (lint → unit → coverage → mutation)
- **CI mode**: `--ci` (lint, unit, coverage only)
- **Specific phase**: `--lint`, `--unit`, `--coverage`, `--mutation`

### Phase 3: Analyze Results
1. **Check test summary** - all phases must pass
2. **If failures**: Examine output for specific errors
3. **If all pass**: Proceed to diff analysis

### Phase 4: Diff Analysis (Post-Success)
1. **Get git diff** of recent changes
2. **Analyze for logic errors**:
   - Off-by-one errors
   - Incorrect conditionals
   - Missing edge case handling
   - Type mismatches
   - Async/await issues
   - Database transaction problems
   - Payment/subscription logic flaws
3. **Propose fixes** for any issues found

## Decision Points

```
┌─────────────────────────────────────┐
│  Run test_runner.py                 │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
   PASSED           FAILED
       │               │
       ▼               ▼
┌─────────────┐  ┌─────────────┐
│ Diff Analysis│  │ Fix Errors  │
│ (Phase 4)   │  │ Re-run      │
└─────────────┘  └─────────────┘
```

## Quality Criteria

- ✅ All linting passes (ruff + pylint)
- ✅ All unit tests pass
- ✅ Coverage meets threshold (check report)
- ✅ Mutation testing passes (or known limitations documented)
- ✅ No logic errors in diff analysis

## Usage

```bash
# Full test suite
python test_runner.py

# CI mode (no mutation)
python test_runner.py --ci

# Specific phase
python test_runner.py --lint
python test_runner.py --unit
python test_runner.py --coverage

# Install deps first
python test_runner.py --install-deps
```

## Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| mutmut internal error | Mark as optional, continue |
| pylint false positives | Check disabled codes in test_runner.py |
| Coverage low | Add tests for uncovered lines |
| Import errors | Verify venv activation, reinstall deps |

## Related Files

- `test_runner.py` - Main test orchestrator
- `requirements-test.txt` - Test dependencies
- `requirements.txt` - Runtime dependencies
- `.venv/` - Python virtual environment
- `tests/` - Unit test directory
- `htmlcov/` - Coverage HTML reports
- `mutants/` - Mutation testing artifacts