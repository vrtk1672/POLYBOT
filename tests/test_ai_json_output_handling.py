from __future__ import annotations

import pytest

from app.services.ai_mesh_intelligence import _parse_json_object


def test_ai_json_parser_accepts_valid_json() -> None:
    assert _parse_json_object('{"status":"OK","confidence":0.4}')["status"] == "OK"


def test_ai_json_parser_extracts_single_embedded_object() -> None:
    parsed = _parse_json_object('noise {"status":"OK"} trailing')

    assert parsed["status"] == "OK"
    assert parsed["_json_extracted"] is True


def test_ai_json_parser_marks_invalid_json_safely() -> None:
    with pytest.raises(ValueError, match="AI_INVALID_JSON"):
        _parse_json_object("not json")
