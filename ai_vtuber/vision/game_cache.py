"""AI VTuber - Game-Aware Visual Cache"""

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CachedEntity:
    """A cached game entity (character, enemy, location, etc.)."""
    entity_type: str  # 'character', 'enemy', 'location', 'ui_element'
    name: str
    confidence: float  # 0.0-1.0 confidence in this identification
    source: str  # 'llm', 'ocr', 'user_hint'
    first_seen: float  # Unix timestamp
    last_seen: float  # Unix timestamp
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'entity_type': self.entity_type,
            'name': self.name,
            'confidence': self.confidence,
            'source': self.source,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'metadata': self.metadata
        }


@dataclass
class ScreenState:
    """Current recognized screen state."""
    game_name: Optional[str] = None
    location: Optional[str] = None
    in_combat: bool = False
    in_menu: bool = False
    in_dialogue: bool = False
    loading: bool = False
    player_health_low: bool = False
    last_update: float = 0.0
    last_significant_event: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'game_name': self.game_name,
            'location': self.location,
            'in_combat': self.in_combat,
            'in_menu': self.in_menu,
            'in_dialogue': self.in_dialogue,
            'loading': self.loading,
            'player_health_low': self.player_health_low,
            'last_update': self.last_update,
            'last_significant_event': self.last_significant_event
        }
    
    def clear(self) -> None:
        """Clear all state (e.g., when game changes)."""
        self.game_name = None
        self.location = None
        self.in_combat = False
        self.in_menu = False
        self.in_dialogue = False
        self.loading = False
        self.player_health_low = False
        self.last_significant_event = None


