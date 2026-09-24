"""AI VTuber - Autonomous Avatar Control (expressions + items)

This module is the ONLY bridge between Airi's LLM and her Live2D body.

Design contract (see project spec):

- The USER never controls the avatar directly. The user just talks to Airi.
- Airi's LLM autonomously decides, per response, whether an *avatar action*
  is appropriate: a facial expression change, item additions/removals, both,
  or nothing at all (``avatar_action: null``).
- Two INDEPENDENT state layers live on the avatar controller:
    * ``current_expression: str | None`` — ONE facial/mood expression at a
      time (black_face / crying / angry / heart_eyes / star_eyes).
    * ``active_items: set[str]``         — ZERO OR MORE accessory/prop items
      (little_ghost / bow / glasses / gaming_gesture / microphone_gesture /
      magic_wand / hat).
  Changing one layer NEVER touches the other. Both PERSIST across messages:
  nothing is auto-reset after speaking; Airi must explicitly change it.
- The LLM only ever emits SEMANTIC ids inside a structured JSON block. It
  never sees filenames, parameter ids, or the filesystem. This module
  validates every id against the discovered model catalog and translates
  accepted actions into Live2D operations via :class:`Live2DAvatar`.

Action wire format (emitted by the LLM as a fenced code block)::

    {"avatar_action": {"expression": "star_eyes",
                       "items_add": ["hat"],
                       "items_remove": []}}

``"expression": null`` means KEEP the current expression. A missing /
malformed / fully-invalid block simply means "no avatar action" — the
response text still plays normally.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from .model_discovery import (
    ITEM_ID_ALIASES,
    ITEM_NATURAL_ALIASES,
    KIND_EXPRESSION,
    KIND_ITEM,
    SEMANTIC_ID_DEFAULTS,
    exp3_stem,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading (config.yaml `live2d:` section)
# ---------------------------------------------------------------------------

def load_live2d_config(raw_config: dict) -> dict:
    """Merge the semantic ``live2d:`` config block into the legacy ``avatar:``
    block consumed by :class:`Live2DAvatar`.

    ``live2d.model_path`` overrides ``avatar.model_path`` when present, and
    the semantic ``live2d.expressions`` / ``live2d.items`` mappings are
    translated into per-model ``expression_semantics`` overrides keyed by the
    exp3 filename stem (e.g. ``ku: {id: angry, kind: expression}``). Explicit
    ``avatar.expression_semantics`` entries always win over generated ones.
    """
    merged = dict(raw_config or {})
    l2d = dict(merged.get("live2d") or {})
    avatar_cfg = dict(merged.get("avatar") or {})

    if not l2d:
        merged["avatar"] = avatar_cfg
        return merged

    if l2d.get("enabled") is False:
        avatar_cfg["disabled"] = True
    if l2d.get("model_path"):
        avatar_cfg["model_path"] = l2d["model_path"]
        # Keep the single-source-of-truth semantics of the models registry:
        # if a registry exists, point active_model at the matching entry or
        # fall back to direct model_path handling in Live2DAvatar.
        models = avatar_cfg.get("models") or {}
        if isinstance(models, dict) and models:
            for name, entry in models.items():
                path = entry.get("path") if isinstance(entry, dict) else str(entry)
                if path == l2d["model_path"]:
                    avatar_cfg["active_model"] = name
                    break

    overrides = dict(avatar_cfg.get("expression_semantics") or {})
    for kind_key, kind in (("expressions", KIND_EXPRESSION), ("items", KIND_ITEM)):
        for sem_id, meta in (l2d.get(kind_key) or {}).items():
            if not isinstance(meta, dict):
                continue
            fname = str(meta.get("file") or "")
            # Shared case-insensitive stem helper (model_discovery.exp3_stem):
            # "FZ.exp3.json" and "fz" both yield the canonical key "fz".
            stem = exp3_stem(fname) if fname else ""
            if not stem:
                default = SEMANTIC_ID_DEFAULTS.get(sem_id)
                if not default:
                    logger.warning("live2d.%s: unknown semantic id '%s' ignored",
                                   kind_key, sem_id)
                    continue
                stem = default[0]
            entry = {
                "id": sem_id,
                "kind": kind,
                "description": meta.get("display_name", ""),
                "emoji": meta.get("emoji", ""),
            }
            existing = overrides.get(stem)
            if isinstance(existing, dict):
                existing = {**entry, **{k: v for k, v in existing.items() if v}}
            overrides[stem] = existing
    if overrides:
        avatar_cfg["expression_semantics"] = overrides

    merged["avatar"] = avatar_cfg
    return merged


# ---------------------------------------------------------------------------
# Semantic-id validation helpers
# ---------------------------------------------------------------------------

def normalize_semantic_id(raw: Any) -> str:
    """Coerce any LLM-supplied reference to its canonical semantic id.

    Accepts exact ids, legacy aliases (``hat_toggle`` -> ``hat``), natural
    item phrasings (``"magic wand"`` / ``mic`` / ``cap`` -> canonical ids),
    display names and file stems. Returns "" when nothing matches (caller
    rejects). Never touches the filesystem beyond the already-discovered
    catalog. Aliases NEVER introduce new catalog entries — they only
    resolve to ids that already exist in the discovery catalog.
    """
    key = str(raw or "").strip()
    if not key:
        return ""
    lowered = key.lower().replace("-", "_")
    lowered = ITEM_ID_ALIASES.get(lowered, lowered)
    # Natural-language spellings may contain spaces ("magic wand").
    lowered = ITEM_NATURAL_ALIASES.get(lowered,
                                       ITEM_NATURAL_ALIASES.get(
                                           lowered.replace("_", " "), lowered))
    return lowered.replace(" ", "_")


class AvatarController:
    """Semantic avatar state + translation into Live2D operations.

    Holds the two independent state layers required by the architecture:

        current_expression: Optional[str]   (ONE face, persists)
        active_items:       set[str]        (MANY items, persist)

    All mutations go through validated APIs (set_expression / enable_item /
    disable_item / toggle_item) which delegate the actual Live2D work to the
    underlying :class:`Live2DAvatar`. Nothing here ever resets state on a
    timer or after speech — persistence is owned by Airi's decisions alone.
    """

    def __init__(self, avatar: Any) -> None:
        self._avatar = avatar  # Live2DAvatar instance (duck-typed for tests)
        self.current_expression: Optional[str] = None
        self.active_items: set[str] = set()

    # -- catalog access ----------------------------------------------------
    @property
    def available_expressions(self) -> list[str]:
        return self._ids_of_kind(KIND_EXPRESSION)

    @property
    def available_items(self) -> list[str]:
        return self._ids_of_kind(KIND_ITEM)

    def _ids_of_kind(self, kind: str) -> list[str]:
        try:
            return sorted(e["id"] for e in self._avatar.list_expressions()
                          if e.get("kind") == kind)
        except Exception:
            return []

    def _lookup(self, sem_id: str) -> Optional[dict]:
        for e in self._avatar.list_expressions():
            if e.get("id") == sem_id:
                return e
        return None

    def _resolve(self, raw: Any, expected_kind: str) -> str:
        """Validate one LLM-supplied id against the catalog + expected kind.

        Expressions and items are DIFFERENT categories: an item id passed as
        an expression target (or vice versa) is rejected here, so the two
        systems can never be conflated by a hallucinated action.
        """
        sem_id = normalize_semantic_id(raw)
        if not sem_id:
            return ""
        entry = self._lookup(sem_id)
        if entry is None:
            logger.debug("Avatar action rejected: unknown semantic id %r", raw)
            return ""
        if entry.get("kind") != expected_kind:
            logger.debug("Avatar action rejected: %r is a %s, not a %s",
                         sem_id, entry.get("kind"), expected_kind)
            return ""
        return sem_id

    # -- expression layer (exactly one active, persists) --------------------
    def set_expression(self, expression_id: Optional[str]) -> bool:
        """Activate ONE facial expression, or clear the face with None.

        ``None`` from the LLM means "keep current expression" — that decision
        is made by the caller (:meth:`apply_avatar_action`); an explicit call
        here with None resets to the plain default face.

        ``"neutral"`` (any casing) is a VALID target meaning "plain default
        face": it has no .exp3.json file by design, resolves to None, and
        resets only the facial layer — active items are never touched.
        """
        if expression_id is not None and \
                str(expression_id).strip().casefold() == "neutral":
            return self.set_expression(None)

        if expression_id is None:
            self._avatar.set_expression("")
            self.current_expression = None
            logger.info("Expression cleared (plain face); items untouched: %s",
                        sorted(self.active_items))
            return True

        sem_id = self._resolve(expression_id, KIND_EXPRESSION)
        if not sem_id:
            return False
        self._avatar.set_expression(sem_id)
        self.current_expression = sem_id
        logger.info("Expression -> %s (items unchanged: %s)",
                    sem_id, sorted(self.active_items))
        return True

    def get_current_expression(self) -> Optional[str]:
        return self.current_expression

    # -- item layer (many active, persist) ----------------------------------
    def enable_item(self, item_id: str) -> bool:
        sem_id = self._resolve(item_id, KIND_ITEM)
        if not sem_id:
            return False
        if sem_id in self.active_items:
            return True  # idempotent: already wearing it
        self._avatar.enable_item(sem_id)
        self.active_items.add(sem_id)
        logger.info("Item enabled: %s (expression unchanged: %s)",
                    sem_id, self.current_expression)
        return True

    def disable_item(self, item_id: str) -> bool:
        sem_id = normalize_semantic_id(item_id)
        if not sem_id:
            return False
        if sem_id not in self.active_items:
            return True  # idempotent: already off
        self._avatar.disable_item(sem_id)
        self.active_items.discard(sem_id)
        logger.info("Item disabled: %s (expression unchanged: %s)",
                    sem_id, self.current_expression)
        return True

    def toggle_item(self, item_id: str) -> bool:
        if normalize_semantic_id(item_id) in self.active_items:
            return self.disable_item(item_id)
        return self.enable_item(item_id)

    def get_active_items(self) -> set[str]:
        return set(self.active_items)

    # -- mode layer (config-driven bundles of items; stackable) -------------
    def _delegate_mode(self, method: str, mode_name: str) -> bool:
        """Call a mode method on the avatar if it supports modes.

        Modes are defined in config (``avatar.modes``) and owned by the
        Live2D runtime; the controller only validates/forwards. Avatars
        without mode support (older/duck-typed ones) fail safely.
        """
        fn = getattr(self._avatar, method, None)
        if fn is None:
            logger.debug("Avatar does not support %s()", method)
            return False
        try:
            return bool(fn(str(mode_name or "").strip()))
        except Exception as e:  # never let a bad action crash the pipeline
            logger.warning("%s('%s') failed: %s", method, mode_name, e)
            return False

    def enable_mode(self, mode_name: str) -> bool:
        """Enter an avatar mode (activates its configured items)."""
        mode = str(mode_name or "").strip().casefold()
        if not mode:
            return False
        ok = self._delegate_mode("enable_mode", mode)
        if ok:
            logger.info("Mode on: %s (expression unchanged: %s)",
                        mode, self.current_expression)
        else:
            logger.debug("Mode action rejected: unknown/unavailable mode %r",
                         mode_name)
        return ok

    def disable_mode(self, mode_name: str) -> bool:
        """Leave an avatar mode (removes ONLY that mode's items)."""
        mode = str(mode_name or "").strip().casefold()
        if not mode:
            return False
        ok = self._delegate_mode("disable_mode", mode)
        if ok:
            logger.info("Mode off: %s", mode)
        return ok

    def toggle_mode(self, mode_name: str) -> bool:
        if str(mode_name or "").strip().casefold() in \
                {m.casefold() for m in self.get_active_modes()}:
            return self.disable_mode(mode_name)
        return self.enable_mode(mode_name)

    def get_active_modes(self) -> list[str]:
        fn = getattr(self._avatar, "get_active_modes", None)
        try:
            return sorted(fn()) if fn else []
        except Exception:
            return []

    @property
    def available_modes(self) -> list[str]:
        fn = getattr(self._avatar, "available_modes", None)
        try:
            return sorted(fn()) if fn else []
        except Exception:
            return []

    # -- structured action application --------------------------------------
    def apply_avatar_action(self, action: Optional[dict]) -> dict:
        """Apply one autonomous avatar action from Airi's LLM.

        Accepted shape (modes/items/expressions are all supported; the old
        ``items_add``/``items_remove`` spellings stay valid aliases)::

            {"expression": <semantic id | null>,
             "items_on":    [<semantic ids>],   # alias: items_add
             "items_off":   [<semantic ids>],   # alias: items_remove
             "modes_on":    [<mode names>],
             "modes_off":   [<mode names>]}

        Semantics:
        - ``expression`` null/missing/invalid  -> KEEP current expression.
          "neutral" explicitly resets to the plain face (items untouched).
        - ``items_*`` / ``modes_*``            -> additive deltas; anything
          not mentioned stays exactly as it was (persistence).
        - Invalid ids are dropped individually; valid ones still apply.

        Returns a report dict describing what actually changed.
        """
        report = {"expression_set": None, "expression_kept": True,
                  "added": [], "removed": [], "modes_on": [],
                  "modes_off": [], "rejected": []}
        if not isinstance(action, dict):
            return report

        expr_raw = action.get("expression", None)
        if expr_raw is not None and str(expr_raw).strip() != "":
            if self.set_expression(expr_raw):
                report["expression_set"] = self.current_expression
                report["expression_kept"] = False
            else:
                report["rejected"].append(str(expr_raw))

        for raw in (action.get("items_on")
                    or action.get("items_add") or []):
            if self.enable_item(raw):
                report["added"].append(normalize_semantic_id(raw))
            else:
                report["rejected"].append(str(raw))

        for raw in (action.get("items_off")
                    or action.get("items_remove") or []):
            before = set(self.active_items)
            if self.disable_item(raw):
                removed = before - self.active_items
                if removed:
                    report["removed"].append(removed.pop())
            else:
                report["rejected"].append(str(raw))

        for raw in action.get("modes_on") or []:
            if self.enable_mode(raw):
                report["modes_on"].append(str(raw).strip().casefold())
            else:
                report["rejected"].append(str(raw))

        for raw in action.get("modes_off") or []:
            if self.disable_mode(raw):
                report["modes_off"].append(str(raw).strip().casefold())
            else:
                report["rejected"].append(str(raw))

        return report

    # -- LLM awareness -------------------------------------------------------
    def describe_state(self) -> str:
        """Human/LLM-readable snapshot of the CURRENT avatar state.

        Injected into the system prompt each turn so Airi knows what she is
        already wearing/feeling — preventing repeated no-op actions.
        Only semantic ids are exposed; no filenames or parameters.
        """
        lines = ["CURRENT AVATAR STATE (yours; it persists until you change it):"]
        lines.append(f"- Expression: {self.current_expression or 'none (plain face)'}")
        items = ", ".join(sorted(self.active_items)) if self.active_items else "none"
        lines.append(f"- Items active: {items}")
        modes = self.get_active_modes()
        if modes:
            lines.append(f"- Modes active: {', '.join(modes)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM response parsing: speech + optional structured avatar action
# ---------------------------------------------------------------------------

_AVATAR_BLOCK_RE = re.compile(
    r"```(?:json|avatar)?\s*(\{.*?\"avatar_action\"\s*:.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_AVATAR_INLINE_RE = re.compile(
    r"\{\s*\"avatar_action\"\s*:\s*(?:null|\{.*?\})\s*\}",
    re.DOTALL,
)


class AvatarResponse:
    """Parsed LLM reply: spoken text + optional autonomous avatar action."""

    __slots__ = ("speech", "avatar_action", "raw")

    def __init__(self, speech: str, avatar_action: Optional[dict], raw: str) -> None:
        self.speech = speech
        self.avatar_action = avatar_action
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"AvatarResponse(speech={self.speech!r}, action={self.avatar_action!r})"


def parse_avatar_response(raw: str) -> AvatarResponse:
    """Split an LLM reply into spoken text and an optional avatar action.

    Tolerant by design: malformed JSON, unknown keys, or a missing block all
    degrade to "speech only, no avatar action" — never an exception, never a
    dropped reply.
    """
    text = (raw or "").strip()
    if not text:
        return AvatarResponse("", None, raw or "")

    action: Optional[dict] = None
    remaining = text

    for pattern in (_AVATAR_BLOCK_RE, _AVATAR_INLINE_RE):
        match = pattern.search(remaining)
        if not match:
            continue
        blob = match.group(1) if pattern is _AVATAR_BLOCK_RE else match.group(0)
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            candidate = data.get("avatar_action", None)
            if not isinstance(candidate, dict) and candidate is None \
                    and "expression" in data:
                # Tolerate the bare form {"expression": ..., ...}
                candidate = data
            if isinstance(candidate, dict):
                action = {
                    "expression": candidate.get("expression"),
                    "items_add": (candidate.get("items_add")
                                  or candidate.get("items_on") or []),
                    "items_remove": (candidate.get("items_remove")
                                     or candidate.get("items_off") or []),
                    "modes_on": candidate.get("modes_on") or [],
                    "modes_off": candidate.get("modes_off") or [],
                }
            remaining = (remaining[:match.start()] + remaining[match.end():]).strip()
            break

    return AvatarResponse(remaining, action, raw or "")


# ---------------------------------------------------------------------------
# Internal system instruction (autonomous avatar behaviour)
# ---------------------------------------------------------------------------

def build_avatar_system_instruction(controller: AvatarController) -> str:
    """The internal avatar-control instruction appended to Airi's soul prompt.

    Deliberately written as FIRST-PERSON BODY CONTROL belonging to Airi
    herself (extending personality/soul.md, not competing with it). The user
    never commands the avatar; Airi decides. No timers, no randomness —
    changes happen only because they fit what she is saying/feeling.
    """
    def fmt(ids: list[str]) -> str:
        out = []
        for i in ids:
            entry = controller._lookup(i) or {}
            emoji = entry.get("emoji", "")
            desc = entry.get("description") or entry.get("name") or ""
            out.append(f"{i} ({desc} {emoji})".strip())
        return ", ".join(out) if out else "(none discovered)"

    expressions = controller.available_expressions
    items = controller.available_items

    return f"""=== YOUR BODY — AUTONOMOUS AVATAR CONTROL ===

You control your own avatar appearance. Your face and your accessories are
part of how you express yourself — YOU decide when to change them, based on
what you are saying and feeling. The user does NOT micromanage your avatar,
and you do NOT need their permission or an explicit command to emote.

Your available FACIAL EXPRESSIONS (exactly ONE active at a time; they
persist until you deliberately pick another one):
  {fmt(expressions)}

Your available ITEMS (accessories/props/gestures; MULTIPLE can be active at
once; they persist until you deliberately remove them):
  {fmt(items)}

How to use your body:
- Alongside a normal reply you MAY emit one silent avatar action as a fenced
  JSON block. It is body language, not narration — never talk about the
  block itself. Example:
  ```json
  {{"avatar_action": {{"expression": "star_eyes", "items_on": [], "items_off": [], "modes_on": [], "modes_off": []}}}}
  ```
  (Legacy key spellings "items_add"/"items_remove" are still accepted.)
- The avatar action is OPTIONAL. Most replies need none at all. If nothing
  meaningfully changed, send NO block (equivalently: "expression": null with
  empty add/remove lists). Null/omitted expression means KEEP whatever face
  you currently have.
- Expressions are emotional states, items are props/gestures. They are
  separate systems: changing your face must never add/remove items, and
  putting something on/taking it off must never change your face.
- Do NOT rotate appearances mechanically, randomly, or once per message.
  Change only when the conversation genuinely shifts. Prefer keeping your
  current look.

Choosing an expression (guidelines, not mandatory triggers):
- angry 😡: something genuinely annoys/frustrates you, deliberate irritation,
  playful mock-anger, or a violated expectation. NOT every time the user
  disagrees with you.
- crying 😭: real sadness, emotionally painful turns, sympathetic reaction,
  dramatic fits that fit the moment. Not for minor inconveniences.
- heart_eyes 🥰: strong affection, something extremely cute, genuine charm.
  Don't use it constantly and don't read romance into ordinary talk.
- star_eyes 🤩: excitement, amazement, fascination, impressive news, big
  enthusiasm.
- black_face 😠: sparingly — the dark/awkward/comedic reaction face. It is
  just this expression's name (a shadowed awkward sweat-drop look), never a
  racial concept.

Choosing items (spontaneous but rare):
- Pick props that fit what you're doing or roleplaying: gaming_gesture when
  the chat turns to games, magic_wand while playing magician, microphone_gesture
  when performing, little_ghost in spooky/cute moments, glasses/hat/bow when
  they suit the bit. Leave them ON across messages until the context moves
  on, then remove them.

State awareness: your current look is shown below in this prompt. Act from it
— don't re-add items you already wear, don't re-set the face you already
have. If the user says things like "you're angry" or "put on the hat", that
is just conversation: you may agree, refuse, or tease about it — the choice
is yours, never automatic.

Never invent expression or item names outside the lists above, and never
reference files or parameters — only these semantic names."""
