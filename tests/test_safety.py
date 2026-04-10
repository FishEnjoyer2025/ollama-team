"""Tests for safety constraints."""
import pytest
from backend.orchestrator import PROTECTED_PATHS, PROTECTED_PREFIXES


def test_db_is_protected():
    assert "backend/db.py" in PROTECTED_PATHS


def test_health_is_protected():
    assert "backend/services/health.py" in PROTECTED_PATHS


def test_gitignore_is_protected():
    assert ".gitignore" in PROTECTED_PATHS


def test_frontend_prefix_is_protected():
    assert "frontend/" in PROTECTED_PREFIXES


def test_git_prefix_is_protected():
    assert ".git/" in PROTECTED_PREFIXES
