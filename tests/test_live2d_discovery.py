"""Tests for external Live2D model discovery + semantic expression layer.

IMPORTANT: These tests never store Live2D model assets in the repository.
A synthetic, minimal Cubism-3 model tree is generated in a tmp_path
directory (simulating an external VTube Studio installation) and the
discovery/avatar layers are pointed at it via configuration only.
The real GPU runtime (live2d-py) is not required.
"""

import json
import logging
from pathlib import Path

import pytest

from ai_vtuber.avatar.model_discovery import discover_model, format_diagnostic
from ai_vtuber.avatar.live2d import Live2DAvatar, _resolve_model_path

logger = logging.getLogger(__name__)

EXPECTED_MAP = {
    "little_ghost": "cw.exp3.json",
    "black_face": "fz.exp3.json",
    "bow_toggle": "h.exp3.json",
    "crying": "hdj.exp3.json",
    "angry": "ku.exp3.json",
    "heart_eyes": "mz.exp3.json",
    "star_eyes": "sq.exp3.json",
    "glasses_toggle": "x.exp3.json",
    "gaming_gesture": "xx.exp3.json",
    "microphone_gesture": "yj.exp3.json",
    "magic_wand": "zs1.exp3.json",
    "hat_toggle": "zs2.exp3.json",
}

EXPR_PARAMS = {
    "cw": [("PartGhost", 1.0)],
    "fz": [("ParamFaceDark", 1.0)],
    "h": [("PartBow", 0.0)],
    "hdj": [("PartTear", 1.0)],
    "ku": [("Param53", 1.0), ("ParamBrowLForm", -1.0), ("ParamMouthForm", -0.5)],
    "mz": [("PartHeartEye", 1.0)],
    "sq": [("PartStarEye", 1.0), ("ParamEyeLSmile", 1.0), ("ParamEyeRSmile", 1.0)],
    "x": [("PartGlasses", 1.0), ("ParamEyeLOpen", 0.9)],
    "xx": [("PartController", 1.0), ("ParamBodyAngleZ", 10.0)],
    "yj": [("PartMic", 1.0)],
    "zs1": [("PartWand", 1.0), ("ParamAngleZ", -15.0)],
    "zs2": [("PartHat", 0.0), ("ParamAngleY", 5.0)],
}

CN_NAMES = {
    "cw": "小幽灵切换", "fz": "黑脸", "h": "蝴蝶结切换", "hdj": "哭哭",
    "ku": "生气", "mz": "爱心眼", "sq": "星星眼", "x": "眼镜切换",
    "xx": "打游戏手势", "yj": "话筒手势", "zs1": "法杖召唤", "zs2": "帽子切换",
}


@pytest.fixture()
def external_model_dir(tmp_path: Path) -> Path:
    """Create a synthetic external model directory (outside the repo)."""
    root = tmp_path / "Live2DModels" / "魔女"
    root.mkdir(parents=True)

    params = [
        "ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamBreath",
        "ParamEyeLOpen", "ParamEyeROpen", "ParamMouthOpenY", "ParamMouthForm",
        "ParamBrowLForm", "Param53",
    ]
    groups = [{
        "GroupId": f"G{i}", "GroupName": f"Group{i}",
        "Parameters": [{"Id": p, "Name": "n"} for p in params],
    } for i in range(3)]
    cdi = {
        "Version": "R3.0.0",
        "Groups": {
            "ParameterGroups": groups,
            "Parts": [{"Id": f"Part{i}", "Name": "p"} for i in range(10)],
        },
        "CombinedParameters": [],
    }
    (root / "魔女.cdi3.json").write_text(
        json.dumps(cdi, ensure_ascii=False), encoding="utf-8")

    model3 = {
        "Version": "3.0.0",
        "FileReferences": {
            "Moc": "魔女.moc3",
            "Physics": "魔女.physics3.json",
            "Textures": ["textures/texture_00.png"],
        },
        "Expressions": [],  # VTube Studio models often omit these
    }
    (root / "魔女.model3.json").write_text(
        json.dumps(model3, ensure_ascii=False), encoding="utf-8")
    (root / "魔女.moc3").write_bytes(b"MOC3")
    (root / "魔女.physics3.json").write_text(
        '{"Version":"3.0.0","Meta":{},"EffectiveForces":{},"PhysicsMappings":[]}',
        encoding="utf-8")
    (root / "textures").mkdir()
    (root / "textures" / "texture_00.png").write_bytes(b"PNG")

    for stem, plist in EXPR_PARAMS.items():
        data = {"Name": CN_NAMES[stem],
                "Parameters": [{"Id": pid, "Value": v} for pid, v in plist]}
        (root / f"{stem}.exp3.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # A deliberately broken expression file — must be skipped, not crash.
    (root / "broken.exp3.json").write_text("{ not json", encoding="utf-8")
    return root


def test_external_discovery(external_model_dir):
    dm = discover_model(external_model_dir / "魔女.model3.json")
    assert dm.parameter_count == 10
    assert len(dm.parameter_groups) == 3
    assert len(dm.parts) == 10
    assert dm.moc3_path is not None and dm.physics_path is not None
    assert dm.cdi3_path is not None
    # broken.exp3.json skipped, 12 valid ones discovered
    assert len(dm.expressions) == 12
    ids = {e.id: e.file for e in dm.expressions}
    assert ids == EXPECTED_MAP
    # all paths point OUTSIDE the repository, inside the external dir
    for e in dm.expressions:
        assert str(external_model_dir) in e.path


def test_expression_parameter_counts_read_from_files(external_model_dir):
    dm = discover_model(external_model_dir / "魔女.model3.json")
    assert dm.expression_by_id("angry").parameter_count == 3
    assert dm.expression_by_id("heart_eyes").parameter_count == 1
    assert dm.expression_by_id("star_eyes").parameter_count == 3
    assert dm.expression_by_id("glasses_toggle").parameter_count == 2


def test_diagnostic_output(external_model_dir):
    dm = discover_model(external_model_dir / "魔女.model3.json")
    text = format_diagnostic(dm)
    assert "魔女" in text
    for sem, fname in EXPECTED_MAP.items():
        assert sem in text and fname in text


def test_semantic_resolution_via_avatar(external_model_dir):
    av = Live2DAvatar({"model_path": str(external_model_dir / "魔女.model3.json")})
    av._discover_model()
    assert "angry" in av.available_expression_ids()
    exp, path = av._resolve_semantic_expression("heart_eyes")
    assert exp is not None and exp.file == "mz.exp3.json"
    exp, path = av._resolve_semantic_expression("生气")  # Chinese display name
    assert exp is not None and exp.file == "ku.exp3.json"
    # Runtime-less calls degrade gracefully (return False, never raise)
    assert av.trigger_expression("angry") is False
    assert av.trigger_expression("does_not_exist") is False
    assert av.set_parameter("NotAParam", 1.0) is False
    assert av.set_parameter("ParamAngleX", float("nan")) is False


def test_missing_model_path_is_reported(tmp_path, caplog):
    missing = tmp_path / "nope" / "x.model3.json"
    with caplog.at_level(logging.ERROR):
        assert _resolve_model_path(str(missing)) is None
    assert any("Live2D model not found" in r.getMessage() for r in caplog.records)


def test_missing_moc3_reports_error(tmp_path):
    mp = tmp_path / "orphan.model3.json"
    mp.write_text(json.dumps({
        "Version": "3.0.0",
        "FileReferences": {"Moc": "missing.moc3", "Textures": []},
    }), encoding="utf-8")
    dm = discover_model(mp)
    assert any("moc3" in e.lower() for e in dm.errors)
