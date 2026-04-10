"""Tests for the orchestrator and safety system."""
import pytest
from backend.orchestrator import Orchestrator, PROTECTED_PATHS, PROTECTED_PREFIXES


def test_protected_paths_filter():
    """Verify protected files are filtered out."""
    orch = Orchestrator()
    paths = ["backend/agents/coder.py", "backend/db.py", ".gitignore"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == ["backend/agents/coder.py"]


def test_protected_prefix_filter():
    """Verify protected prefixes block files under them."""
    orch = Orchestrator()
    paths = ["docs/spec.md", ".git/config"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == []


def test_frontend_pages_allowed():
    """Agents can modify frontend pages and components."""
    orch = Orchestrator()
    paths = ["frontend/src/pages/Settings.tsx", "frontend/src/components/NewWidget.tsx"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == paths


def test_core_frontend_protected():
    """Core frontend wiring files are still protected."""
    orch = Orchestrator()
    paths = ["frontend/src/App.tsx", "frontend/src/api.ts", "frontend/src/main.tsx"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == []


def test_backend_agents_allowed():
    """Agents can modify their own code."""
    orch = Orchestrator()
    paths = ["backend/agents/reviewer.py", "backend/services/tools.py", "prompts/planner.md"]
    allowed = orch._validate_file_paths(paths)
    assert allowed == paths


def test_allowed_paths_pass():
    """Verify non-protected files pass through."""
    orch = Orchestrator()
    paths = [
        "backend/agents/planner.py",
        "prompts/planner.md",
        "tests/test_new.py",
    ]
    allowed = orch._validate_file_paths(paths)
    assert allowed == paths
