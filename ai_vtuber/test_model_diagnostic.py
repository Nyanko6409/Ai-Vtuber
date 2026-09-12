#!/usr/bin/env python3
"""
Live2D Model Diagnostic Script
Validates model files and checks for common issues.
"""

import json
import sys
from pathlib import Path

MODEL_PATH = "/mnt/e/SteamLibrary/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/ganyu/ganyu.model3.json"

def check_file(path: Path, required: bool = True) -> bool:
    """Check if a file exists and print status."""
    exists = path.exists()
    status = "✓" if exists else "✗"
    req_str = "REQUIRED" if required else "optional"
    print(f"  {status} {path.name} ({req_str})")
    if not exists and required:
        return False
    return True

def main():
    print("=" * 60)
    print("Live2D Model Diagnostic")
    print("=" * 60)
    print()
    
    model_path = Path(MODEL_PATH)
    print(f"Model path: {model_path}")
    print(f"Exists: {model_path.exists()}")
    print()
    
    if not model_path.exists():
        print("✗ Model file does not exist!")
        print(f"  Please check the path in config.yaml")
        return 1
    
    # Read model JSON
    try:
        with open(model_path, 'r', encoding='utf-8') as f:
            model_data = json.load(f)
        print("✓ Model JSON loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load model JSON: {e}")
        return 1
    
    model_dir = model_path.parent
    print(f"\nModel directory: {model_dir}")
    print(f"Directory exists: {model_dir.exists()}")
    print()
    
    # Check FileReferences
    if 'FileReferences' not in model_data:
        print("✗ Model JSON missing 'FileReferences' section")
        return 1
    
    refs = model_data['FileReferences']
    all_ok = True
    
    print("Required Files:")
    print("-" * 60)
    
    # Check moc3 file
    if 'Moc' in refs:
        moc_path = model_dir / refs['Moc']
        if not check_file(moc_path, required=True):
            all_ok = False
        else:
            # Check file size
            size = moc_path.stat().st_size
            print(f"    Size: {size / 1024 / 1024:.2f} MB")
    else:
        print("  ✗ No Moc file specified in model JSON")
        all_ok = False
    
    # Check textures
    if 'Textures' in refs:
        print(f"\nTextures ({len(refs['Textures'])} files):")
        for tex in refs['Textures']:
            tex_path = model_dir / tex
            if not check_file(tex_path, required=True):
                all_ok = False
            else:
                size = tex_path.stat().st_size
                print(f"    Size: {size / 1024:.2f} KB")
    else:
        print("\n✗ No textures specified in model JSON")
        all_ok = False
    
    print("\nOptional Files:")
    print("-" * 60)
    
    # Check physics
    if 'Physics' in refs:
        phys_path = model_dir / refs['Physics']
        check_file(phys_path, required=False)
    else:
        print("  - No physics file specified")
    
    # Check pose
    if 'Pose' in refs:
        pose_path = model_dir / refs['Pose']
        check_file(pose_path, required=False)
    else:
        print("  - No pose file specified")
    
    # Check display info
    if 'DisplayInfo' in refs:
        display_path = model_dir / refs['DisplayInfo']
        check_file(display_path, required=False)
    else:
        print("  - No display info file specified")
    
    # Check motions
    if 'motions' in model_data:
        print(f"\nMotions:")
        motion_count = 0
        missing_count = 0
        for group_name, group_data in model_data['motions'].items():
            if isinstance(group_data, list):
                for motion in group_data:
                    if 'File' in motion:
                        motion_path = model_dir / motion['File']
                        if motion_path.exists():
                            motion_count += 1
                        else:
                            missing_count += 1
                            print(f"  ✗ Missing: {motion['File']}")
        print(f"  ✓ Found {motion_count} motion files")
        if missing_count > 0:
            print(f"  ✗ Missing {missing_count} motion files")
    else:
        print("\n  - No motions specified")
    
    # Check expressions
    if 'expressions' in model_data:
        print(f"\nExpressions:")
        exp_count = 0
        missing_count = 0
        for exp in model_data['expressions']:
            if 'File' in exp:
                exp_path = model_dir / exp['File']
                if exp_path.exists():
                    exp_count += 1
                else:
                    missing_count += 1
                    print(f"  ✗ Missing: {exp['File']}")
        print(f"  ✓ Found {exp_count} expression files")
        if missing_count > 0:
            print(f"  ✗ Missing {missing_count} expression files")
    else:
        print("\n  - No expressions specified")
    
    print("\n" + "=" * 60)
    if all_ok:
        print("✓ All required files present")
        print("\nThe model should load correctly.")
        print("If you still get SIGSEGV, the issue might be:")
        print("  - Corrupted .moc3 file")
        print("  - Incompatible model format")
        print("  - OpenGL context issue")
        print("  - Python/native ABI mismatch")
    else:
        print("✗ Missing required files!")
        print("\nPlease ensure all required files are present.")
    print("=" * 60)
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
