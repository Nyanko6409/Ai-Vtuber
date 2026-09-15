"""
Text normalization for TTS output.

Removes:
- Markdown formatting (*, _, **, __, etc.)
- Emoji names (:smile:, :laughing:, etc.)
- Unicode emojis
- Excessive punctuation (!!!, ???, etc.)
- Special characters that shouldn't be spoken
- Stuttering patterns (w-w-what -> what)

Ensures clean, natural speech output.
"""

import re
from typing import List


# Common emoji names to remove
EMOJI_NAMES = [
    'smile', 'laughing', 'grin', 'joy', 'rofl', 'smirk', 'heart_eyes',
    'kissing_heart', 'kissing', 'kissing_smiling_eyes', 'kissing_closed_eyes',
    'wink', 'blush', 'innocent', 'relaxed', 'upside_down', 'tongue',
    'money_mouth', 'nerd', 'sunglasses', 'hugging', 'confused', 'neutral_face',
    'expressionless', 'no_mouth', 'grimacing', 'rolling_eyes', 'thinking',
    'flushed', 'disappointed', 'worried', 'angry', 'rage', 'pensive',
    'confounded', 'unamused', 'sweat', 'cry', 'sob', 'triumph', 'astonished',
    'fearful', 'cold_sweat', 'disappointed_relieved', 'zipper_mouth',
    'mask', 'thermometer_face', 'head_bandage', 'sleeping', 'zzz', 'poop',
    'hankey', 'shit', 'fire', 'sparkles', 'star', 'dizzy', 'boom', 'collision',
    'sweat_drops', 'droplet', 'dash', 'muscle', 'point_up', 'point_down',
    'point_left', 'point_right', 'thumbsup', 'thumbsdown', 'fist', 'wave',
    'ok_hand', 'clap', 'pray', 'raised_hands', 'open_hands', 'writing_hand',
    'nail_care', 'ear', 'nose', 'eyes', 'eye', 'lips', 'tongue', 'baby',
    'boy', 'girl', 'man', 'woman', 'person_with_blond_hair', 'older_man',
    'older_woman', 'cat', 'dog', 'mouse', 'hamster', 'rabbit', 'fox', 'bear',
    'panda_face', 'koala', 'tiger', 'lion_face', 'cow', 'pig', 'frog',
    'monkey_face', 'chicken', 'penguin', 'bird', 'bat', 'wolf', 'horse',
    'unicorn_face', 'bee', 'bug', 'butterfly', 'snail', 'shell', 'beetle',
    'ant', 'spider', 'scorpion', 'crab', 'snake', 'turtle', 'lizard',
    'octopus', 'squid', 'shrimp', 'tropical_fish', 'fish', 'blowfish',
    'dolphin', 'shark', 'whale', 'whale2', 'crocodile', 'leopard', 'tiger2',
    'water_buffalo', 'ox', 'cow2', 'deer', 'dromedary_camel', 'camel',
    'elephant', 'rhinoceros', 'hippopotamus', 'mouse2', 'rat', 'rabbit2',
    'cat2', 'dog2', 'pig2', 'boar', 'ram', 'sheep', 'goat', 'racehorse',
    'pig_nose', 'sunflower', 'rose', 'tulip', 'hibiscus', 'cherry_blossom',
    'blossom', 'carnation', 'bouquet', 'four_leaf_clover', 'maple_leaf',
    'fallen_leaf', 'leaves', 'mushroom', 'cactus', 'palm_tree', 'evergreen_tree',
    'deciduous_tree', 'seedling', 'herb', 'shamrock', 'christmas_tree',
    'tanabata_tree', 'bamboo', 'gift', 'balloon', 'tada', 'confetti_ball',
    'ribbon', 'diamond_shape_with_a_dot_inside', 'gem', 'crown', 'newspaper',
    'book', 'books', 'bookmark_tabs', 'label', 'moneybag', 'yen', 'dollar',
    'euro', 'pound', 'credit_card', 'chart', 'email', 'envelope', 'inbox_tray',
    'outbox_tray', 'package', 'mailbox', 'postbox', 'battery', 'electric_plug',
    'computer', 'printer', 'keyboard', 'mouse', 'trackball', 'joystick',
    'compression', 'minidisc', 'floppy_disk', 'cd', 'dvd', 'vhs', 'camera',
    'camera_flash', 'video_camera', 'movie_camera', 'projector', 'film_frames',
    'telephone_receiver', 'phone', 'pager', 'fax', 'tv', 'radio', 'microphone',
    'level_slider', 'control_knobs', 'compass', 'stopwatch', 'timer_clock',
    'alarm_clock', 'clock', 'hourglass', 'hourglass_flowing_sand', 'satellite',
    'rocket', 'flying_saucer', 'helicopter', 'steam_locomotive', 'railway_car',
    'bullettrain_side', 'bullettrain_front', 'metro', 'light_rail', 'station',
    'tram', 'monorail', 'mountain_railway', 'train', 'bus', 'oncoming_bus',
    'trolleybus', 'minibus', 'ambulance', 'fire_engine', 'police_car',
    'oncoming_police_car', 'taxi', 'oncoming_taxi', 'car', 'oncoming_automobile',
    'blue_car', 'truck', 'articulated_lorry', 'tractor', 'racing_car', 'motorcycle',
    'motor_scooter', 'bike', 'kick_scooter', 'busstop', 'fuelpump', 'rotating_light',
    'traffic_light', 'vertical_traffic_light', 'construction', 'anchor',
    'boat', 'canoe', 'speedboat', 'passenger_ship', 'ferry', 'motor_boat',
    'ship', 'airplane', 'small_airplane', 'flight_departure', 'flight_arrival',
    'seat', 'parachute', 'parasol_on_ground', 'barber', 'hotsprings',
]


