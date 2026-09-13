"""AI VTuber - Emotion and Topic Analyzer

Lightweight word/content-based emotion detection and topic extraction.
Does NOT use external LLM calls - runs locally with keyword/pattern matching.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class AnalysisResult:
    """Result of analyzing an LLM response."""
    emotion: str
    topic: str
    cleaned_text: str


# Supported emotions (must match Live2D expression capabilities)
SUPPORTED_EMOTIONS = {
    "neutral",
    "happy", 
    "sad",
    "angry",
    "surprised",
    "embarrassed"
}

# Emotion tag pattern for explicit tags
EMOTION_TAG_PATTERN = re.compile(r'^\[(neutral|happy|sad|angry|surprised|embarrassed)\]\s*', re.IGNORECASE)

# Keyword-based emotion scoring
# Each emotion has positive indicators and negative/negation patterns
EMOTION_KEYWORDS = {
    "happy": {
        "positive": [
            "great", "wonderful", "amazing", "fantastic", "awesome", "excellent",
            "love", "loved", "loving", "enjoy", "enjoyed", "fun", "excited",
            "glad", "pleased", "delighted", "thrilled", "satisfied", "proud",
            "happy", "happiness", "cheerful", "joy", "joyful", "smile", "smiling",
            "laugh", "laughing", "haha", "lol", "yay", "woohoo", "congrats",
            "congratulations", "bravo", "well done", "good job", "perfect",
            "beautiful", "nice", "cool", "sweet", "brilliant", "success",
            "succeeded", "fixed", "finally", "works", "working", "solved",
            "accomplished", "achieved", "victory", "win", "won", "winner"
        ],
        "patterns": [
            r"\b(i'm|i am|so|very|really)\s+(happy|glad|pleased|excited|thrilled)\b",
            r"\b(that's|that is|this is|it's|it is)\s+(great|awesome|amazing|wonderful)\b",
            r"\b(finally|at last)\b.*\b(fixed|done|finished|complete|works)\b",
            r"\b(congratulations|congrats|well done|good job|bravo)\b"
        ]
    },
    "sad": {
        "positive": [
            "sad", "sadness", "unhappy", "disappointed", "disappointing",
            "hurt", "hurts", "painful", "pain", "sorry", "apologize", "apology",
            "regret", "regretful", "wish", "wishes", "miss", "missing", "lonely",
            "alone", "depressed", "depressing", "down", "blue", "melancholy",
            "tear", "tears", "crying", "cry", "sob", "sobbing", "ouch", "oof",
            "heartbreaking", "heartbreak", "tragic", "tragedy", "loss", "lost",
            "fail", "failed", "failing", "failure", "mistake", "mistakes",
            "wrong", "broken", "break", "breaking", "tired", "exhausted",
            "frustrated", "frustrating", "annoyed", "annoying"
        ],
        "patterns": [
            r"\b(i'm|i am|feel|feeling)\s+(sad|upset|disappointed|down|blue)\b",
            r"\b(that's|that is|this is|it's|it is)\s+(sad|disappointing|hurtful|painful)\b",
            r"\b(i\s+(wish|hope|miss|regret)|if only)\b",
            r"\b(sorry|apologize|my bad|oops)\b"
        ]
    },
    "angry": {
        "positive": [
            "angry", "anger", "mad", "furious", "outraged", "outrageous",
            "infuriated", "irritated", "annoyed", "frustrated", "aggravated",
            "pissed", "livid", "enraged", "irate", "hostile", "aggressive",
            "hate", "hated", "hating", "loathe", "despise", "stupid", "idiotic",
            "ridiculous", "absurd", "nonsense", "bullshit", "damn", "crap",
            "hell", "why does", "why do", "always", "never", "keeps", "keep"
        ],
        "patterns": [
            r"\b(i'm|i am|so|very)\s+(angry|mad|furious|frustrated|annoyed)\b",
            r"\b(why\s+(does|do|is|are|not|can't|won't))\b",
            r"\b(this|that|it)\s+(sucks|is terrible|is awful|is horrible)\b",
            r"\b(enough|stop it|shut up|give me a break)\b",
            r"!{2,}",  # Multiple exclamation marks
            r"[A-Z]{3,}"  # ALL CAPS words (3+ letters)
        ]
    },
    "surprised": {
        "positive": [
            "wow", "whoa", "omg", "oh my god", "oh my gosh", "really", "seriously",
            "actually", "unexpected", "surprising", "surprised", "shocked",
            "astonished", "amazed", "stunned", "incredible", "unbelievable",
            "can't believe", "cannot believe", "wait", "hold on", "what", "huh",
            "eh", "oh", "ah", "gasp", "no way", "you're kidding", "joking",
            "unexpectedly", "suddenly", "out of nowhere"
        ],
        "patterns": [
            r"\b(wow|whoa|omg|oh my god|oh my gosh)\b",
            r"\b(i can't|i cannot|i couldn't|i could not)\s+believe\b",
            r"\b(wait|hold on|seriously|really)\b[?!]",
            r"\b(what|how|why)\b.*[?!]",
            r"[?!]{2,}"  # Multiple punctuation
        ]
    },
    "embarrassed": {
        "positive": [
            "embarrassed", "embarrassing", "awkward", "awkwardly", "shy", "shyly",
            "blush", "blushing", "flushed", "sheepish", "bashful", "timid",
            "nervous", "nervously", "uneasy", "uncomfortable", "self-conscious",
            "humiliated", "ashamed", "guilty", "oops", "uh oh", "d'oh", "facepalm",
            "cringe", "cringeworthy", "mortified", "flustered", "stutter",
            "um", "uh", "er", "erm", "like", "you know", "kinda", "sorta"
        ],
        "patterns": [
            r"\b(i'm|i am|feel|feeling)\s+(embarrassed|awkward|shy|nervous|ashamed)\b",
            r"\b(oops|uh oh|d'oh|facepalm|my bad)\b",
            r"\b(um|uh|er|erm)\b.*\b(um|uh|er|erm)\b",  # Multiple filler words
            r"\b(don't look|don't watch|no one see)\b"
        ]
    },
    "neutral": {
        "positive": [],
        "patterns": []
    }
}

# Topic keywords and categories
TOPIC_KEYWORDS = {
    "Python": ["python", "py", "script", "import", "pip", "venv", "module", "package"],
    "debugging": ["bug", "error", "fix", "fixed", "debug", "crash", "issue", "problem", "broken", "solve", "solved"],
    "Live2D": ["live2d", "cubism", "model", "avatar", "expression", "parameter", "rendering", "vtuber"],
    "coding": ["code", "coding", "program", "programming", "function", "variable", "loop", "class", "method"],
    "game": ["game", "gaming", "boss", "level", "player", "npc", "quest", "inventory", "save", "load"],
    "Elden Ring": ["elden ring", "eldenring", "malenia", "margit", "godrick", "radahn", "tarnished", "rune"],
    "weather": ["weather", "sunny", "rain", "snow", "cloudy", "temperature", "forecast", "storm"],
    "food": ["food", "eat", "eating", "delicious", "tasty", "recipe", "cook", "cooking", "meal", "lunch", "dinner"],
    "music": ["music", "song", "listen", "listening", "album", "artist", "band", "concert", "melody"],
    "movie": ["movie", "film", "watch", "watching", "show", "series", "episode", "actor", "actress", "director"],
    "book": ["book", "read", "reading", "author", "novel", "chapter", "story", "writer", "literature"],
    "technology": ["tech", "technology", "computer", "laptop", "phone", "device", "software", "hardware", "app"],
    "AI": ["ai", "artificial intelligence", "machine learning", "ml", "neural", "llm", "model", "training"],
    "cats": ["cat", "cats", "kitten", "kittens", "feline", "meow", "pet", "pets"],
    "dogs": ["dog", "dogs", "puppy", "puppies", "canine", "woof", "bark", "pet", "pets"]
}


def analyze_response(text: str) -> AnalysisResult:
    """
    Analyze an LLM response to extract emotion and topic.
    
    Args:
        text: The raw LLM response (may include emotion tag).
        
    Returns:
        AnalysisResult with emotion, topic, and cleaned text.
    """
    if not text or not text.strip():
        return AnalysisResult(emotion="neutral", topic="general", cleaned_text="")
    
    original_text = text
    text_stripped = text.strip()
    
    # Step 1: Check for explicit emotion tag
    explicit_emotion = None
    tag_match = EMOTION_TAG_PATTERN.match(text_stripped)
    if tag_match:
        explicit_emotion = tag_match.group(1).lower()
        text_for_analysis = text_stripped[tag_match.end():].strip()
    else:
        text_for_analysis = text_stripped
    
    # Step 2: Detect emotion from content
    detected_emotion = _detect_emotion(text_for_analysis)
    
    # Step 3: Apply emotion priority
    # If explicit tag exists, use it; otherwise use detected emotion
    final_emotion = explicit_emotion if explicit_emotion else detected_emotion
    
    # Ensure emotion is valid
    if final_emotion not in SUPPORTED_EMOTIONS:
        final_emotion = "neutral"
    
    # Step 4: Extract topic
    topic = _extract_topic(text_for_analysis)
    
    # Step 5: Clean text (remove emotion tag if present)
    if tag_match:
        cleaned_text = text_stripped[tag_match.end():].strip()
    else:
        cleaned_text = text_stripped
    
    return AnalysisResult(
        emotion=final_emotion,
        topic=topic,
        cleaned_text=cleaned_text
    )


def _detect_emotion(text: str) -> str:
    """
    Detect emotion from text using keyword/pattern matching.
    
    Uses a scoring system where each emotion accumulates points
    based on keyword matches and pattern matches.
    
    Args:
        text: Text to analyze (without emotion tag).
        
    Returns:
        Detected emotion string.
    """
    if not text:
        return "neutral"
    
    text_lower = text.lower()
    scores = {emotion: 0 for emotion in SUPPORTED_EMOTIONS}
    
    # Handle negation patterns
    negation_patterns = [
        r"\b(not|n't|never|no)\s+(\w+)",
        r"\b(i'm not|i am not|don't|doesn't|didn't|won't|wouldn't)\s+(\w+)"
    ]
    
    # Find all negated words
    negated_words = set()
    for pattern in negation_patterns:
        for match in re.finditer(pattern, text_lower):
            if match.group(2):
                negated_words.add(match.group(2))
    
    # Score each emotion
    for emotion, keywords in EMOTION_KEYWORDS.items():
        if emotion == "neutral":
            continue
            
        # Score positive keywords (but reduce score if negated)
        for keyword in keywords["positive"]:
            keyword_lower = keyword.lower()
            if keyword_lower in text_lower:
                # Check if this keyword is negated
                is_negated = any(
                    keyword_lower in negated or negated in keyword_lower
                    for negated in negated_words
                )
                if is_negated:
                    # Negated positive words might indicate opposite emotion
                    # e.g., "not angry" -> reduce anger score
                    scores[emotion] -= 1
                else:
                    scores[emotion] += 2
        
        # Score pattern matches
        for pattern in keywords["patterns"]:
            if re.search(pattern, text_lower):
                scores[emotion] += 3
    
    # Special handling for multiple exclamation marks and caps (anger indicator)
    if len(re.findall(r'!', text)) >= 2:
        scores["angry"] += 2
    if len(re.findall(r'[A-Z]{3,}', text)) >= 1:
        scores["angry"] += 1
        scores["surprised"] += 1
    
    # Find highest scoring emotion
    max_score = max(scores.values())
    
    if max_score <= 0:
        return "neutral"
    
    # Get all emotions with the max score
    top_emotions = [e for e, s in scores.items() if s == max_score]
    
    # Tie-breaking priority: surprised > angry > sad > happy > embarrassed > neutral
    priority_order = ["surprised", "angry", "sad", "happy", "embarrassed", "neutral"]
    
    for emotion in priority_order:
        if emotion in top_emotions:
            return emotion
    
    return "neutral"


def _extract_topic(text: str) -> str:
    """
    Extract the main topic from text.
    
    Looks for keywords associated with known topics and returns
    the most relevant topic. Returns "general" if no clear topic emerges.
    
    Args:
        text: Text to analyze.
        
    Returns:
        Short topic description (1-4 words) or "general".
    """
    if not text:
        return "general"
    
    text_lower = text.lower()
    topic_scores = {}
    
    # Score each topic based on keyword matches
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            # Use word boundary matching to avoid false positives
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text_lower))
            score += matches
        
        if score > 0:
            topic_scores[topic] = score
    
    if not topic_scores:
        return "general"
    
    # Return the topic with highest score
    best_topic = max(topic_scores.keys(), key=lambda t: topic_scores[t])
    
    # Special handling for multi-word topics that should stay together
    # Already handled by the keyword lists
    
    return best_topic


def strip_emotion_tag(text: str) -> str:
    """
    Remove emotion tag from text if present.
    
    Args:
        text: Text that may start with [emotion] tag.
        
    Returns:
        Text with tag removed, or original text if no tag found.
    """
    if not text:
        return text
    
    match = EMOTION_TAG_PATTERN.match(text.strip())
    if match:
        return text.strip()[match.end():].strip()
    
    return text.strip()
