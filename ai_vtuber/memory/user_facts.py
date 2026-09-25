"""AI VTuber - Deterministic durable-user-fact extraction.

Cheap regex-based detection of facts that belong in ``data/user.md``:
names, nicknames, likes/dislikes, preferences, tools used, ongoing
projects, favorites and interests.  Used two ways:

1. During conversation (no LLM call): :func:`detect_fact_candidates`
   flags messages that *might* contain durable facts so the session gets
   a meaningful title / can be consolidated even if the app dies.
2. At consolidation time as a RELIABILITY FALLBACK: when the LLM
   extraction fails or returns malformed JSON, :func:`extract_user_facts`
   still produces structured entries so nothing obvious is lost.

Every entry carries a ``category`` so it lands under the right heading in
user.md, plus optional ``supersedes`` hints for conflict resolution
("I used to use X but now I use Y" replaces the old tool fact).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .consolidation import contains_secret
from .titler import slugify

# Categories -> user.md section headings
CATEGORY_SECTIONS = {
    "identity": "Identity",
    "nickname": "Identity",
    "likes": "Likes",
    "dislikes": "Dislikes",
    "preferences": "Preferences",
    "interests": "Interests",
    "projects": "Projects",
    "environment": "Environment",
}

_NAME_STOP = {
    "going", "not", "so", "very", "really", "just", "here", "there", "now",
    "back", "still", "always", "never", "sure", "sorry", "glad", "happy",
    "trying", "thinking", "feeling", "looking", "kind", "sort", "bit",
    "little", "boy", "girl", "friend", "name's", "self", "own", "favorite",
    "favourite", "new", "old", "same", "different", "actual", "honest",
}

_CLEAN = lambda s: re.sub(r"\s+", " ", (s or "").strip(" .,;!?\n\t"))

_PATTERNS = [
    # identity (explicit compiled regexes below; placeholders here) ----
    ("name", "identity", None, "Name: {value}"),
    ("name-lower", "identity", None, "Name: {value}"),
    ("nickname", "nickname", None, "Nickname: {value}"),
    # likes / dislikes --------------------------------------------------
    ("like", "likes",
     re.compile(r"\bi (?:really |pretty |quite |kinda |kind of )?(?:like|love|enjoy|adore|am into)\s+"
                r"(.{2,120})", re.IGNORECASE),
     "Likes {value}."),
    ("dislike", "dislikes",
     re.compile(r"\bi (?:really |truly |absolutely )?(?:dont like|don't like|do not like|dislike|hate|can't stand|cannot stand)\s+"
                r"(.{2,120})", re.IGNORECASE),
     "Dislikes {value}."),
    # preferences --------------------------------------------------------
    ("prefer", "preferences",
     re.compile(r"\bi prefer(?: using| to use|ing)?\s+(.{2,120})", re.IGNORECASE),
     "Prefers {value}."),
    ("favorite", "interests",
     re.compile(r"\bmy favou?rite\s+([\w \-]{1,40}?)\s+(?:is|are)\s+(.{2,120})",
                re.IGNORECASE),
     "Favorite {slot1}: {value}."),
    # environment / tools --------------------------------------------------
    ("use", "environment",
     re.compile(r"\bi(?: currently| usually| generally)? use\s+(.{2,120})",
                re.IGNORECASE),
     "Uses {value}."),
    ("working-on", "projects", None, "Working on {value}."),
    # interests --------------------------------------------------------------
    ("interested", "interests",
     re.compile(r"\bi(?:'m| am)? (?:very |really )?(?:interested in|into|passionate about)\s+(.{2,120})",
                re.IGNORECASE),
     "Interested in {value}."),
]

# "used to X but now Y" / "switched from X to Y" -> supersede old fact
_SWITCH_RE = re.compile(
    r"\bi (?:used to(?: use)?|switched from|moved from|migrated from)\s+(.+?)"
    r"(?:\s+but now(?: use)?|\s+now(?: use)?|\s+to)\s+(.+)", re.IGNORECASE)

# "call me X" only counts as a nickname when preceded by an explicit cue.
_NAME_RX = re.compile(
    r"(?:my name(?: is|'s)|i am called|i'm called|this is|name is)\s+"
    r"([A-Z][\w'\u3040-\u30ff\u4e00-\u9fff-]*)")
_NAME_LOWER_RX = re.compile(r"\bmy name is ([a-z][\w'-]+)", re.IGNORECASE)
_NICKNAME_RX = re.compile(
    r"(?:you can call me|my nickname(?: is|'s)|please call me|"
    r"or just call me)\s+([A-Za-z][\w'\u3040-\u30ff\u4e00-\u9fff-]*)",
    re.IGNORECASE)
_WORKING_RX = re.compile(
    r"\bi(?:'m| am| m)? (?:currently |also )?(?:working on|building|developing)\s+(.{2,160})",
    re.IGNORECASE)

_GENERIC_OBJECTS = {
    "it", "this", "that", "them", "these", "those", "everything", "anything",
    "something", "what", "how", "so", "to", "the", "a", "an", "some", "more",
    "things", "time", "much", "too", "not", "doing", "playing", "using",
}


def _clean_value(v: str) -> str:
    v = _CLEAN(v)
    # trim trailing clause noise: keep at most ~8 words unless clearly one noun
    v = re.split(r"[,;]\s+(?:and|but)\s+", v)[0]
    return _CLEAN(v)


def _looks_durable(category: str, value: str) -> bool:
    if not value or len(value) < 2 or len(value) > 160:
        return False
    first = value.split()[0].lower().strip(".,!")
    if first in _GENERIC_OBJECTS:
        return False
    if category == "identity":
        token = value.split()[0]
        if token.lower() in _NAME_STOP or len(token) < 2 or len(token) > 30:
            return False
        if not re.match(r"[^\d]", token):   # names don't start with digits
            return False
    return True


def extract_user_facts(messages: List[str]) -> List[Dict]:
    """Deterministically pull durable user facts out of raw user messages.

    Returns entries shaped like the consolidation pipeline expects::

        {"fact": "...", "supersedes": [...], "category": "likes"}
    """
    entries: List[Dict] = []
    seen_norms = set()

    def add(fact: str, category: str, supersedes: Optional[List[str]] = None):
        norm = fact.lower().rstrip(".")
        key = re.sub(r"[^a-z0-9 ]", "", norm)
        key = re.sub(r"\s+", " ", key).strip()
        if key in seen_norms:
            return
        seen_norms.add(key)
        entries.append({"fact": _CLEAN(fact), "supersedes": supersedes or [],
                        "category": category})

    for msg in messages:
        text = (msg or "").strip()
        if not text or contains_secret(text):
            continue
        switch = _SWITCH_RE.search(text)
        if switch:
            old, new = _clean_value(switch.group(1)), _clean_value(switch.group(2))
            if _looks_durable("preferences", new):
                # phrase replacement so fallback_merge can drop the old bullet
                add(f"Prefers {new} (previously {old})", "preferences",
                    supersedes=[f"Uses {old}", f"Prefers {old}"])
                continue
        for pid, category, rx, template in _PATTERNS:
            if rx is None:      # identity/working-on patterns (named regexes)
                if pid == "name":
                    m = _NAME_RX.search(text)
                elif pid == "name-lower":
                    m = _NAME_LOWER_RX.search(text)
                elif pid == "nickname":
                    m = _NICKNAME_RX.search(text)
                else:
                    m = _WORKING_RX.search(text)
            else:
                m = rx.search(text)
            if not m:
                continue
            groups = m.groups()
            value = _clean_value(groups[-1])
            if not _looks_durable(category, value):
                continue
            slots = {"value": value.rstrip(".,!?")}
            if "{slot1}" in template and len(groups) >= 2:
                slots["slot1"] = _clean_value(groups[0]).lower()
            fact = template.format(**slots)
            if category == "identity" and fact.lower().startswith("name:"):
                # normalize capitalization of proper names typed lowercase
                nm = fact.split(":", 1)[1].strip()
                if nm.islower():
                    fact = "Name: " + nm.capitalize()
            add(fact, category)
            break  # one fact per message keeps things conservative
    return entries


def detect_fact_candidates(text: str) -> bool:
    """Very cheap check: could this message contain a durable user fact?

    Used during live conversation WITHOUT any LLM call (title refresh &
    consolidation gating only).
    """
    t = text.lower()
    if len(t) < 8:
        return False
    for cue in ("my name", "i like", "i love", "i hate", "i dislike",
                "i prefer", "i use", "i'm working", "i am working",
                "my favorite", "my favourite", "call me", "interested in",
                "i enjoy", "used to", "switched from"):
        if cue in t:
            return True
    return False


def categorize_entry(entry: Dict) -> str:
    """Best-effort section mapping for entries lacking an explicit category."""
    cat = entry.get("category")
    if cat in CATEGORY_SECTIONS:
        return CATEGORY_SECTIONS[cat]
    f = str(entry.get("fact", "")).lower()
    for cue, section in (("name:", "Identity"), ("nickname:", "Identity"),
                         ("likes ", "Likes"), ("dislikes ", "Dislikes"),
                         ("prefers ", "Preferences"), ("uses ", "Environment"),
                         ("working on ", "Projects"),
                         ("interested in ", "Interests"),
                         ("favorite ", "Interests")):
        if f.startswith(cue) or f". {cue}" in f:
            return section
    return "Important Context"


def route_entries_to_sections(content: str, entries: List[Dict]) -> str:
    """Insert categorized bullets under their matching ``## Section`` heading.

    Deterministic alternative to blind appending: dedupes against existing
    bullets (normalized substring match), removes superseded bullets, and
    creates missing sections before the ``## Updated`` footer.  The
    ``## Updated`` section is refreshed with today's India date.
    """
    from ..utils.time import now_india
    lines = content.splitlines()
    # index sections: name -> line index of heading
    sec_idx = {}
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("## "):
            sec_idx.setdefault(s[3:].strip(), i)

    # remove superseded bullets first
    removed = set()
    for e in entries:
        for old in e.get("supersedes") or []:
            norm_old = re.sub(r"[^a-z0-9 ]", "", str(old).lower())
            norm_old = re.sub(r"\s+", " ", norm_old).strip().rstrip(".")
            if not norm_old:
                continue
            for i, ln in enumerate(lines):
                if i in removed or not ln.strip().startswith("- "):
                    continue
                norm_ln = re.sub(r"[^a-z0-9 ]", "", ln.strip()[2:].lower())
                norm_ln = re.sub(r"\s+", " ", norm_ln).strip().rstrip(".")
                norm_ln = re.sub(r"_\(added [\d-]+\)_", "", norm_ln).strip()
                if norm_ln == norm_old or norm_old in norm_ln:
                    removed.add(i)

    existing_norms = []
    for i, ln in enumerate(lines):
        if i in removed or not ln.strip().startswith("- "):
            continue
        n = re.sub(r"[^a-z0-9 ]", "", ln.strip()[2:].lower())
        n = re.sub(r"\s+", " ", n).strip().rstrip(".")
        n = re.sub(r"_\(added [\d-]+\)_", "", n).strip()
        if n:
            existing_norms.append(n)

    inserts: List[tuple[int, str]] = []   # (line index, text)
    new_sections: List[tuple[str, str]] = []
    for e in entries:
        fact = str(e.get("fact", "")).strip().rstrip(".")
        if not fact or contains_secret(fact):
            continue
        norm = re.sub(r"[^a-z0-9 ]", "", fact.lower())
        norm = re.sub(r"\s+", " ", norm).strip()
        if any(norm in x or x in norm for x in existing_norms if x):
            continue      # duplicate / already covered
        existing_norms.append(norm)
        section = categorize_entry(e)
        stamp = now_india().strftime("%Y-%m-%d")
        bullet = f"- {fact} _(added {stamp})_"
        if section in sec_idx:
            hi = sec_idx[section]
            j = hi + 1
            # skip description/placeholder lines directly after heading
            while j < len(lines) and not lines[j].strip().startswith("## "):
                j += 1
            # insert before next heading, after last bullet
            k = j
            while k > hi + 1 and not lines[k - 1].strip():
                k -= 1
            if k > hi + 1 and lines[k - 1].strip().startswith("- (none"):
                # replace placeholder
                inserts.append((k - 1, bullet))
                lines[k - 1] = ""   # mark consumed (delete placeholder)
                removed.add(k - 1)
            else:
                inserts.append((k, bullet))
        else:
            new_sections.append((section, bullet))

    # apply removals + inserts (process high->low to keep indices valid)
    out = list(lines)
    for idx, _ in sorted(((i, 0) for i in removed), reverse=True):
        del out[idx]
    for idx, text in sorted(inserts, key=lambda x: -x[0]):
        out.insert(idx, text)

    # add brand-new sections before "## Updated" (or append)
    if new_sections:
        upd = None
        for i, ln in enumerate(out):
            if ln.strip() == "## Updated":
                upd = i
                break
        block: List[str] = []
        for section, bullet in new_sections:
            block += [f"## {section}", bullet, ""]
        pos = upd if upd is not None else len(out)
        out[pos:pos] = [""] + block

    # refresh ## Updated section
    stamp = now_india().strftime("%Y-%m-%d %H:%M")
    if "## Updated" in "\n".join(out):
        res = []
        skip = False
        done = False
        for ln in out:
            s = ln.strip()
            if s == "## Updated" and not done:
                skip = True
                done = True
                res.append("## Updated")
                res.append("")
                res.append(f"- Last updated: {stamp} (Asia/Kolkata)")
                continue
            if skip:
                if s.startswith("## ") or (s.startswith("# ") and not s.startswith("## ")):
                    skip = False
                    res.append(ln)
                continue
            res.append(ln)
        out = res
    else:
        out += ["", "## Updated", "", f"- Last updated: {stamp} (Asia/Kolkata)", ""]

    text = "\n".join(out).rstrip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text