class TextNormalizer:
    """Normalize text for TTS output."""
    
    def __init__(self):
        # Compile regex patterns for efficiency
        self.markdown_patterns = [
            (re.compile(r'\*\*(.+?)\*\*'), r'\1'),  # **bold**
            (re.compile(r'__(.+?)__'), r'\1'),      # __bold__
            (re.compile(r'\*(.+?)\*'), r'\1'),      # *italic*
            (re.compile(r'_(.+?)_'), r'\1'),        # _italic_
            (re.compile(r'~~(.+?)~~'), r'\1'),      # ~~strikethrough~~
            (re.compile(r'`(.+?)`'), r'\1'),        # `code`
            (re.compile(r'```[\s\S]*?```'), ''),    # ```code block```
            (re.compile(r'^#\s+', re.MULTILINE), ''),  # # heading
            (re.compile(r'^##\s+', re.MULTILINE), ''), # ## heading
            (re.compile(r'^###\s+', re.MULTILINE), ''), # ### heading
            (re.compile(r'^####\s+', re.MULTILINE), ''), # #### heading
            (re.compile(r'^#####\s+', re.MULTILINE), ''), # ##### heading
            (re.compile(r'^######\s+', re.MULTILINE), ''), # ###### heading
            (re.compile(r'>\s+', re.MULTILINE), ''),   # > quote
            (re.compile(r'^-\s+', re.MULTILINE), ''),  # - list
            (re.compile(r'^\*\s+', re.MULTILINE), ''), # * list
            (re.compile(r'^\d+\.\s+', re.MULTILINE), ''), # 1. list
            (re.compile(r'\[(.+?)\]\(.+?\)'), r'\1'),  # [text](url)
        ]
        
        # Emoji name pattern: :name:
        self.emoji_name_pattern = re.compile(r':[a-zA-Z0-9_]+:')
        
        # Unicode emoji ranges (common ones)
        self.unicode_emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251"  # Enclosed characters
            "]+",
            flags=re.UNICODE
        )
        
        # Excessive punctuation
        self.excessive_punctuation_patterns = [
            (re.compile(r'!{2,}'), '!'),      # Multiple ! -> single !
            (re.compile(r'\?{2,}'), '?'),     # Multiple ? -> single ?
            (re.compile(r'\.{2,}'), '.'),     # Multiple . -> single .
            (re.compile(r',{2,}'), ','),      # Multiple , -> single ,
            (re.compile(r';{2,}'), ';'),      # Multiple ; -> single ;
            (re.compile(r':{2,}'), ':'),      # Multiple : -> single :
        ]
        
        # Stuttering patterns: w-w-what -> what, h-hello -> hello
        # Handles single character repeats with hyphens (including 3+ repeats like I-I-I think)
        self.stutter_pattern = re.compile(r'\b([a-zA-Z]-)+([a-zA-Z]+)\b')
        
        # Repeated words: hello hello -> hello (applied multiple times for 3+ repeats)
        self.repeated_word_pattern = re.compile(r'\b(\w+)(\s+\1)+\b', re.IGNORECASE)
        
        # Special characters that shouldn't be spoken
        self.special_char_patterns = [
            (re.compile(r'[\\|/\\\\]'), ''),  # Backslashes, pipes
            (re.compile(r'[{}\\[\\]]'), ''),  # Brackets
            (re.compile(r'[&^%$#@~`]+'), ''), # Special symbols
        ]
    
    def normalize(self, text: str) -> str:
        """
        Normalize text for TTS output.
        
        Args:
            text: Raw text from LLM
            
        Returns:
            Cleaned text suitable for TTS
        """
        if not text or not isinstance(text, str):
            return ""
        
        result = text.strip()
        
        # Remove markdown formatting
        for pattern, replacement in self.markdown_patterns:
            result = pattern.sub(replacement, result)
        
        # Remove emoji names (:smile:, etc.)
        result = self.emoji_name_pattern.sub('', result)
        
        # Remove unicode emojis
        result = self.unicode_emoji_pattern.sub('', result)
        
        # Remove special characters
        for pattern, replacement in self.special_char_patterns:
            result = pattern.sub(replacement, result)
        
        # Fix excessive punctuation
        for pattern, replacement in self.excessive_punctuation_patterns:
            result = pattern.sub(replacement, result)
        
        # Fix stuttering: w-w-what -> what (apply multiple times for longer stutters)
        max_iterations = 3
        for _ in range(max_iterations):
            new_result = self.stutter_pattern.sub(lambda m: m.group(2), result)
            if new_result == result:
                break
            result = new_result
        
        # Fix repeated words: hello hello -> hello (apply multiple times for 3+ repeats)
        max_iterations = 3
        for _ in range(max_iterations):
            new_result = self.repeated_word_pattern.sub(r'\1', result)
            if new_result == result:
                break
            result = new_result
        
        # Clean up extra whitespace
        result = re.sub(r'\s+', ' ', result)
        result = result.strip()
        
        # Ensure proper sentence spacing after punctuation
        result = re.sub(r'([.!?])\s*', r'\1 ', result)
        result = result.strip()
        
        return result
    
    def normalize_batch(self, texts: List[str]) -> List[str]:
        """Normalize multiple texts efficiently."""
        return [self.normalize(text) for text in texts]


# Global instance for reuse
_normalizer = None


def get_normalizer() -> TextNormalizer:
    """Get or create the global normalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = TextNormalizer()
    return _normalizer


def normalize_text(text: str) -> str:
    """
    Normalize text for TTS output.
    
    This is the main entry point for text normalization.
    
    Args:
        text: Raw text from LLM
        
    Returns:
        Cleaned text suitable for TTS
    """
    return get_normalizer().normalize(text)
