"""Tests for emotion and topic analyzer."""

import pytest
from ai_vtuber.emotion.analyzer import (
    analyze_response,
    strip_emotion_tag,
    SUPPORTED_EMOTIONS,
    AnalysisResult
)


class TestExplicitEmotionTag:
    """Test handling of explicit emotion tags."""
    
    def test_happy_tag(self):
        result = analyze_response("[happy] I'm so glad!")
        assert result.emotion == "happy"
        assert result.cleaned_text == "I'm so glad!"
    
    def test_sad_tag(self):
        result = analyze_response("[sad] That hurts.")
        assert result.emotion == "sad"
        assert result.cleaned_text == "That hurts."
    
    def test_angry_tag(self):
        result = analyze_response("[angry] Why does this keep breaking?!")
        assert result.emotion == "angry"
        assert result.cleaned_text == "Why does this keep breaking?!"
    
    def test_surprised_tag(self):
        result = analyze_response("[surprised] Wait, really?!")
        assert result.emotion == "surprised"
        assert result.cleaned_text == "Wait, really?!"
    
    def test_embarrassed_tag(self):
        result = analyze_response("[embarrassed] Umm... don't look at me...")
        assert result.emotion == "embarrassed"
        assert result.cleaned_text == "Umm... don't look at me..."
    
    def test_neutral_tag(self):
        result = analyze_response("[neutral] Let's move on.")
        assert result.emotion == "neutral"
        assert result.cleaned_text == "Let's move on."
    
    def test_tag_with_newline(self):
        result = analyze_response("[happy]\nI fixed it!")
        assert result.emotion == "happy"
        assert result.cleaned_text == "I fixed it!"
    
    def test_case_insensitive_tag(self):
        result = analyze_response("[HAPPY] Great job!")
        assert result.emotion == "happy"


class TestEmotionWithoutTag:
    """Test emotion detection from content without explicit tags."""
    
    def test_happy_content(self):
        result = analyze_response("I finally fixed it! That was so satisfying!")
        assert result.emotion == "happy"
    
    def test_sad_content(self):
        result = analyze_response("That really hurt...")
        assert result.emotion == "sad"
    
    def test_angry_content(self):
        result = analyze_response("Why does this keep breaking?!")
        assert result.emotion in ["angry", "surprised"]  # Could be either
    
    def test_surprised_content(self):
        result = analyze_response("Wait, it actually works?!")
        assert result.emotion == "surprised"
    
    def test_embarrassed_content(self):
        result = analyze_response("Umm... don't look at me...")
        assert result.emotion == "embarrassed"
    
    def test_neutral_content(self):
        result = analyze_response("Let's move on to the next step.")
        assert result.emotion == "neutral"
    
    def test_congratulations(self):
        result = analyze_response("Congratulations! Well done!")
        assert result.emotion == "happy"
    
    def test_apology(self):
        result = analyze_response("Sorry, my bad.")
        assert result.emotion == "sad"


class TestNegation:
    """Test handling of negation patterns."""
    
    def test_not_angry(self):
        result = analyze_response("I'm not angry, I'm just disappointed.")
        # Should detect sadness from "disappointed", not anger
        assert result.emotion == "sad"
    
    def test_not_happy(self):
        result = analyze_response("I'm not happy about this.")
        # Negated happiness often indicates sadness
        assert result.emotion in ["sad", "angry"]
    
    def test_positive_without_negation(self):
        result = analyze_response("This is great!")
        assert result.emotion == "happy"


