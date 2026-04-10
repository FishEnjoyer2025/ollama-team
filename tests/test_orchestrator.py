"""Tests for the orchestrator and safety system."""
import pytest
from backend.orchestrator import Orchestrator, PROTECTED_PATHS, PROTECTED_PREFIXES


def test_protected_paths_filter():
    """Verify protected files are filtered out."""
    orch = Orchestrator()
    paths = ["backend/agents/coder.py", "backend/db.py", ".gitignore", "frontend/src/App.tsx"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == ["backend/agents/coder.py"]


def test_protected_prefix_filter():
    """Verify protected prefixes block all files under them."""
    orch = Orchestrator()
    paths = ["frontend/src/pages/Settings.tsx", "docs/spec.md", ".git/config"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == []


def test_allowed_paths_pass():
    """Verify non-protected files pass through."""
    orch = Orchestrator()
    paths = [
        "backend/agents/planner.py",
        "backend/orchestrator.py",
        "prompts/planner.md",
        "tests/test_new.py",
    ]
    allowed = orch._validate_file_paths(paths)
    assert allowed == paths
