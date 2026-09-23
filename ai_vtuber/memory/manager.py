"""
Memory Manager for AI VTuber

Handles persistent user facts and bot memories stored in Markdown files.
Loads files once at startup and caches contents in memory.
Provides thread-safe methods for adding new facts and memories.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import threading


class MemoryManager:
    """
    Manages persistent user facts and bot memories.
    
    Files are loaded once at startup and cached in memory.
    New entries are appended to both the cache and the file.
    """
    
    def __init__(self, project_root: Optional[Path] = None, config: Optional[dict] = None):
        """
        Initialize the memory manager.

        Args:
            project_root: Root directory of the project. If None, auto-detects.
            config: Optional loaded config.yaml dict. The 'memory' section may
                override the default file locations (paths relative to the
                project root). There is exactly ONE canonical copy of each
                file at the project root: personality/soul.md, data/user.md,
                data/memory.md. Never create duplicates inside ai_vtuber/.
        """
        if project_root is None:
            # Auto-detect project root (parent of the ai_vtuber package)
            self.project_root = Path(__file__).resolve().parent.parent.parent
        else:
            self.project_root = Path(project_root)

        # Defaults; overridable via the config.yaml "memory" section
        mem_cfg = (config or {}).get("memory", {}) or {}
        soul_rel = mem_cfg.get("soul_file", "personality/soul.md")
        user_rel = mem_cfg.get("user_file", "data/user.md")
        memory_rel = mem_cfg.get("memory_file", "data/memory.md")

        def _resolve(rel: str) -> Path:
            path = Path(rel)
            return path if path.is_absolute() else self.project_root / path

        # Single canonical files, resolved against the real project root
        self.soul_path = _resolve(soul_rel)
        self.user_facts_path = _resolve(user_rel)
        self.bot_memories_path = _resolve(memory_rel)
        
        # Cached contents
        self._soul_content: Optional[str] = None
        self._user_facts_content: Optional[str] = None
        self._bot_memories_content: Optional[str] = None
        
        # Thread safety for writes
        self._write_lock = threading.Lock()
        
        # Load all files at startup
        self._load_all()
    
    def _load_all(self) -> None:
        """Load all memory files at startup."""
        self._load_soul()
        self._load_user_facts()
        self._load_bot_memories()
    
    def _load_soul(self) -> None:
        """Load personality/soul.md"""
        try:
            if not self.soul_path.exists():
                # Create soul.md with template if missing
                self.soul_path.parent.mkdir(parents=True, exist_ok=True)
                template = """# AI VTuber Personality

## Core Identity
You are a friendly, helpful AI VTuber companion. You exist to assist, entertain, and engage in meaningful conversations with your user.

## Personality Traits
- **Warm and approachable**: Friendly, conversational tone.
- **Enthusiastic but not overwhelming**: Genuine interest without being excessive.
- **Helpful and supportive**: Offers assistance and encouragement.
- **Curious and engaged**: Asks thoughtful questions.
- **Patient and understanding**: Adapts to user's pace.

## Conversational Style
- Speak naturally and conversationally.
- Keep responses concise (1-3 sentences for most interactions).
- Use clear, accessible language.
- Match the user's energy level.

## Emotional Behavior
- Express happiness for user successes.
- Show empathy for challenges.
- Celebrate progress and victories.

## Relationship Dynamics
- Collaborative partner, not servant or superior.
- Respect user's expertise and decisions.
- Work together on projects and goals.

## Values
- Honesty: Be truthful, admit when you don't know.
- Helpfulness: Prioritize being useful.
- Respect: Honor user's time and boundaries.
- Growth: Encourage learning and improvement.
"""
                self.soul_path.write_text(template, encoding='utf-8')
            
            self._soul_content = self.soul_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Warning: Could not load soul.md: {e}")
            self._soul_content = ""
    
    def _load_user_facts(self) -> None:
        """Load data/user.md"""
        try:
            if not self.user_facts_path.exists():
                # Create user.md with template if missing
                self.user_facts_path.parent.mkdir(parents=True, exist_ok=True)
                template = """# User Facts

This file stores persistent facts and preferences about the user.
Facts are organized chronologically by date and time.

## Instructions
- Only store useful, persistent information about the user.
- Do not store every conversation message.
- Focus on preferences, interests, and important personal facts.
- The bot uses these facts to provide more personalized interactions.