class TestTopicExtraction:
    """Test topic extraction functionality."""
    
    def test_python_debugging_topic(self):
        result = analyze_response("I finally fixed the Python import error.")
        # Should detect either Python or debugging as topic
        assert result.topic in ["Python", "debugging"]
    
    def test_elden_ring_topic(self):
        result = analyze_response("That boss in Elden Ring is ridiculous.")
        assert result.topic == "Elden Ring"
    
    def test_live2d_rendering_topic(self):
        result = analyze_response("Live2D is rendering the model upside down.")
        assert result.topic == "Live2D"
    
    def test_weather_topic(self):
        result = analyze_response("She said the weather should be sunny tomorrow.")
        assert result.topic == "weather"
    
    def test_no_identifiable_topic(self):
        result = analyze_response("I can't believe that happened...")
        assert result.topic == "general"
    
    def test_cats_topic(self):
        result = analyze_response("My cats are so cute today!")
        assert result.topic == "cats"
    
    def test_coding_topic(self):
        result = analyze_response("This function has a bug in the loop.")
        assert result.topic in ["coding", "debugging"]


class TestTextCleaning:
    """Test emotion tag stripping and text cleaning."""
    
    def test_strip_happy_tag(self):
        result = analyze_response("[happy] I finally fixed the Python bug!")
        assert result.cleaned_text == "I finally fixed the Python bug!"
        assert "[happy]" not in result.cleaned_text
    
    def test_no_tag_to_strip(self):
        result = analyze_response("Hello there!")
        assert result.cleaned_text == "Hello there!"
    
    def test_empty_response(self):
        result = analyze_response("")
        assert result.emotion == "neutral"
        assert result.topic == "general"
        assert result.cleaned_text == ""
    
    def test_whitespace_only(self):
        result = analyze_response("   ")
        assert result.emotion == "neutral"
        assert result.topic == "general"


class TestShortResponses:
    """Test handling of short responses."""
    
    def test_single_word_happy(self):
        result = analyze_response("Excellent!")
        assert result.emotion == "happy"
    
    def test_single_word_sad(self):
        result = analyze_response("Ouch.")
        assert result.emotion == "sad"
    
    def test_single_word_surprised(self):
        result = analyze_response("Wow!")
        assert result.emotion == "surprised"
    
    def test_greeting(self):
        result = analyze_response("Hello!")
        assert result.emotion == "neutral"
        assert result.topic == "general"


class TestMultiSentence:
    """Test multi-sentence responses."""
    
    def test_mixed_emotions_dominant_happy(self):
        result = analyze_response("It was hard but I finally solved it! Great job!")
        assert result.emotion == "happy"
    
    def test_mixed_emotions_dominant_sad(self):
        result = analyze_response("I tried but failed. It's disappointing.")
        assert result.emotion == "sad"
    
    def test_complex_topic(self):
        result = analyze_response("The Python code for the game has a bug.")
        # Should pick the highest scoring topic
        assert result.topic in ["Python", "debugging", "game", "coding"]


class TestInvalidTags:
    """Test handling of invalid or malformed tags."""
    
    def test_invalid_tag_name(self):
        # Invalid tag should be ignored, emotion detected from content
        result = analyze_response("[invalid] Hello there!")
        # Since [invalid] is not in our pattern, it's treated as regular text
        assert result.emotion == "neutral"
    
    def test_unclosed_tag(self):
        result = analyze_response("[happy Hello!")
        # Malformed tag - treated as regular text
        assert result.emotion == "neutral"
    
    def test_multiple_tags(self):
        result = analyze_response("[happy][sad] Confusing!")
        # Only first valid tag is captured by regex
        assert result.emotion == "happy"


class TestStripEmotionTag:
    """Test the standalone strip_emotion_tag function."""
    
    def test_strip_valid_tag(self):
        text = "[happy] Hello world!"
        result = strip_emotion_tag(text)
        assert result == "Hello world!"
    
    def test_no_tag(self):
        text = "Hello world!"
        result = strip_emotion_tag(text)
        assert result == "Hello world!"
    
    def test_empty_string(self):
        result = strip_emotion_tag("")
        assert result == ""
    
    def test_tag_with_spaces(self):
        text = "[sad]   I'm sad   "
        result = strip_emotion_tag(text)
        assert result == "I'm sad"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
