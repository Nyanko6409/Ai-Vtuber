#!/usr/bin/env python3
"""
Standalone Live2D Test
Isolates each step of Live2D initialization to find where SIGSEGV occurs.

This test performs each operation separately and reports success/failure.
"""

import sys
import os
import time
from pathlib import Path

MODEL_PATH = "/mnt/e/SteamLibrary/steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/ganyu/ganyu.model3.json"

print("=" * 60)
print("STANDALONE LIVE2D TEST")
print("=" * 60)
print(f"Model: {MODEL_PATH}")
print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")

# Test results tracking
results = {}

def report_test(test_num, test_name, success, error_msg=None):
    """Report test result."""
    status = "OK" if success else "FAILED"
    results[test_num] = success
    print(f"[{test_num}] {test_name}: {status}")
    if error_msg and not success:
        print(f"    Error: {error_msg}")
    return success

# ============================================================================
# TEST A: Create Pygame window/context
# ============================================================================
print(f"\n[TEST A] Creating Pygame window/context")
try:
    import pygame
    pygame.init()
    screen = pygame.display.set_mode(
        (800, 600),
        pygame.DOUBLEBUF | pygame.OPENGL
    )
    pygame.display.set_caption("Live2D Test")
    report_test(1, "Pygame context", True)
except Exception as e:
    report_test(1, "Pygame context", False, str(e))
    print("\nCannot proceed without Pygame context.")
    sys.exit(1)

# ============================================================================
# TEST B: Initialize Live2D/Cubism
# ============================================================================
print(f"\n[TEST B] Initializing Live2D/Cubism")
try:
    # Import live2d module
    try:
        import live2d.v3 as live2d
        print(f"  Using live2d.v3")
    except ImportError:
        import live2d.v2 as live2d
        print(f"  Using live2d.v2")
    
    print(f"  Live2D module: {live2d.__file__}")
    
    # Initialize Live2D
    live2d.init()
    report_test(2, "Live2D initialization", True)
except Exception as e:
    report_test(2, "Live2D initialization", False, str(e))
    print("\nCannot proceed without Live2D initialization.")
    pygame.quit()
    sys.exit(1)

# ============================================================================
# TEST C: Load model JSON
# ============================================================================
print(f"\n[TEST C] Loading model JSON")
try:
    model_path = Path(MODEL_PATH)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    
    print(f"  Model path: {model_path}")
    print(f"  Model exists: {model_path.exists()}")
    report_test(3, "Model loading", True)
except Exception as e:
    report_test(3, "Model loading", False, str(e))
    print("\nCannot proceed without model file.")
    pygame.quit()
    sys.exit(1)

# ============================================================================
# TEST D: Initialize OpenGL for Live2D
# ============================================================================
print(f"\n[TEST D] Initializing OpenGL for Live2D")
try:
    live2d.glInit()
    report_test(4, "Renderer initialization", True)
except Exception as e:
    report_test(4, "Renderer initialization", False, str(e))
    print("\nCannot proceed without OpenGL initialization.")
    pygame.quit()
    sys.exit(1)

# ============================================================================
# TEST E: Create LAppModel and load model
# ============================================================================
print(f"\n[TEST E] Creating LAppModel and loading model")
try:
    model = live2d.LAppModel()
    print(f"  LAppModel created")
    
    # Load the model
    model.LoadModelJson(str(model_path))
    print(f"  Model loaded")
    
    report_test(5, "Model creation and loading", True)
except Exception as e:
    report_test(5, "Model creation and loading", False, str(e))
    print("\nCannot proceed without model loaded.")
    pygame.quit()
    sys.exit(1)

# ============================================================================
# TEST F: Resize model to window size
# ============================================================================
print(f"\n[TEST F] Resizing model to window size")
try:
    model.Resize(800, 600)
    print(f"  Model resized to 800x600")
    report_test(6, "Model resize", True)
except Exception as e:
    report_test(6, "Model resize", False, str(e))

# ============================================================================
# TEST G: Update model
# ============================================================================
print(f"\n[TEST G] Updating model")
try:
    model.Update()
    print(f"  Model updated")
    report_test(7, "Model update", True)
except Exception as e:
    report_test(7, "Model update", False, str(e))

# ============================================================================
# TEST H: Draw one frame
# ============================================================================
print(f"\n[TEST H] Drawing one frame")
try:
    # Clear buffer
    live2d.clearBuffer()
    print(f"  Buffer cleared")
    
    # Draw model
    model.Draw()
    print(f"  Model drawn")
    
    # Flip display
    pygame.display.flip()
    print(f"  Display flipped")
    
    report_test(8, "Model render", True)
except Exception as e:
    report_test(8, "Model render", False, str(e))

# ============================================================================
# TEST I: Keep window open for visual verification
# ============================================================================
print(f"\n[TEST I] Keeping window open for 3 seconds")
print("  (If you see the model, rendering is working)")
try:
    # Run a few frames
    for i in range(90):  # 3 seconds at 30 FPS
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                break
        
        live2d.clearBuffer()
        model.Update()
        model.Draw()
        pygame.display.flip()
        time.sleep(1.0 / 30.0)
    
    report_test(9, "Sustained rendering", True)
except Exception as e:
    report_test(9, "Sustained rendering", False, str(e))

# ============================================================================
# Cleanup
# ============================================================================
print(f"\n[Cleanup]")
try:
    live2d.dispose()
    print(f"  Live2D disposed")
    pygame.quit()
    print(f"  Pygame quit")
    report_test(10, "Cleanup", True)
except Exception as e:
    report_test(10, "Cleanup", False, str(e))

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)

test_names = {
    1: "Pygame context",
    2: "Live2D initialization",
    3: "Model loading",
    4: "Renderer initialization",
    5: "Model creation and loading",
    6: "Model resize",
    7: "Model update",
    8: "Model render",
    9: "Sustained rendering",
    10: "Cleanup"
}

all_passed = True
for test_num in sorted(results.keys()):
    status = "✓ PASS" if results[test_num] else "✗ FAIL"
    print(f"[{test_num}] {test_names.get(test_num, 'Unknown')}: {status}")
    if not results[test_num]:
        all_passed = False

print("\n" + "=" * 60)
if all_passed:
    print("ALL TESTS PASSED")
    print("Live2D is working correctly!")
else:
    print("SOME TESTS FAILED")
    print("The first failure indicates where the problem occurs.")
print("=" * 60)

sys.exit(0 if all_passed else 1)
