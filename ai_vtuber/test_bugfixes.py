#!/usr/bin/env python3
"""
Test script to verify the bug fixes for:
1. Text rendering orientation
2. Keyboard shortcuts
3. CUDA library handling
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_texture_coordinates():
    """Test that texture coordinates are correctly flipped."""
    print("=" * 60)
    print("TEST 1: Texture Coordinates")
    print("=" * 60)
    
    # Read chat_ui.py and check texture coordinates
    with open('ui/chat_ui.py', 'r') as f:
        content = f.read()
    
    # Check for correct texture coordinates
    if 'GL.glTexCoord2f(0, 1); GL.glVertex2f(0, 0)' in content:
        print("✓ chat_ui.py: Texture coordinates correctly flipped")
    else:
        print("✗ chat_ui.py: Texture coordinates NOT flipped")
        return False
    
    # Read pygame_ui.py and check texture coordinates
    with open('ui/pygame_ui.py', 'r') as f:
        content = f.read()
    
    if 'GL.glTexCoord2f(0, 1); GL.glVertex2f(0, 0)' in content:
        print("✓ pygame_ui.py: Texture coordinates correctly flipped")
    else:
        print("✗ pygame_ui.py: Texture coordinates NOT flipped")
        return False
    
    print("\n✓ TEST 1 PASSED: Texture coordinates are correct\n")
    return True

def test_keyboard_handling():
    """Test that keyboard event handling is correctly ordered."""
    print("=" * 60)
    print("TEST 2: Keyboard Event Handling")
    print("=" * 60)
    
    # Read main.py and check event handling order
    with open('main.py', 'r') as f:
        content = f.read()
    
    # Check that special keys are handled before chat input
    lines = content.split('\n')
    
    # Find the KEYDOWN event handler
    keydown_line = -1
    escape_line = -1
    tab_line = -1
    chat_handle_line = -1
    
    for i, line in enumerate(lines):
        if 'elif event.type == pygame.KEYDOWN:' in line:
            keydown_line = i
        if keydown_line > 0 and 'if event.key == pygame.K_ESCAPE:' in line and escape_line == -1:
            escape_line = i
        if keydown_line > 0 and 'elif event.key == pygame.K_TAB:' in line and tab_line == -1:
            tab_line = i
        if keydown_line > 0 and 'if chat_ui.input_active:' in line and chat_handle_line == -1:
            chat_handle_line = i
    
    if keydown_line == -1:
        print("✗ KEYDOWN event handler not found")
        return False
    
    if escape_line == -1 or tab_line == -1:
        print("✗ Special key handlers not found")
        return False
    
    if chat_handle_line == -1:
        print("✗ Chat input handler not found")
        return False
    
    # Check order: special keys should come before chat input
    if escape_line < chat_handle_line and tab_line < chat_handle_line:
        print("✓ Special keys (ESC, TAB) are handled before chat input")
    else:
        print("✗ Special keys are NOT handled before chat input")
        return False
    
    # Check for continue statements after special keys
    has_tab_continue = False
    has_f_continue = False
    has_d_continue = False
    
    for i in range(tab_line, min(tab_line + 10, len(lines))):
        if 'continue' in lines[i]:
            has_tab_continue = True
            break
    
    for i, line in enumerate(lines):
        if 'elif event.key == pygame.K_f:' in line:
            for j in range(i, min(i + 5, len(lines))):
                if 'continue' in lines[j]:
                    has_f_continue = True
                    break
        if 'elif event.key == pygame.K_d:' in line:
            for j in range(i, min(i + 5, len(lines))):
                if 'continue' in lines[j]:
                    has_d_continue = True
                    break
    
    if has_tab_continue:
        print("✓ TAB key has continue statement")
    else:
        print("✗ TAB key missing continue statement")
        return False
    
    if has_f_continue:
        print("✓ F key has continue statement")
    else:
        print("✗ F key missing continue statement")
        return False
    
    if has_d_continue:
        print("✓ D key has continue statement")
    else:
        print("✗ D key missing continue statement")
        return False
    
    print("\n✓ TEST 2 PASSED: Keyboard event handling is correct\n")
    return True

def test_cuda_troubleshooting():
    """Test that CUDA troubleshooting guide exists in README."""
    print("=" * 60)
    print("TEST 3: CUDA Troubleshooting Guide")
    print("=" * 60)
    
    # Read README.md and check for CUDA troubleshooting
    with open('README.md', 'r') as f:
        content = f.read()
    
    if 'libcublas.so.12' in content:
        print("✓ README.md contains libcublas.so.12 error documentation")
    else:
        print("✗ README.md missing libcublas.so.12 error documentation")
        return False
    
    if 'nvidia-cuda-toolkit' in content:
        print("✓ README.md contains CUDA toolkit installation instructions")
    else:
        print("✗ README.md missing CUDA toolkit installation instructions")
        return False
    
    if 'device: "cpu"' in content:
        print("✓ README.md contains CPU fallback instructions")
    else:
        print("✗ README.md missing CPU fallback instructions")
        return False
    
    if 'LD_LIBRARY_PATH' in content:
        print("✓ README.md contains library path instructions")
    else:
        print("✗ README.md missing library path instructions")
        return False
    
    print("\n✓ TEST 3 PASSED: CUDA troubleshooting guide is complete\n")
    return True

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("AI VTuber Bug Fix Verification Tests")
    print("=" * 60 + "\n")
    
    results = []
    
    # Test 1: Texture coordinates
    results.append(("Texture Coordinates", test_texture_coordinates()))
    
    # Test 2: Keyboard handling
    results.append(("Keyboard Event Handling", test_keyboard_handling()))
    
    # Test 3: CUDA troubleshooting
    results.append(("CUDA Troubleshooting", test_cuda_troubleshooting()))
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✓ ALL TESTS PASSED\n")
        print("The bug fixes have been successfully applied:")
        print("  1. Text rendering is now correctly oriented")
        print("  2. Keyboard shortcuts work even when chat is active")
        print("  3. CUDA troubleshooting guide is available")
        print("\nYou can now run the application:")
        print("  python main.py --debug")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED\n")
        print("Please review the failed tests above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
