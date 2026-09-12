#!/usr/bin/env python3
"""
Live2D Diagnostic Script
Inspects the installed live2d-py package to understand what we're working with.
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("LIVE2D PACKAGE DIAGNOSTICS")
print("=" * 60)

print(f"\n[Python Environment]")
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python implementation: {sys.implementation.name}")
print(f"Platform: {sys.platform}")

print(f"\n[Searching for live2d packages]")

# Try to find live2d package
try:
    import live2d
    print(f"✓ live2d module found")
    print(f"  Location: {live2d.__file__}")
    print(f"  Version: {getattr(live2d, '__version__', 'unknown')}")
except ImportError as e:
    print(f"✗ live2d not found: {e}")
    sys.exit(1)

# Check for v2 and v3 modules
print(f"\n[Live2D Version Modules]")
try:
    import live2d.v2
    print(f"✓ live2d.v2 available")
    print(f"  Location: {live2d.v2.__file__}")
except ImportError as e:
    print(f"✗ live2d.v2 not available: {e}")

try:
    import live2d.v3
    print(f"✓ live2d.v3 available")
    print(f"  Location: {live2d.v3.__file__}")
except ImportError as e:
    print(f"✗ live2d.v3 not available: {e}")

# Check for native libraries
print(f"\n[Native Libraries]")
live2d_path = Path(live2d.__file__).parent
print(f"Package directory: {live2d_path}")

# List all files in the package
print(f"\nFiles in package directory:")
for item in sorted(live2d_path.iterdir()):
    if item.is_file():
        size = item.stat().st_size
        print(f"  {item.name} ({size} bytes)")
    elif item.is_dir():
        print(f"  {item.name}/ (directory)")

# Check for .so files (Linux shared libraries)
so_files = list(live2d_path.glob("*.so")) + list(live2d_path.glob("**/*.so"))
if so_files:
    print(f"\n[Native .so files found]")
    for so in so_files:
        print(f"  {so}")
        # Try to get more info about the .so
        try:
            import subprocess
            result = subprocess.run(['file', str(so)], capture_output=True, text=True)
            print(f"    {result.stdout.strip()}")
        except:
            pass
else:
    print(f"\n[No .so files found]")

# Check for .pyd files (Windows)
pyd_files = list(live2d_path.glob("*.pyd"))
if pyd_files:
    print(f"\n[Native .pyd files found (Windows)]")
    for pyd in pyd_files:
        print(f"  {pyd}")

# Try to inspect the module structure
print(f"\n[Module Attributes]")
attrs = [a for a in dir(live2d) if not a.startswith('_')]
print(f"Public attributes: {attrs[:20]}")  # First 20

# Check if there's version info in the module
if hasattr(live2d, 'LIVE2D_VERSION'):
    print(f"Live2D version: {live2d.LIVE2D_VERSION}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
