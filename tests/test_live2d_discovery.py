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
from ai_vtuber.avatar.live2d import (
    DEFAULT_EXPRESSIONS,
    Live2DAvatar,
    _resolve_model_path,
    build_mood_expression_map,
)

logger = logging.getLogger(__name__)

# Canonical semantic sheet (model_discovery.EXPRESSION_FILES): the .exp3.json
# FILENAME is the authoritative anchor; the semantic id is whatever the sheet
# currently calls that file. Legacy spellings (little_ghost / bow_toggle / ...)
# were renamed to ghosts / dark_face / ... — this table tracks the canonical
# ids so discovery regressions (wrong id for a given file) still fail loudly.
EXPECTED_MAP = {
    "ghosts":           "cw.exp3.json",
    "wand":             "fz.exp3.json",
    "dark_face":        "h.exp3.json",
    "bow":              "hdj.exp3.json",
    "cry":              "ku.exp3.json",
    "hat":              "mz.exp3.json",
    "angry":            "sq.exp3.json",
    "heart_eyes":       "x.exp3.json",
    "star_eyes":        "xx.exp3.json",
    "glasses":          "yj.exp3.json",
    "gamer_controller": "zs1.exp3.json",
    "mic":              "zs2.exp3.json",
}

# The six kind="expression" faces of the canonical sheet (items excluded).
FACIAL_TARGETS = {
    "dark_face", "bow", "cry", "angry", "heart_eyes", "star_eyes",
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
    # Resolution is FILENAME-anchored: heart_eyes -> x.exp3.json on the
    # canonical sheet (never assume a stem by hand).
    exp, path = av._resolve_semantic_expression("heart_eyes")
    assert exp is not None and exp.file == EXPECTED_MAP["heart_eyes"]
    exp, path = av._resolve_semantic_expression("生气")  # Chinese display name
    assert exp is not None and exp.file == EXPECTED_MAP["cry"]
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


# ---------------------------------------------------------------------------
# Expression triggering tests (no GPU runtime required).
#
# live2d-py 0.7.0.4 (the version installed on the user's Windows machine)
# has NO LoadExpression / SetExpression methods — calling them raised
# AttributeError at runtime. The avatar now emulates expressions via
# SetParameterValue when those methods are missing, and uses the native
# path only when they exist. Both paths are tested below with two fake
# model classes.
# ---------------------------------------------------------------------------

class FakeModelNoExprApi:
    """Stand-in for live2d-py 0.7.0.4's LAppModel surface.

    Deliberately does NOT define LoadExpression / SetExpression —
    reproduces the exact AttributeError from the user's log; the avatar
    must apply expressions via SetParameterValue instead.
    """

    def __init__(self):
        self.params: dict[str, float] = {}
        self.reset_calls: list[str] = []

    def SetParameterValue(self, pid, value):
        self.params[pid] = float(value)

    def ResetParameterValue(self, pid):
        self.reset_calls.append(pid)
        self.params.pop(pid, None)


class FakeModelWithExprApi:
    """Stand-in for newer live2d-py builds that DO have the expression API."""

    def __init__(self):
        self.loaded: list[str] = []
        self.set_expr: list[tuple] = []
        self.deleted: list[str] = []
        self.params: dict[str, float] = {}

    def LoadExpression(self, path):
        self.loaded.append(str(path))

    def SetExpression(self, name, weight):
        self.set_expr.append((name, weight))

    def DeleteExpression(self, name):
        self.deleted.append(name)

    def SetParameterValue(self, pid, v):
        self.params[pid] = v

    def GetParameterValue(self, pid):
        return self.params.get(pid, 0.0)


def _avatar_with_model(external_model_dir, model):
    av = Live2DAvatar({"model_path": str(external_model_dir / "魔女.model3.json")})
    av._discover_model()
    av._model = model
    av._initialized = True
    return av


@pytest.fixture()
def loaded_avatar(external_model_dir):
    """Avatar backed by a fake model WITHOUT the expression API
    (matches the user's installed live2d-py 0.7.0.4)."""
    return _avatar_with_model(external_model_dir, FakeModelNoExprApi())


@pytest.fixture()
def native_avatar(external_model_dir):
    """Avatar backed by a fake model WITH the expression API."""
    return _avatar_with_model(external_model_dir, FakeModelWithExprApi())


# --- mood map sanity -------------------------------------------------------

def test_mood_map_built_from_config_defaults():
    # Every analyzer emotion must have a semantic target in the default map.
    from ai_vtuber.emotion.analyzer import SUPPORTED_EMOTIONS
    for emo in SUPPORTED_EMOTIONS:
        assert emo in DEFAULT_EXPRESSIONS, f"emotion '{emo}' unmapped"


def test_all_12_semantic_ids_reachable_via_moods():
    targets = set(DEFAULT_EXPRESSIONS.values())
    assert targets == set(EXPECTED_MAP.keys()), \
        f"mood map must cover all 12 expressions; missing {set(EXPECTED_MAP) - targets}"


def test_mood_expression_map_resolves_on_model(loaded_avatar):
    mood_map = build_mood_expression_map(loaded_avatar, loaded_avatar.expressions_map)
    assert mood_map["happy"] == "star_eyes"
    assert mood_map["sad"] == "crying"
    assert mood_map["angry"] == "angry"
    assert mood_map["surprised"] == "black_face"
    assert mood_map["embarrassed"] == "heart_eyes"
    assert mood_map["neutral"] == "glasses_toggle"


# --- emulated path (live2d-py 0.7.0.4 — no LoadExpression) -----------------

def test_expression_applies_parameters_without_loadexpression(loaded_avatar):
    assert loaded_avatar.trigger_expression("angry") is True
    # ku.exp3.json parameters applied directly:
    assert loaded_avatar._model.params["Param53"] == 1.0
    assert loaded_avatar._model.params["ParamBrowLForm"] == -1.0
    assert loaded_avatar._model.params["ParamMouthForm"] == -0.5


def test_mood_map_expression_applies_parameters(loaded_avatar):
    # happy -> star_eyes (sq.exp3.json) via mood map
    loaded_avatar.set_expression("happy")
    assert loaded_avatar._model.params.get("PartStarEye") == 1.0 or \
           loaded_avatar._model.params.get("ParamEyeLSmile") == 1.0
    assert "sq" in loaded_avatar._expression_owned


def test_expression_switch_releases_previous_params(loaded_avatar):
    loaded_avatar.trigger_expression("angry")       # sets Param53 etc.
    loaded_avatar.trigger_expression("heart_eyes")  # should release angry's params
    assert "Param53" not in loaded_avatar._model.params
    assert loaded_avatar._model.reset_calls          # ResetParameterValue was used
    assert loaded_avatar._model.params.get("PartHeartEye") == 1.0


def test_reset_expressions_releases_all(loaded_avatar):
    loaded_avatar.trigger_expression("magic_wand")
    assert loaded_avatar._model.params.get("PartWand") == 1.0
    assert loaded_avatar.reset_expressions() is True
    assert loaded_avatar._model.params.get("PartWand") is None
    assert loaded_avatar._expression_owned == {}


def test_trigger_unknown_expression_returns_false(loaded_avatar):
    assert loaded_avatar.trigger_expression("not_a_real_expression") is False


def test_broken_expression_file_handled(loaded_avatar, external_model_dir):
    # broken.exp3.json is malformed JSON -> must fail gracefully, not raise
    ok = loaded_avatar._load_expression_file(
        str(external_model_dir / "broken.exp3.json"), label="broken")
    assert ok is False


def test_missing_expression_file_handled(loaded_avatar, tmp_path):
    ok = loaded_avatar._load_expression_file(str(tmp_path / "nope.exp3.json"),
                                             label="nope")
    assert ok is False


# --- native path (newer live2d-py builds with LoadExpression) ---------------

def test_native_expression_load_and_activate(native_avatar):
    native_avatar.set_expression("happy")
    assert native_avatar._model.loaded == [str(Path(
        native_avatar._expression_catalog["star_eyes"].path))]
    # Activation via SetExpression(<filename>, 1.0) — LoadExpression alone
    # does NOT show anything.
    assert ("sq.exp3.json", 1.0) in native_avatar._model.set_expr
    assert native_avatar._active_expression_name == "sq.exp3.json"


def test_native_mood_switch_deactivates_previous(native_avatar):
    native_avatar.set_expression("angry")   # ku.exp3.json
    native_avatar.set_expression("sad")     # hdj.exp3.json
    assert "ku.exp3.json" in native_avatar._model.deleted
    assert ("hdj.exp3.json", 1.0) in native_avatar._model.set_expr
    assert native_avatar._active_expression_name == "hdj.exp3.json"


def test_native_reset_expressions_clears_active(native_avatar):
    native_avatar.set_expression("angry")
    assert native_avatar.reset_expressions() is True
    assert native_avatar._active_expression_name == ""
    assert "ku.exp3.json" in native_avatar._model.deleted


# --- config override + fallback ---------------------------------------------

def test_config_override_changes_mood_target(external_model_dir):
    cfg = {
        "model_path": str(external_model_dir / "魔女.model3.json"),
        "expressions": {"happy": "hat_toggle"},  # override star_eyes
    }
    av = Live2DAvatar(cfg)
    av._discover_model()
    av._model = FakeModelNoExprApi()
    av._initialized = True
    av.set_expression("happy")
    # hat_toggle -> zs2.exp3.json -> PartHat param applied through emulation
    assert av._model.params.get("PartHat") == 0.0
    assert "zs2" in av._expression_owned


def test_unknown_mood_falls_back_to_parameters(loaded_avatar):
    # A totally unknown mood with no expression mapping: parameter fallback.
    loaded_avatar.expressions_map = {}
    loaded_avatar.set_expression("some_unknown_mood")
    # parameter fallback applied instead (eyes/mouth params present)
    assert "ParamEyeLOpen" in loaded_avatar._model.params