class GameCache:
    """
    Lightweight cache for recognized game entities and UI information.
    
    Features:
    - Stores detected game names, character names, enemy names, locations
    - Reuses previously recognized information
    - Supports expiration/invalidation when game changes
    - Keeps temporary observations separate from long-term memory
    - Uses SQLite for persistence across sessions
    - Tracks confidence and source information
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        cache_ttl_seconds: float = 3600.0,  # 1 hour default TTL
        min_confidence: float = 0.6  # Minimum confidence to trust
    ):
        """
        Initialize the game cache.
        
        Args:
            db_path: Path to SQLite database (None for in-memory)
            cache_ttl_seconds: Time-to-live for cached entities
            min_confidence: Minimum confidence threshold for caching
        """
        self.cache_ttl = cache_ttl_seconds
        self.min_confidence = min_confidence
        self._lock = threading.Lock()
        self._current_state = ScreenState()
        
        # In-memory entity cache
        self._entities: Dict[str, CachedEntity] = {}
        
        # Initialize SQLite database
        if db_path is None:
            # Use in-memory database
            self._db_path = ":memory:"
        else:
            # Use file-based database
            db_file = Path(db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            self._db_path = str(db_file)
        
        self._init_database()
        logger.info(f"Game cache initialized (db={self._db_path})")
    
    def _init_database(self) -> None:
        """Initialize SQLite database schema."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            # Create entities table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    metadata TEXT,
                    UNIQUE(entity_type, name)
                )
            """)
            
            # Create indexes for faster lookups
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_last_seen ON entities(last_seen)"
            )
            
            # Create game state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize game cache database: {e}")
    
    def add_entity(
        self,
        entity_type: str,
        name: str,
        confidence: float,
        source: str = 'llm',
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add or update a cached entity.
        
        Args:
            entity_type: Type of entity ('character', 'enemy', etc.)
            name: Entity name
            confidence: Confidence score (0.0-1.0)
            source: Source of information ('llm', 'ocr', 'user_hint')
            metadata: Additional metadata
            
        Returns:
            True if entity was added/updated, False if rejected
        """
        if confidence < self.min_confidence:
            logger.debug(
                f"Entity '{name}' rejected: confidence {confidence:.2f} "
                f"below threshold {self.min_confidence:.2f}"
            )
            return False
        
        now = time.time()
        key = f"{entity_type}:{name}"
        
        with self._lock:
            # Check if entity exists
            existing = self._entities.get(key)
            
            if existing:
                # Update existing entity
                if confidence > existing.confidence:
                    # Only update if new confidence is higher
                    existing.confidence = confidence
                    existing.source = source
                existing.last_seen = now
                if metadata:
                    existing.metadata.update(metadata)
                    
                logger.debug(
                    f"Updated entity '{name}' (confidence={confidence:.2f})"
                )
            else:
                # Create new entity
                entity = CachedEntity(
                    entity_type=entity_type,
                    name=name,
                    confidence=confidence,
                    source=source,
                    first_seen=now,
                    last_seen=now,
                    metadata=metadata or {}
                )
                self._entities[key] = entity
                
                # Persist to database
                self._persist_entity(entity)
                
                logger.info(
                    f"Cached entity: {entity_type}='{name}' "
                    f"(confidence={confidence:.2f}, source={source})"
                )
            
            return True
    
    def get_cached_entities(
        self,
        entity_type: Optional[str] = None,
        min_confidence: Optional[float] = None,
        max_age_seconds: Optional[float] = None
    ) -> List[CachedEntity]:
        """
        Get cached entities with optional filtering.
        
        Args:
            entity_type: Filter by entity type (None for all)
            min_confidence: Minimum confidence threshold
            max_age_seconds: Maximum age in seconds (None for no limit)
            
        Returns:
            List of matching CachedEntity objects
        """
        now = time.time()
        threshold_conf = min_confidence or self.min_confidence
        
        with self._lock:
            entities = []
            
            for entity in self._entities.values():
                # Filter by type
                if entity_type and entity.entity_type != entity_type:
                    continue
                    
                # Filter by confidence
                if entity.confidence < threshold_conf:
                    continue
                
                # Filter by age
                if max_age_seconds:
                    age = now - entity.last_seen
                    if age > max_age_seconds:
                        continue
                
                entities.append(entity)
            
            # Sort by confidence (highest first)
            entities.sort(key=lambda e: e.confidence, reverse=True)
            
            return entities
    
    def get_entity(
        self,
        entity_type: str,
        name: str
    ) -> Optional[CachedEntity]:
        """Get a specific entity by type and name."""
        key = f"{entity_type}:{name}"
        with self._lock:
            return self._entities.get(key)
    
    def remove_entity(self, entity_type: str, name: str) -> bool:
        """Remove an entity from the cache."""
        key = f"{entity_type}:{name}"
        with self._lock:
            if key in self._entities:
                del self._entities[key]
                self._remove_entity_from_db(entity_type, name)
                logger.info(f"Removed entity: {entity_type}='{name}'")
                return True
            return False
    
    def invalidate_old_entities(self, max_age_seconds: Optional[float] = None) -> int:
        """
        Remove entities older than TTL or specified age.
        
        Returns:
            Number of entities removed
        """
        now = time.time()
        max_age = max_age_seconds or self.cache_ttl
        removed = 0
        
        with self._lock:
            keys_to_remove = []
            
            for key, entity in self._entities.items():
                age = now - entity.last_seen
                if age > max_age:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                entity = self._entities[key]
                del self._entities[key]
                self._remove_entity_from_db(entity.entity_type, entity.name)
                removed += 1
        
        if removed > 0:
            logger.info(f"Invalidated {removed} old cached entities")
        
        return removed
    
    def get_current_state(self) -> ScreenState:
        """Get current screen state."""
        with self._lock:
            return self._current_state
    
    def update_state(self, updates: Dict[str, Any]) -> None:
        """
        Update screen state from analysis result.
        
        Args:
            updates: Dictionary of state fields to update
        """
        with self._lock:
            state = self._current_state
            
            if 'game_name' in updates:
                state.game_name = updates['game_name']
            if 'location' in updates:
                state.location = updates['location']
            if 'in_combat' in updates:
                state.in_combat = updates['in_combat']
            if 'in_menu' in updates:
                state.in_menu = updates['in_menu']
            if 'in_dialogue' in updates:
                state.in_dialogue = updates['in_dialogue']
            if 'loading' in updates:
                state.loading = updates['loading']
            if 'player_health_low' in updates:
                state.player_health_low = updates['player_health_low']
            if 'last_significant_event' in updates:
                state.last_significant_event = updates['last_significant_event']
            
            state.last_update = time.time()
    
    def clear_state(self) -> None:
        """Clear current screen state (e.g., when game changes)."""
        with self._lock:
            self._current_state.clear()
            logger.info("Screen state cleared")
    
    def reset_game_cache(self) -> None:
        """
        Reset entire game cache (when user switches games).
        
        This clears all entities and state.
        """
        with self._lock:
            self._entities.clear()
            self._current_state.clear()
            
            # Clear database
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM entities")
                cursor.execute("DELETE FROM game_state")
                conn.commit()
                conn.close()
                
                logger.info("Game cache fully reset")
                
            except Exception as e:
                logger.error(f"Failed to reset game cache database: {e}")
    
    def _persist_entity(self, entity: CachedEntity) -> None:
        """Persist entity to SQLite database."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            import json
            metadata_json = json.dumps(entity.metadata)
            
            cursor.execute("""
                INSERT OR REPLACE INTO entities 
                (entity_type, name, confidence, source, first_seen, last_seen, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                entity.entity_type,
                entity.name,
                entity.confidence,
                entity.source,
                entity.first_seen,
                entity.last_seen,
                metadata_json
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to persist entity to database: {e}")
    
    def _remove_entity_from_db(self, entity_type: str, name: str) -> None:
        """Remove entity from SQLite database."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "DELETE FROM entities WHERE entity_type=? AND name=?",
                (entity_type, name)
            )
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to remove entity from database: {e}")
    
    def load_entities_from_db(self) -> int:
        """
        Load entities from SQLite database into memory.
        
        Returns:
            Number of entities loaded
        """
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT entity_type, name, confidence, source, "
                "first_seen, last_seen, metadata FROM entities"
            )
            
            import json
            loaded = 0
            
            for row in cursor.fetchall():
                entity = CachedEntity(
                    entity_type=row[0],
                    name=row[1],
                    confidence=row[2],
                    source=row[3],
                    first_seen=row[4],
                    last_seen=row[5],
                    metadata=json.loads(row[6]) if row[6] else {}
                )
                
                key = f"{entity.entity_type}:{entity.name}"
                self._entities[key] = entity
                loaded += 1
            
            conn.close()
            
            if loaded > 0:
                logger.info(f"Loaded {loaded} entities from database")
            
            return loaded
            
        except Exception as e:
            logger.error(f"Failed to load entities from database: {e}")
            return 0
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            
            # Count entities by type
            by_type: Dict[str, int] = {}
            for entity in self._entities.values():
                by_type[entity.entity_type] = by_type.get(entity.entity_type, 0) + 1
            
            # Calculate average confidence
            avg_confidence = 0.0
            if self._entities:
                avg_confidence = sum(
                    e.confidence for e in self._entities.values()
                ) / len(self._entities)
            
            return {
                'total_entities': len(self._entities),
                'entities_by_type': by_type,
                'average_confidence': avg_confidence,
                'cache_ttl': self.cache_ttl,
                'min_confidence': self.min_confidence,
                'current_state': self._current_state.to_dict()
            }
