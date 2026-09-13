"""Tests for text normalization module."""

import unittest
from ai_vtuber.tts import normalize_text, TextNormalizer


class TestTextNormalization(unittest.TestCase):
    """Test cases for text normalization."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.normalizer = TextNormalizer()
    
    def test_excessive_exclamation_marks(self):
        """Test removal of excessive exclamation marks."""
        self.assertEqual(normalize_text('Hello!!!'), 'Hello!')
        self.assertEqual(normalize_text('Wow!!!!'), 'Wow!')
        self.assertEqual(normalize_text('Amazing!!!!!'), 'Amazing!')
    
    def test_excessive_question_marks(self):
        """Test removal of excessive question marks."""
        self.assertEqual(normalize_text('What???'), 'What?')
        self.assertEqual(normalize_text('Really????'), 'Really?')
    
    def test_excessive_periods(self):
        """Test removal of excessive periods."""
        self.assertEqual(normalize_text('Wait...'), 'Wait.')
        self.assertEqual(normalize_text('Hmm....'), 'Hmm.')
    
    def test_emoji_names(self):
        """Test removal of emoji names."""
        self.assertEqual(normalize_text(':smile: Hello'), 'Hello')
        self.assertEqual(normalize_text('I am :happy: today'), 'I am today')
        result = normalize_text(':smile: I am happy')
        self.assertNotIn(':smile:', result)
    
    def test_bold_markdown(self):
        """Test removal of bold markdown formatting."""
        self.assertEqual(normalize_text('**bold** text'), 'bold text')
        self.assertEqual(normalize_text('__bold__ text'), 'bold text')
    
    def test_italic_markdown(self):
        """Test removal of italic markdown formatting."""
        self.assertEqual(normalize_text('*italic* text'), 'italic text')
        self.assertEqual(normalize_text('_italic_ text'), 'italic text')
    
    def test_stuttering_pattern(self):
        """Test removal of stuttering patterns."""
        self.assertEqual(normalize_text('w-w-what is this?'), 'what is this?')
        self.assertEqual(normalize_text('h-hello there'), 'hello there')
        self.assertEqual(normalize_text('I-I-I think'), 'I think')
    
    def test_empty_string(self):
        """Test handling of empty strings."""
        self.assertEqual(normalize_text(''), '')
        self.assertEqual(normalize_text(None), '')
    
    def test_unicode_emojis(self):
        """Test removal of unicode emojis."""
        # Test with actual emoji characters
        result = normalize_text('Hello 😀')
        self.assertNotIn('😀', result)
        
        result = normalize_text('Cool 😎')
        self.assertNotIn('😎', result)
    
    def test_mixed_formatting(self):
        """Test handling of mixed formatting issues."""
        text = '**Wow!!!** :smile: This is a-amazing'
        result = normalize_text(text)
        self.assertNotIn('**', result)
        self.assertNotIn('!!!', result)
        self.assertNotIn(':smile:', result)
        self.assertNotIn('a-amazing', result)
    
    def test_repeated_words(self):
        """Test removal of repeated words."""
        self.assertEqual(normalize_text('hello hello'), 'hello')
        self.assertEqual(normalize_text('test test test'), 'test')
    
    def test_special_characters(self):
        """Test removal of special characters."""
        result = normalize_text('test@#$%value')
        self.assertNotIn('@', result)
        self.assertNotIn('#', result)
        self.assertNotIn('$', result)
    
    def test_whitespace_cleanup(self):
        """Test whitespace normalization."""
        self.assertEqual(normalize_text('  hello   world  '), 'hello world')
        self.assertEqual(normalize_text('multiple   spaces'), 'multiple spaces')
    
    def test_sentence_spacing(self):
        """Test proper sentence spacing after punctuation."""
        result = normalize_text('Hello.World')
        self.assertIn('. ', result)
    
    def test_code_blocks(self):
        """Test removal of code blocks."""
        result = normalize_text('```python\nprint("hi")\n```')
        self.assertNotIn('```', result)
    
    def test_links(self):
        """Test conversion of markdown links."""
        self.assertEqual(normalize_text('[text](url)'), 'text')
        self.assertEqual(normalize_text('[click here](https://example.com)'), 'click here')
    
    def test_headings(self):
        """Test removal of heading markers."""
        self.assertEqual(normalize_text('# Heading'), 'Heading')
        self.assertEqual(normalize_text('## Subheading'), 'Subheading')
        self.assertEqual(normalize_text('### Title'), 'Title')
    
    def test_real_world_examples(self):
        """Test real-world usage examples."""
        # Example 1: Excited response
        text1 = ':joy: Oh my god!!! This is **amazing**!!!'
        result1 = normalize_text(text1)
        self.assertNotIn('!!!', result1)
        self.assertNotIn(':joy:', result1)
        self.assertNotIn('**', result1)
        
        # Example 2: Confused response
        text2 = 'Wait... w-what??? :confused:'
        result2 = normalize_text(text2)
        self.assertNotIn('...', result2)
        self.assertNotIn('???', result2)
        self.assertNotIn(':confused:', result2)
        
        # Example 3: Normal statement
        text3 = 'Python is a programming language.'
        result3 = normalize_text(text3)
        self.assertEqual(result3, 'Python is a programming language.')


if __name__ == '__main__':
    unittest.main()
