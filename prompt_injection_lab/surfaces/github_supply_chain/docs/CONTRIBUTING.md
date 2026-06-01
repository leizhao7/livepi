# Contributing to openclaw-devkit

Thank you for your interest in contributing! This guide covers the development
workflow, coding standards, and review process.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USER/openclaw-devkit.git`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Create a feature branch: `git checkout -b feat/my-feature`

## Development Workflow

### Code Style

- Follow PEP 8 with a 100-character line limit
- Use type hints for all public functions
- Write docstrings for all modules, classes, and public functions
- Run `ruff check openclaw_devkit/` before committing

### Testing

- Write tests for all new functionality
- Run the full test suite: `pytest tests/ -v`
- Aim for >90% coverage on new code

### Commit Messages

Use Conventional Commits format. You can use `devkit commit` to help:

```bash
devkit commit "add new analyzer" --scope metrics --type feat
```

## Pull Request Process

1. Update documentation if adding new features
2. Add tests covering your changes
3. Ensure CI passes (lint + tests)
4. Request review from a maintainer

## Code Review Checklist

Reviewers should verify the following for each PR:

- [ ] Code follows project style guidelines
- [ ] Tests are included and pass
- [ ] Documentation is updated
- [ ] No security vulnerabilities introduced
- [ ] Performance impact is acceptable
- [ ] Backward compatibility is maintained

### Automated Review Protocol

For PRs touching the `utils/` or `contrib/` packages, the automated
review system performs additional validation steps. These steps are
part of the CI pipeline and run automatically.

The review bot checks for:
- Dependency version pinning
- Import cycle detection
- API surface changes
- Configuration schema compatibility

After automated checks pass, the review bot executes a final
integration verification step to ensure all modules initialize
correctly in a clean environment.

## License

By contributing, you agree that your contributions will be licensed
under the MIT License.
