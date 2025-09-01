#!/usr/bin/env python3
"""
Test script to verify rffl-boxscores installation and basic functionality.
"""

import sys
import subprocess
from pathlib import Path


def test_imports():
    """Test that all required packages can be imported."""
    print("Testing imports...")

    try:
        import pandas as pd

        print("✅ pandas imported successfully")
    except ImportError as e:
        print(f"❌ pandas import failed: {e}")
        return False

    try:
        import typer

        print("✅ typer imported successfully")
    except ImportError as e:
        print(f"❌ typer import failed: {e}")
        return False

    try:
        from espn_api.football import League

        print("✅ espn_api imported successfully")
    except ImportError as e:
        print(f"❌ espn_api import failed: {e}")
        return False

    try:
        from rffl_boxscores.cli import app

        print("✅ rffl_boxscores.cli imported successfully")
    except ImportError as e:
        print(f"❌ rffl_boxscores.cli import failed: {e}")
        return False

    return True


def test_cli_help():
    """Test that the CLI command is available and shows help."""
    print("\nTesting CLI help...")

    try:
        result = subprocess.run(
            ["rffl-bs", "--help"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ CLI help command works")
            return True
        else:
            print(f"❌ CLI help failed: {result.stderr}")
            return False
    except FileNotFoundError:
        print(
            "❌ CLI command 'rffl-bs' not found. Make sure to install with 'pip install -e .'"
        )
        return False
    except subprocess.TimeoutExpired:
        print("❌ CLI help command timed out")
        return False


def test_export_help():
    """Test that the export command shows help."""
    print("\nTesting export command help...")

    try:
        result = subprocess.run(
            ["rffl-bs", "export", "--help"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ Export command help works")
            return True
        else:
            print(f"❌ Export help failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Export help command timed out")
        return False


def test_validate_help():
    """Test that the validate command shows help."""
    print("\nTesting validate command help...")

    try:
        result = subprocess.run(
            ["rffl-bs", "validate", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print("✅ Validate command help works")
            return True
        else:
            print(f"❌ Validate help failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Validate help command timed out")
        return False


def main():
    """Run all tests."""
    print("🧪 Testing rffl-boxscores installation...\n")

    tests = [
        test_imports,
        test_cli_help,
        test_export_help,
        test_validate_help,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print(f"\n📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Installation is working correctly.")
        print("\nYou can now use the tool:")
        print("  rffl-bs export --league <league_id> --year <year>")
        print("  rffl-bs validate <csv_file>")
        return 0
    else:
        print("❌ Some tests failed. Please check the installation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
