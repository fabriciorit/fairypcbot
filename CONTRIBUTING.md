# Contributing to fairypcbot

First off, thank you for considering contributing to fairypcbot!

## Development setup

To set up your local development environment:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/fairypcbot.git
   cd fairypcbot
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the project in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Running tests

Before submitting a pull request, please ensure all tests and checks pass:

- Run unit tests: `pytest`
- Check code formatting and linting: `ruff check src tests`
- Check type hints: `mypy src/fairypcbot/schemas src/fairypcbot/registry`

## The provenance rule

For components in the `library/` directory, **only authorial artifacts** are allowed.
- PRs **must not** add artifacts with `source: easyeda` or `source: datasheet` to the `library/` directory.
- Vendor-sourced data is obtained on demand via `fae catalog fetch` and stored locally in the user's cache.

## Documentation size contract

The framework adheres to strict size constraints for LLM documentation (`docs/llm/`):
- `INDEX.md` must be ≤ 150 lines.
- Each topic document must be ≤ 400 lines.
- These limits are enforced by CI tests.

## Code style

- Use `ruff` for code formatting and linting.
- Maximum line length is 100 characters.
- Write docstrings in clear English.

## Commit messages

We prefer [Conventional Commits](https://www.conventionalcommits.org/) for commit messages (e.g., `feat: add awesome feature`, `fix: resolve bug in routing`).
