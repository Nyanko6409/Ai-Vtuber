"""AI VTuber - Live2D native runtime helpers.

Live2D / native runtime initialization support for
:class:`ai_vtuber.avatar.live2d.Live2DAvatar`:

* locating the ``live2d`` (live2d-py) package WITHOUT importing it,
* Python/native ABI compatibility checks (prevents SIGSEGV from loading a
  .so built for a different CPython version),
* model path resolution / repair (mojibake recovery, project-root relative
  paths, filesystem case-insensitive matching),
* avatar-config model selection (``active_model`` registry vs legacy
  ``model_path``),
* pure validation of the ``.model3.json`` file references on disk.

This module performs NO live2d imports at module level and never touches
the rendering or expression layers — keep it that way so importing it is
always safe (no GPU / no native extension required).
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _find_live2d_package_path() -> Optional[Path]:
    """Find the live2d package location WITHOUT importing it.
    
    This is critical to prevent SIGSEGV from loading incompatible native extensions.
    """
    import importlib.util
    
    try:
        spec = importlib.util.find_spec("live2d")
        if spec and spec.origin:
            return Path(spec.origin).parent
    except (ImportError, AttributeError, ValueError):
        pass
    
    # Fallback: search sys.path
    for path in sys.path:
        live2d_path = Path(path) / "live2d"
        if live2d_path.is_dir() and (live2d_path / "__init__.py").exists():
            return live2d_path
    
    return None


def _check_native_compatibility(package_path: Path) -> tuple[bool, str]:
    """Check if the native .so files are compatible with current Python version.
    
    Returns (is_compatible, error_message).
    """
    current_python = f"cp{sys.version_info.major}{sys.version_info.minor}"
    
    # Find all .so files
    so_files = list(package_path.glob("*.so")) + list(package_path.glob("**/*.so"))
    
    if not so_files:
        return True, ""  # No native files, assume compatible
    
    # Check each .so file
    for so_file in so_files:
        try:
            # Read first 50KB to check for Python version markers
            with open(so_file, 'rb') as f:
                content = f.read(50000)
            
            # Look for Python version markers in the binary
            for py_ver in ['cp38', 'cp39', 'cp310', 'cp311', 'cp312', 'cp313']:
                if py_ver.encode() in content:
                    if py_ver != current_python:
                        error_msg = (
                            f"Python version mismatch detected!\n"
                            f"  Current Python: {current_python} (Python {sys.version_info.major}.{sys.version_info.minor})\n"
                            f"  live2d-py native extension built for: {py_ver}\n"
                            f"  This will cause SIGSEGV (segmentation fault).\n"
                            f"\n"
                            f"SOLUTION - Choose one:\n"
                            f"  Option A: Install Python {sys.version_info.major}.{sys.version_info.minor} compatible live2d-py\n"
                            f"    pip uninstall live2d-py\n"
                            f"    pip install live2d-py  # Try to get correct version\n"
                            f"\n"
                            f"  Option B: Use Python that matches live2d-py\n"
                            f"    If live2d-py is for Python 3.12, use Python 3.12:\n"
                            f"    sudo apt install python3.12 python3.12-venv\n"
                            f"    python3.12 -m venv venv312\n"
                            f"    source venv312/bin/activate\n"
                            f"    pip install -r requirements.txt\n"
                        )
                        return False, error_msg
                    else:
                        # Found matching version
                        return True, ""
            
            # No version marker found - can't determine
            logger.debug(f"Could not determine Python version for {so_file.name}")
            
        except Exception as e:
            logger.debug(f"Could not check {so_file}: {e}")
    
    return True, ""  # Assume compatible if we can't determine


def _fix_mojibake(text: str) -> str:
    """Repair text that was decoded as cp1252/latin-1 but is really UTF-8.

    On Windows, ``open()`` without an explicit encoding uses the system code
    page (cp1252 / cp936 / ...).  A config.yaml saved as UTF-8 containing
    non-ASCII paths (e.g. 魔女) then loads as garbled text like 'é­\"å¥³'.
    Re-encoding through the original code page recovers the real string.
    Returns the input unchanged if it is not double-decoded UTF-8.
    """
    if not text or text.isascii():
        return text
    for enc in ("cp1252", "latin-1"):
        try:
            fixed = text.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        # Only accept when the repair actually changed something and the
        # result contains no replacement chars / control junk.
        if fixed != text and "\ufffd" not in fixed:
            return fixed
    return text


def _repair_path_on_fs(p: Path) -> Optional[Path]:
    """Last-resort recovery: walk the path components and match each one
    case-insensitively against its parent directory listing.

    This fixes paths whose characters got mangled by a wrong text decoding
    (or wrong case on Windows): a directory literally named 'é­\"å¥³'
    does not exist but '魔女' does — scanning the parent finds it.
    Returns a Path that exists on disk, or None.
    """
    try:
        resolved = Path(os.path.abspath(str(p)))
    except (OSError, ValueError):
        return None

    # Collect the chain of components down to the deepest existing ancestor.
    missing: list[str] = []
    cur = resolved
    while not cur.exists():
        parent = cur.parent
        if parent == cur:  # reached filesystem root
            return None
        missing.insert(0, cur.name)
        cur = parent

    for name in missing:
        try:
            entries = list(cur.iterdir())
        except OSError:
            return None
        match = next((e for e in entries if e.name == name), None)
        if match is None:
            match = next(
                (e for e in entries if e.name.casefold() == name.casefold()),
                None,
            )
        if match is None:
            fixed = _fix_mojibake(name)
            if fixed != name:
                match = next((e for e in entries if e.name == fixed), None)
                if match is None:
                    match = next(
                        (e for e in entries
                         if e.name.casefold() == fixed.casefold()),
                        None,
                    )
        if match is None:
            return None
        cur = match
    return cur if cur.exists() else None


def _resolve_model_path(raw_path: str) -> Optional[Path]:
    """Resolve and validate a Live2D model path.
    
    Supports:
    - Absolute paths (Windows, Linux, WSL)
    - Relative paths (resolved from project root)
    - Paths with spaces
    - Environment variable expansion
    
    Args:
        raw_path: Raw path string from configuration
        
    Returns:
        Resolved Path object if valid, None otherwise
    """
    if not raw_path or not raw_path.strip():
        return None

    # Repair double-decoded UTF-8 before touching the filesystem.
    raw_path = _fix_mojibake(raw_path)

    p = Path(raw_path).expanduser()

    # Some code pages (e.g. cp936/GBK on Chinese Windows) mangle the whole
    # string differently than per-component; try a component-wise repair too.
    if not p.exists():
        parts = p.parts
        candidate = Path(*[_fix_mojibake(part) for part in parts])
        if candidate != p and candidate.exists():
            logger.info(
                f"Live2D model path repaired component-wise:\n"
                f"  {p}\n  -> {candidate}"
            )
            p = candidate
    
    # If path is relative, resolve it relative to the project root
    # Project root is 2 levels up from ai_vtuber/avatar/live2d.py
    if not p.is_absolute():
        try:
            project_root = Path(__file__).resolve().parents[2]
            p = project_root / p
        except Exception as e:
            logger.warning(f"Could not determine project root for relative path: {e}")
    
    p = p.resolve()

    if not p.exists():
        recovered = _repair_path_on_fs(p)
        if recovered is not None:
            logger.warning(
                f"Live2D model path did not match exactly; recovered via "
                f"directory scan:\n  {p}\n  -> {recovered}"
            )
            p = recovered

    if not p.exists():
        logger.error("Live2D model not found:")
        logger.error(f"{p}")
        logger.error(
            "Please update config.yaml 'avatar.model_path' (or 'avatar.models') to point to your Live2D model file.\n"
            "You can use:\n"
            "  - Absolute path: C:/Users/Name/Models/model.model3.json\n"
            "  - Relative path: assets/avatars/my_model/model.model3.json (from project root)\n"
            "  - WSL path: /mnt/e/SteamLibrary/.../model.model3.json"
        )
        return None

    if not p.is_file():
        logger.error(f"Live2D model path is not a file: {p}")
        return None

    if p.suffix.lower() != ".json":
        logger.error(f"Live2D model must be a .json file, got: {p.suffix}")
        return None

    return p


def _resolve_active_model(config: dict) -> tuple[str, Optional[str]]:
    """Resolve which model path to use from the avatar config block.

    Priority:
      1. avatar.active_model  -> name lookup in avatar.models registry
      2. first entry of avatar.models (if active_model empty/unknown)
      3. avatar.model_path    -> legacy single-path option

    Returns (path_string, selected_name). Path may be "" if nothing configured.
    """
    models = config.get("models") or {}
    active = str(config.get("active_model", "") or "").strip()

    if isinstance(models, dict) and models:
        names = list(models.keys())
        if active and active in models:
            chosen = active
        else:
            if active:
                logger.warning(
                    f"avatar.active_model '{active}' not found in avatar.models "
                    f"(available: {', '.join(names)}). Falling back to first entry."
                )
            chosen = names[0]
        entry = models[chosen] or {}
        path = entry.get("path", "") if isinstance(entry, dict) else str(entry)
        desc = entry.get("description", "") if isinstance(entry, dict) else ""
        logger.info(f"Live2D model selected by name: '{chosen}'"
                    + (f" ({desc})" if desc else "")
                    + f" -> {path}")
        return str(path), chosen

    # Legacy: single model_path
    return str(config.get("model_path", "") or ""), None


def validate_model_files(model_path: Optional[Path],
                         set_error: callable) -> bool:
    """Validate that all required model files exist.

    Args:
        model_path: Resolved ``.model3.json`` path.
        set_error: Callback invoked with the error message when validation
            fails (the avatar stores it in its ``_error_message`` state).

    Returns:
        True when every required file is present.
    """
    import json

    if not model_path or not model_path.exists():
        error_msg = f"Model file does not exist: {model_path}"
        set_error(error_msg)
        logger.error(error_msg)
        return False

    model_dir = model_path.parent
    logger.info(f"Validating model files in: {model_dir}")

    try:
        with open(model_path, 'r', encoding='utf-8') as f:
            model_data = json.load(f)
    except Exception as e:
        error_msg = f"Failed to read model JSON: {e}"
        set_error(error_msg)
        logger.error(error_msg)
        return False

    # Check FileReferences
    if 'FileReferences' not in model_data:
        error_msg = "Model JSON missing 'FileReferences' section"
        set_error(error_msg)
        logger.error(error_msg)
        return False

    refs = model_data['FileReferences']
    missing_files = []

    # Check moc3 file (required)
    if 'Moc' in refs:
        moc_path = model_dir / refs['Moc']
        if not moc_path.exists():
            missing_files.append(f"Moc: {moc_path}")
        else:
            logger.debug(f"✓ Moc file exists: {moc_path.name}")

    # Check textures (required)
    if 'Textures' in refs:
        for tex in refs['Textures']:
            tex_path = model_dir / tex
            if not tex_path.exists():
                missing_files.append(f"Texture: {tex_path}")
            else:
                logger.debug(f"✓ Texture exists: {tex_path.name}")

    # Check physics (optional but recommended)
    if 'Physics' in refs:
        phys_path = model_dir / refs['Physics']
        if not phys_path.exists():
            logger.warning(f"Physics file missing (optional): {phys_path}")
        else:
            logger.debug(f"✓ Physics file exists: {phys_path.name}")

    # Check pose (optional)
    if 'Pose' in refs:
        pose_path = model_dir / refs['Pose']
        if not pose_path.exists():
            logger.warning(f"Pose file missing (optional): {pose_path}")
        else:
            logger.debug(f"✓ Pose file exists: {pose_path.name}")

    # Check motions (optional)
    if 'motions' in model_data:
        motion_count = 0
        for group_name, group_data in model_data['motions'].items():
            if isinstance(group_data, list):
                for motion in group_data:
                    if 'File' in motion:
                        motion_path = model_dir / motion['File']
                        if motion_path.exists():
                            motion_count += 1
                        else:
                            logger.warning(f"Motion file missing: {motion_path}")
        logger.debug(f"✓ Found {motion_count} motion files")

    # Check expressions (optional)
    if 'expressions' in model_data:
        exp_count = 0
        for exp in model_data['expressions']:
            if 'File' in exp:
                exp_path = model_dir / exp['File']
                if exp_path.exists():
                    exp_count += 1
                else:
                    logger.warning(f"Expression file missing: {exp_path}")
        logger.debug(f"✓ Found {exp_count} expression files")

    # Report missing required files
    if missing_files:
        error_msg = "Missing required model files:\n" + "\n".join(f"  - {f}" for f in missing_files)
        set_error(error_msg)
        logger.error(error_msg)
        return False

    logger.info("✓ All required model files validated")
    return True
