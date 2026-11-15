---
name: test-conventions
description: Test conventions for cookbook. Use when writing, changing, reviewing or refactoring tests, fixtures, pytest cases or test data, including tests added as part of a feature or bug fix.
---

# Test conventions

## Level
Runner-first: tests call the `queries`, `search`, `notes` and `export` functions, and the routes through FastAPI's `TestClient`, against a throwaway SQLite database in `tmp_path`, created by the app's migrations and filled with a few invented recipes in `conftest.py`. No fakes: the app has no external boundary. Pure-function cases only for FTS5 query escaping in `search.py`, whose input space is too large to cover through the database.

<!-- agents-md python-tests v1 -->
## Cases and parametrize
- Use `pytest.mark.parametrize` for a flat table of scalar values or to enumerate an enum or constant. Use `pytest-cases` when each scenario bundles its own data.
- A `case_*` function names the scenario, holds its data inline and returns one value, or a tuple that `@parametrize_with_cases("article_candidates, expected_threshold", cases=".")` unpacks into named, typed test arguments. Each tuple element is one whole value (a frame, a model, a list, the expected result), never a record's fields spread across positions.
- Annotate each case's return type. When several cases return the same tuple, name it once with a type alias above them, commented with what each element is: `type ScoringCase = tuple[...]`, or `ScoringCase: TypeAlias = tuple[...]` where the repo supports Python below 3.12. Don't add a test-only class to hold a scenario.
- Keep cases in the test's own module, above the test: pytest-cases only collects cases defined before the test, so a case below it never runs and fails nothing.
- When one module holds cases for several tests, tag them with `@case(tags=...)` and select with `has_tag`, never `glob`: a renamed case silently drops out of a glob.
- Never pass fixture names as strings for `request.getfixturevalue`, and never branch inside a test on which scenario is running. Whatever differs between scenarios is a value the case returns.

## Fixtures
- A fixture arranges one thing and returns it: no factories, nested functions or assertions.
- `conftest.py` holds the fixtures that more than one test file uses. Never import from `conftest.py`.
- Inline a fixture that only one test uses. The exception is data too large to read inside a test.
- Share behaviour (setup, act), never the data under test.

## Stand-ins
- Patch with `mocker.patch.object` where the module under test looks the name up. Use `mocker.create_autospec` for function-shaped boundaries so call signatures are checked.
- For HTTP, use `httpx.MockTransport` and assert the recorded request contents.
- A fixed-return stand-in must still tell business-significant requests apart; use a small fake when the response depends on the request.
- Construct real Pydantic models and settings with real values; don't mock them.

## Assertions
- Choose input data that makes a plausible mistake (wrong join, threshold, column, ignored batch) change the asserted output.
- Assert a call only where the call is the behaviour, and then assert what it carries.
- A known defect gets `pytest.mark.xfail(strict=True, raises=..., reason=...)` expressing the intended behaviour, never a test that pins the defect.

## Docstrings and comments
- A test's docstring says what it proves. Comments say why test data exists, not what an assertion does. Never say "happy path".
<!-- /agents-md python-tests -->

## This repo
- Stand-ins: none; the app has no external boundary. Anything that seems to need one is a design question to raise first.
- Search tests need recipes that share words across fields (an ingredient in one recipe that is a tag or title word in another), so a query searching the wrong column changes which slugs come back.
- Test data is invented: never real recipes, images, people or places, because the repo is public.
- Route tests cover each write route as a guest (rejected) and as the admin.
- Assert lists of slugs in their expected order, not counts.
