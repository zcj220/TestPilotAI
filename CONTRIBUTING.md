# Contributing to TestPilot AI

Thank you for your interest in contributing to TestPilot AI! 🎉

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Poetry
- Docker Desktop (for web testing)
- Git

### Development Setup

1. **Fork the repository** on GitHub

2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/TestPilotAI.git
   cd TestPilotAI
   ```

3. **Install dependencies**:
   ```bash
   poetry install --with dev
   poetry run playwright install chromium
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your AI API key
   ```

5. **Run tests to verify setup**:
   ```bash
   poetry run pytest
   ```

---

## 📝 How to Contribute

### Reporting Bugs

1. **Search existing issues** to avoid duplicates
2. **Create a new issue** with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Screenshots/logs if applicable

### Suggesting Features

1. **Check existing feature requests** in Issues
2. **Create a new issue** with `[Feature Request]` prefix
3. **Describe**:
   - Use case and motivation
   - Proposed solution
   - Alternatives considered

### Submitting Pull Requests

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Follow code style guidelines (see below)
   - Add tests for new features
   - Update documentation if needed

3. **Run tests and linters**:
   ```bash
   poetry run pytest
   poetry run ruff check src/
   poetry run black src/
   poetry run mypy src/
   ```

4. **Commit your changes**:
   ```bash
   git commit -m "feat: add amazing feature"
   ```
   Follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `test:` - Test additions/changes
   - `refactor:` - Code refactoring
   - `chore:` - Maintenance tasks

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request** on GitHub:
   - Clear title and description
   - Reference related issues (e.g., "Fixes #123")
   - Screenshots/demos for UI changes

---

## 🎨 Code Style Guidelines

### Python

- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type Hints**: Required for public APIs
- **Docstrings**: Google style for modules, classes, and public functions

Example:
```python
def execute_test(blueprint: Blueprint, auto_repair: bool = False) -> TestReport:
    """Execute a test blueprint.

    Args:
        blueprint: Test blueprint configuration
        auto_repair: Enable auto-repair loop if True

    Returns:
        Test report with results and bugs

    Raises:
        TestExecutionError: If test execution fails
    """
    pass
```

### TypeScript (Extension)

- **Formatter**: Prettier
- **Linter**: ESLint
- **Style**: 2-space indentation, single quotes

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

Examples:
- `feat(android): add visual AI fallback for Flutter apps`
- `fix(blueprint): handle empty selector in assert_text`
- `docs(readme): update installation instructions`

---

## 🧪 Testing Guidelines

### Writing Tests

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test interactions between components
- **E2E tests**: Test complete workflows (use blueprint runner)

### Test Structure

```python
def test_feature_name():
    """Test description."""
    # Arrange
    input_data = ...
    
    # Act
    result = function_under_test(input_data)
    
    # Assert
    assert result == expected_output
```

### Running Tests

```bash
# All tests
poetry run pytest

# Specific file
poetry run pytest tests/test_blueprint_runner.py

# With coverage
poetry run pytest --cov=src --cov-report=html

# Verbose output
poetry run pytest -v
```

---

## 📚 Documentation

### Code Documentation

- **Docstrings**: Required for all public modules, classes, and functions
- **Type hints**: Required for function signatures
- **Comments**: Explain "why", not "what" (code should be self-explanatory)

### README Updates

- Update `README.md` for user-facing changes
- Update `CHANGELOG.md` for version releases

---

## 🔍 Review Process

1. **Automated checks** must pass:
   - Unit tests
   - Linters (Ruff, Black)
   - Type checking (mypy)

2. **Code review** by maintainers:
   - Code quality and style
   - Test coverage
   - Documentation completeness

3. **Approval and merge**:
   - At least 1 maintainer approval required
   - Squash merge preferred for feature branches

---

## 🌟 Recognition

Contributors will be:
- Listed in `CONTRIBUTORS.md`
- Mentioned in release notes
- Credited in commit history

---

## 📧 Questions?

- **GitHub Discussions** - For general questions
- **GitHub Issues** - For bug reports and feature requests

---

Thank you for contributing to TestPilot AI! 🚀
