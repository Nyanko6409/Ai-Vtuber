"""AI VTuber - Deterministic semantic session titling.

Generates short, human/LLM-readable titles from the actual conversation
content WITHOUT an extra LLM call per message:

1. A temporary title exists at session creation (timestamp based).
2. Once enough content accumulates, :func:`generate_title` derives a
   slugy topic title deterministically from user messages + keyword cues.
3. The consolidated session summary can refine the title once at close.

Titles are filename-safe, bounded (~60 chars) and never generic when the
transcript contains real content.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

# Ordered keyword cues -> canonical topic phrases.  First match on the
# highest-cue-count bucket wins, which keeps titles deterministic.
_TOPIC_CUES = {
    "live2d": ["live2d", "model3", ".moc3", "expression", "motion group",
              "rigging", "vtuber model", "avatar render"],
    "memory-system": ["memory", "user.md", "memory.md", "session store",
                      "remember", "consolidat", "retrieval", "recall"],
    "github-bug-fix": ["github", "pull request", "commit", "branch",
                       "repository", "merge conflict"],
    "bug-fix": ["bug", "crash", "error", "exception", "traceback", "fix",
                "broken", "not working", "doesn't work", "debug"],
    "llm-integration": ["llm", "lm studio", "lmstudio", "ollama", "prompt",
                        "system prompt", "context window", "token"],
    "stt-tts-audio": ["stt", "tts", "whisper", "microphone", "speech",
                      "audio", "voice", "kittentts"],
    "vision": ["vision", "screen capture", "screenshot", "ocr", "camera"],
    "game-development": ["game dev", "godot", "unity", "elden ring",
                         "zelda", "rpg", "level design"],
    "ui-design": ["interface", "layout", "design", "color scheme", "theme"],
    "project-planning": ["roadmap", "plan for", "schedule", "deadline",
                         "milestone", "todo"],
    "learning": ["how do i", "how to", "explain", "teach me", "learn",
                 "tutorial"],
}

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "has", "was",
    "were", "are", "you", "your", "mine", "what", "when", "where", "why",
    "how", "can", "could", "would", "should", "about", "just", "like",
    "really", "very", "some", "any", "all", "not", "but", "its", "it's",
    "please", "thanks", "hey", "hi", "hello", "from", "into", "our",
    "there", "here", "then", "than", "them", "they", "their", "because",
    "after", "before", "today", "yesterday", "make", "makes", "made",
    "get", "got", "lets", "let", "want", "need", "know", "think", "going",
}

_MAX_LEN = 60


def slugify(text: str) -> str:
    """Filename-safe lowercase-hyphenated slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)


def sanitize_title(title: str) -> str:
    """Make *title* safe as a filename component and bound its length."""
    t = title.strip()
    # drop path separators / control chars entirely
    t = re.sub(r"[\\/\r\n\t\x00-\x1f]", "", t)
    t = re.sub(r'[<>:"|?*\[\]]', "", t)
    t = re.sub(r"\s+", " ", t).strip(" .-")
    if len(t) > _MAX_LEN:
        cut = t[:_MAX_LEN]
        sp = cut.rfind(" ")
        if sp >= _MAX_LEN // 2:
            cut = cut[:sp]
        t = cut.rstrip(" ,.-")
    return t


def extract_keywords(texts: Iterable[str]) -> List[str]:
    """Content words ranked by frequency across *texts* (stable ties)."""
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    idx = 0
    for text in texts:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9+#]{2,}", text):
            lw = w.lower()
            if lw in _STOPWORDS:
                continue
            if lw not in counts:
                first_seen[lw] = idx
                idx += 1
            counts[lw] = counts.get(lw, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
    return [w for w, c in ranked if c >= 1]


def generate_title(messages: List[str], started: str = "",
                   fallback_slug: str = "session") -> str:
    """Deterministic semantic title from raw user-message strings.

    Strategy:
      1. Score configured topic cues against the combined text.
      2. If a topic matched, title = "<Topic Words> <top keyword>".
      3. Otherwise take the most salient content words of the FIRST
         substantive user message (early messages define the topic).
    Never returns a generic 'Chat Session' style title when content exists.
    """
    texts = [m.strip() for m in messages if m and m.strip()]
    if not texts:
        return ""
    blob = " \n ".join(texts).lower()

    scored = []
    for topic, cues in _TOPIC_CUES.items():
        hits = sum(blob.count(c) for c in cues)
        if hits:
            scored.append((hits, topic))
    scored.sort(key=lambda x: -x[0])

    keywords = extract_keywords(texts)

    def cap(w: str) -> str:
        return w.capitalize() if w.islower() else w.upper() if len(w) <= 3 and w not in {"use", "api"} else w

    if scored:
        top_topic = scored[0][1]
        label = top_topic.replace("-", " ").title()
        # fix common acronyms for readability
        for a, b in {"Live2D": "Live2D", "Llm": "LLM", "Stt": "STT",
                     "Tts": "TTS", "Github": "GitHub", "Ui": "UI"}.items():
            label = re.sub(rf"\b{a}\b", b, label)
        # append the strongest non-topic keyword as a qualifier
        topic_words = set(slugify(label).split("-"))
        extra = next((k for k in keywords
                      if slugify(k) not in topic_words and k not in _STOPWORDS),
                     "")
        if extra:
            label = f"{label}: {cap(extra)}"
        return sanitize_title(label)

    # No configured topic: build from the first meaningful user message.
    base = texts[0]
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]+|\d+", base)
             if w.lower() not in _STOPWORDS]
    if not words:  # e.g. pure CJK message
        trimmed = base.replace("\n", " ")
        return sanitize_title(trimmed[:40]) or fallback_slug
    picked: List[str] = []
    used = 0
    for w in words:
        if used + len(w) + 1 > _MAX_LEN - 12:
            break
        picked.append(cap(w))
        used += len(w) + 1
        if len(picked) >= 6:
            break
    title = " ".join(picked)
    # add one more high-frequency keyword if it adds information
    if keywords and slugify(keywords[0]) not in slugify(title).split("-"):
        pass
    return sanitize_title(title) or fallback_slug


def title_from_summary(summary: str, current: str) -> str:
    """Optionally refine *current* title using the consolidated summary.

    Reads the ``## Topics`` bullets; returns the existing title when the
    summary offers nothing better (keeps updates rare & cheap).
    """
    if not summary:
        return current
    topics: List[str] = []
    in_topics = False
    for line in summary.splitlines():
        s = line.strip()
        if s.lower().startswith("## topics"):
            in_topics = True
            continue
        if in_topics:
            if s.startswith("## "):
                break
            if s.startswith("- "):
                topics.append(s[2:])
    if not topics:
        return current
    cand = generate_title(topics)
    return cand or current
