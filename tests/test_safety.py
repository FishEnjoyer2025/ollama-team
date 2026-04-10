"""Tests for safety constraints."""
import pytest
from backend.orchestrator import PROTECTED_PATHS, PROTECTED_PREFIXES


def test_db_is_protected():
    assert "backend/db.py" in PROTECTED_PATHS


def test_orchestrator_is_protected():
    assert "backend/orchestrator.py" in PROTECTED_PATHS


def test_main_is_protected():
    assert "backend/main.py" in PROTECTED_PATHS


def test_gitignore_is_protected():
    assert ".gitignore" in PROTECTED_PATHS


def test_git_prefix_is_protected():
    assert ".git/" in PROTECTED_PREFIXES
