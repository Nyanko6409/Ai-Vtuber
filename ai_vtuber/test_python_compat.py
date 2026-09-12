#!/usr/bin/env python3
"""
Python/Native Compatibility Check
Investigates whether there's a Python version mismatch causing SIGSEGV.
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("PYTHON/NATIVE COMPATIBILITY CHECK")
print("=" * 60)

print(f"\n[Current Python Environment]")
print(f"Executable: {sys.executable}")
print(f"Version: {sys.version}")
print(f"Version info: {sys.version_info}")
print(f"Implementation: {sys.implementation.name}")
print(f"Platform: {sys.platform}")
print(f"Prefix: {sys.prefix}")

# Check for multiple Python installations
print(f"\n[Checking for multiple Python installations]")
python_paths = [
    "/usr/bin/python3",
    "/usr/bin/python3.11",
    "/usr/bin/python3.12",
    "/usr/local/bin/python3",
    "/usr/local/bin/python3.11",
    "/usr/local/bin/python3.12",
]

for path in python_paths:
    if os.path.exists(path):
        print(f"  Found: {path}")
        try:
            import subprocess
            result = subprocess.run([path, "--version"], capture_output=True, text=True)
            print(f"    {result.stdout.strip()}")
        except:
            pass

# Check live2d package location
print(f"\n[Live2D Package Location]")
try:
    import live2d
    live2d_path = Path(live2d.__file__).parent
    print(f"Package path: {live2d_path}")
    print(f"Site-packages: {'site-packages' in str(live2d_path)}")
    
    # Check if it's in the current venv
    current_prefix = Path(sys.prefix)
    package_prefix = live2d_path.parent.parent  # Go up from live2d/ to site-packages/
    
    if current_prefix in live2d_path.parents:
        print(f"  ✓ Package is in current environment")
    else:
        print(f"  ✗ Package is NOT in current environment!")
        print(f"    Current env: {current_prefix}")
        print(f"    Package env: {package_prefix}")
        
except ImportError as e:
    print(f"✗ live2d not importable: {e}")
    sys.exit(1)

# Check native extension files
print(f"\n[Native Extension Files]")
so_files = list(live2d_path.glob("*.so")) + list(live2d_path.glob("**/*.so"))
pyd_files = list(live2d_path.glob("*.pyd"))

if so_files:
    print(f"Linux .so files found:")
    for so in so_files:
        print(f"  {so}")
        # Try to extract Python version from filename
        name = so.name
        if 'cp311' in name:
            print(f"    → Built for Python 3.11")
        elif 'cp312' in name:
            print(f"    → Built for Python 3.12")
        elif 'cp310' in name:
            print(f"    → Built for Python 3.10")
        else:
            print(f"    → Python version not in filename")
        
        # Try to get more info using file command
        try:
            import subprocess
            result = subprocess.run(['file', str(so)], capture_output=True, text=True)
            if 'python' in result.stdout.lower():
                print(f"    → {result.stdout.strip()}")
        except:
            pass

elif pyd_files:
    print(f"Windows .pyd files found:")
    for pyd in pyd_files:
        print(f"  {pyd}")
else:
    print(f"No native extension files found!")

# Check PYTHONPATH
print(f"\n[PYTHONPATH]")
pythonpath = os.environ.get('PYTHONPATH', '')
if pythonpath:
    print(f"PYTHONPATH is set:")
    for path in pythonpath.split(':'):
        print(f"  {path}")
else:
    print(f"PYTHONPATH is not set")

# Check sys.path
print(f"\n[sys.path]")
for path in sys.path:
    print(f"  {path}")

# Try to import and check version info
print(f"\n[Live2D Module Info]")
try:
    import live2d
    print(f"Module file: {live2d.__file__}")
    
    # Check for version attributes
    for attr in ['__version__', 'VERSION', 'version', 'LIVE2D_VERSION']:
        if hasattr(live2d, attr):
            print(f"{attr}: {getattr(live2d, attr)}")
    
    # Try to get native module info
    if hasattr(live2d, '__file__'):
        module_file = Path(live2d.__file__)
        print(f"\nModule directory contents:")
        for item in sorted(module_file.parent.iterdir()):
            if item.is_file():
                size = item.stat().st_size
                print(f"  {item.name} ({size} bytes)")
                
except Exception as e:
    print(f"Error checking module info: {e}")

# Check if we can detect the Python version the native module was built for
print(f"\n[Native Module Python Version Detection]")
try:
    import live2d
    import ctypes
    
    # Try to load the native module and check for version symbols
    module_file = Path(live2d.__file__)
    
    # Look for .so files
    so_files = list(module_file.parent.glob("*.so"))
    if so_files:
        so_file = so_files[0]
        print(f"Checking: {so_file.name}")
        
        # Try to read strings from the .so file
        try:
            with open(so_file, 'rb') as f:
                content = f.read()
                
            # Look for Python version strings
            import re
            python_versions = re.findall(rb'python3\.\d+', content)
            if python_versions:
                print(f"  Found Python version strings:")
                for ver in set(python_versions):
                    print(f"    {ver.decode()}")
            else:
                print(f"  No Python version strings found in binary")
                
        except Exception as e:
            print(f"  Could not read binary: {e}")
    
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("COMPATIBILITY CHECK COMPLETE")
print("=" * 60)

print("\n[Analysis]")
print("If the native .so file was built for Python 3.12 but you're running")
print("Python 3.11, this would cause a SIGSEGV due to ABI incompatibility.")
print("\nThe solution would be to:")
print("1. Install the correct live2d-py version for Python 3.11")
print("2. Or upgrade to Python 3.12")
print("3. Or build live2d-py from source for Python 3.11")
