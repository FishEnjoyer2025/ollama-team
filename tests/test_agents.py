"""Tests for agent base class."""
import json
import pytest
from backend.agents.base import Agent


def test_parse_json_direct():
    """Direct JSON string is parsed."""
    agent = Agent()
    result = agent._parse_json('{"key": "value"}')
    assert result == {"key": "value"}


def test_parse_json_code_block():
    """JSON in markdown code block is extracted."""
    agent = Agent()
    text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
    result = agent._parse_json(text)
    assert result == {"key": "value"}


def test_parse_json_embedded():
    """JSON embedded in prose is extracted."""
    agent = Agent()
    text = 'The answer is {"description": "test", "risk": "low"} and that is all.'
    result = agent._parse_json(text)
    assert result == {"description": "test", "risk": "low"}


def test_parse_json_fallback():
    """Unparseable text gets wrapped in raw_response."""
    agent = Agent()
    result = agent._parse_json("just some text with no json")
    assert "raw_response" in result
    assert result["raw_response"] == "just some text with no json"
