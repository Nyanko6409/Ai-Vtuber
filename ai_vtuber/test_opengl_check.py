#!/usr/bin/env python3
"""
OpenGL/WSL Compatibility Check
Verifies that OpenGL is working correctly in the WSL environment.
"""

import sys

print("=" * 60)
print("OPENGL/WSL COMPATIBILITY CHECK")
print("=" * 60)

print(f"\n[Checking Pygame installation]")
try:
    import pygame
    print(f"✓ Pygame version: {pygame.version.ver}")
except ImportError as e:
    print(f"✗ Pygame not installed: {e}")
    sys.exit(1)

print(f"\n[Initializing Pygame]")
try:
    pygame.init()
    print(f"✓ Pygame initialized")
except Exception as e:
    print(f"✗ Pygame initialization failed: {e}")
    sys.exit(1)

print(f"\n[Creating OpenGL window]")
try:
    # Create a small OpenGL-capable window
    screen = pygame.display.set_mode((640, 480), pygame.DOUBLEBUF | pygame.OPENGL)
    print(f"✓ OpenGL window created (640x480)")
except Exception as e:
    print(f"✗ Failed to create OpenGL window: {e}")
    print(f"  This might indicate WSLg/OpenGL issues")
    pygame.quit()
    sys.exit(1)

print(f"\n[Checking OpenGL context]")
try:
    from OpenGL import GL
    print(f"✓ PyOpenGL imported")
    
    # Get OpenGL information
    vendor = GL.glGetString(GL.GL_VENDOR)
    renderer = GL.glGetString(GL.GL_RENDERER)
    version = GL.glGetString(GL.GL_VERSION)
    shading_version = GL.glGetString(GL.GL_SHADING_LANGUAGE_VERSION)
    
    print(f"\n[OpenGL Information]")
    print(f"  Vendor: {vendor}")
    print(f"  Renderer: {renderer}")
    print(f"  Version: {version}")
    print(f"  Shading Language Version: {shading_version}")
    
    # Check for required OpenGL features
    extensions = GL.glGetString(GL.GL_EXTENSIONS)
    if extensions:
        ext_list = extensions.split()
        print(f"\n[OpenGL Extensions] ({len(ext_list)} total)")
        
        # Check for important extensions
        required = ['GL_ARB_texture_non_power_of_two', 'GL_EXT_blend_func_separate']
        for req in required:
            if req in ext_list:
                print(f"  ✓ {req}")
            else:
                print(f"  ✗ {req} (MISSING)")
    
    # Test basic OpenGL operations
    print(f"\n[Testing OpenGL operations]")
    
    # Clear buffer
    GL.glClearColor(0.2, 0.3, 0.4, 1.0)
    GL.glClear(GL.GL_COLOR_BUFFER_BIT)
    print(f"  ✓ glClear() works")
    
    # Check for errors
    error = GL.glGetError()
    if error == GL.GL_NO_ERROR:
        print(f"  ✓ No OpenGL errors")
    else:
        print(f"  ✗ OpenGL error: {error}")
    
except ImportError as e:
    print(f"✗ PyOpenGL not installed: {e}")
    print(f"  Install with: pip install PyOpenGL")
except Exception as e:
    print(f"✗ OpenGL check failed: {e}")
    import traceback
    traceback.print_exc()

print(f"\n[Cleaning up]")
try:
    pygame.quit()
    print(f"✓ Pygame cleaned up")
except Exception as e:
    print(f"✗ Cleanup error: {e}")

print("\n" + "=" * 60)
print("OPENGL CHECK COMPLETE")
print("=" * 60)
print("\nIf all checks passed, OpenGL/WSL should work for Live2D.")
print("If there are failures, the issue is with WSLg/OpenGL setup.")
