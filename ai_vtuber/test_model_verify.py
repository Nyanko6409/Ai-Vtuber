#!/usr/bin/env python3
"""
Model File Verification Script
Checks that all files referenced in the Live2D model exist.
"""

import sys
import json
from pathlib import Path

MODEL_PATH = "/mnt/e/SteamLibrary/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/ganyu/ganyu.model3.json"

print("=" * 60)
print("LIVE2D MODEL FILE VERIFICATION")
print("=" * 60)

model_path = Path(MODEL_PATH)
print(f"\nModel path: {model_path}")
print(f"Exists: {model_path.exists()}")
print(f"Is file: {model_path.is_file()}")

if not model_path.exists():
    print(f"\n✗ Model file does not exist!")
    print(f"  Please check the path in config.yaml")
    sys.exit(1)

print(f"\n[Reading model3.json]")
try:
    with open(model_path, 'r', encoding='utf-8') as f:
        model_data = json.load(f)
    print(f"✓ Model JSON loaded successfully")
except Exception as e:
    print(f"✗ Failed to load model JSON: {e}")
    sys.exit(1)

model_dir = model_path.parent
print(f"Model directory: {model_dir}")

print(f"\n[Checking referenced files]")

# Check FileReferences
if 'FileReferences' in model_data:
    refs = model_data['FileReferences']
    
    # Check moc3 file
    if 'Moc' in refs:
        moc_path = model_dir / refs['Moc']
        print(f"\nMoc3 file: {moc_path}")
        print(f"  Exists: {moc_path.exists()}")
        if not moc_path.exists():
            print(f"  ✗ MISSING!")
    
    # Check textures
    if 'Textures' in refs:
        print(f"\nTextures ({len(refs['Textures'])} files):")
        for tex in refs['Textures']:
            tex_path = model_dir / tex
            exists = tex_path.exists()
            status = "✓" if exists else "✗ MISSING"
            print(f"  {status} {tex}")
    
    # Check physics
    if 'Physics' in refs:
        phys_path = model_dir / refs['Physics']
        print(f"\nPhysics file: {phys_path}")
        print(f"  Exists: {phys_path.exists()}")
        if not phys_path.exists():
            print(f"  ✗ MISSING!")
    
    # Check pose
    if 'Pose' in refs:
        pose_path = model_dir / refs['Pose']
        print(f"\nPose file: {pose_path}")
        print(f"  Exists: {pose_path.exists()}")
        if not pose_path.exists():
            print(f"  ✗ MISSING!")
    
    # Check display info
    if 'DisplayInfo' in refs:
        display_path = model_dir / refs['DisplayInfo']
        print(f"\nDisplayInfo file: {display_path}")
        print(f"  Exists: {display_path.exists()}")
        if not display_path.exists():
            print(f"  ✗ MISSING!")

# Check motions
if ' motions' in model_data:
    motions = model_data['motions']
    print(f"\n[Motions]")
    for group_name, group_data in motions.items():
        if isinstance(group_data, list):
            print(f"\n  Group: {group_name} ({len(group_data)} files)")
            for motion in group_data:
                if 'File' in motion:
                    motion_path = model_dir / motion['File']
                    exists = motion_path.exists()
                    status = "✓" if exists else "✗ MISSING"
                    print(f"    {status} {motion['File']}")

# Check expressions
if 'expressions' in model_data:
    expressions = model_data['expressions']
    print(f"\n[Expressions] ({len(expressions)} files)")
    for exp in expressions:
        if 'File' in exp:
            exp_path = model_dir / exp['File']
            exists = exp_path.exists()
            status = "✓" if exists else "✗ MISSING"
            print(f"  {status} {exp['File']}")

print("\n" + "=" * 60)
print("MODEL VERIFICATION COMPLETE")
print("=" * 60)