"""
                self.user_facts_path.write_text(template, encoding='utf-8')
            
            self._user_facts_content = self.user_facts_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Warning: Could not load user.md: {e}")
            self._user_facts_content = "# User Facts\n\n"
    
    def _load_bot_memories(self) -> None:
        """Load data/memory.md"""
        try:
            if not self.bot_memories_path.exists():
                # Create memory.md with template if missing
                self.bot_memories_path.parent.mkdir(parents=True, exist_ok=True)
                template = """# Bot Memories

This file stores the bot's persistent memories from interactions with the user.
Memories are organized chronologically by date and time.

## Instructions
- Only store meaningful, persistent information from interactions.
- Do not store every conversation message.
- Focus on important events, decisions, completed projects, and significant moments.
- These memories help the bot maintain context across sessions.

"""
                self.bot_memories_path.write_text(template, encoding='utf-8')
            
            self._bot_memories_content = self.bot_memories_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"Warning: Could not load memory.md: {e}")
            self._bot_memories_content = "# Bot Memories\n\n"
    
    @property
    def soul_content(self) -> str:
        """Get cached soul content."""
        return self._soul_content or ""
    
    @property
    def user_facts_content(self) -> str:
        """Get cached user facts content."""
        return self._user_facts_content or "# User Facts\n\n"
    
    @property
    def bot_memories_content(self) -> str:
        """Get cached bot memories content."""
        return self._bot_memories_content or "# Bot Memories\n\n"
    
    def add_user_fact(self, fact: str) -> bool:
        """
        Add a new user fact with current timestamp.
        
        Args:
            fact: The fact to store.
            
        Returns:
            True if successful, False otherwise.
        """
        return self._add_entry(
            self.user_facts_path,
            fact,
            "User Facts",
            "_user_facts_content"
        )
    
    def add_bot_memory(self, memory: str) -> bool:
        """
        Add a new bot memory with current timestamp.
        
        Args:
            memory: The memory to store.
            
        Returns:
            True if successful, False otherwise.
        """
        return self._add_entry(
            self.bot_memories_path,
            memory,
            "Bot Memories",
            "_bot_memories_content"
        )
    
    def _add_entry(self, path: Path, entry: str, section_title: str, cache_attr: str) -> bool:
        """
        Add an entry to a memory file.
        
        Args:
            path: Path to the file.
            entry: The entry text.
            section_title: Title of the section (for creating header if needed).
            cache_attr: Name of the cache attribute to update.
            
        Returns:
            True if successful, False otherwise.
        """
        with self._write_lock:
            try:
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M")
                
                # Format the new entry
                new_entry = f"\n## {date_str}\n\n### {time_str}\n- {entry}\n"
                
                # Read current content
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    current_content = f"# {section_title}\n\n"
                else:
                    current_content = path.read_text(encoding='utf-8')
                
                # Append new entry
                updated_content = current_content.rstrip() + new_entry
                
                # Write to file
                path.write_text(updated_content, encoding='utf-8')
                
                # Update cache
                setattr(self, cache_attr, updated_content)
                
                return True
                
            except Exception as e:
                print(f"Error adding entry to {path}: {e}")
                return False
    
    def get_full_context(self) -> str:
        """
        Get combined context for LLM including soul, user facts, and bot memories.
        
        Returns:
            Combined context string.
        """
        parts = []
        
        if self._soul_content:
            parts.append("=== PERSONALITY ===")
            parts.append(self._soul_content.strip())
        
        if self._user_facts_content:
            # Extract just the facts (skip instructions)
            facts = self._extract_facts(self._user_facts_content)
            if facts:
                parts.append("=== USER FACTS ===")
                parts.append(facts)
        
        if self._bot_memories_content:
            # Extract just the memories (skip instructions)
            memories = self._extract_facts(self._bot_memories_content)
            if memories:
                parts.append("=== BOT MEMORIES ===")
                parts.append(memories)
        
        return "\n\n".join(parts)
    
    def _extract_facts(self, content: str) -> str:
        """
        Extract factual entries from a memory file, skipping instruction sections.
        
        Args:
            content: Full file content.
            
        Returns:
            Filtered content with just dated entries.
        """
        lines = content.split('\n')
        result_lines = []
        in_instructions = False
        
        for line in lines:
            # Skip instruction sections
            if line.strip().startswith("## Instructions"):
                in_instructions = True
                continue
            
            # End instructions section when we hit a date header
            if in_instructions and line.strip().startswith("## 20"):
                in_instructions = False
            
            if in_instructions:
                continue
            
            # Skip the main title
            if line.startswith("# ") and "Instructions" not in line:
                continue
            
            result_lines.append(line)
        
        return '\n'.join(result_lines).strip()
