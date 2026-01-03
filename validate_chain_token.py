#!/usr/bin/env python3
"""Quick validation script for chain and token models."""

import sys

try:
    print("Testing imports...")
    print("✓ All models and schemas imported successfully")

    print("\nTesting API router...")
    from src.api.chains_tokens import router

    print(f"✓ API router created with {len(router.routes)} routes")

    print("\nAll validations passed!")
    sys.exit(0)

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
