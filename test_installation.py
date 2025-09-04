#!/usr/bin/env python3
"""
Test script to verify rffl-boxscores installation and basic functionality.
"""

import sys
import subprocess


def test_imports():
    """Test that all required packages can be imported."""
    print("Testing imports...")

    try:
        import pandas as pd  # noqa: F401

        print("✅ pandas imported successfully")
    except ImportError as e:
        raise AssertionError(f"pandas import failed: {e}")

    try:
        import typer  # noqa: F401

        print("✅ typer imported successfully")
    except ImportError as e:
        raise AssertionError(f"typer import failed: {e}")

    try:
        from espn_api.football import League  # noqa: F401

        print("✅ espn_api imported successfully")
    except ImportError as e:
        raise AssertionError(f"espn_api import failed: {e}")

    try:
        from rffl_boxscores.cli import app  # noqa: F401

        print("✅ rffl_boxscores.cli imported successfully")
    except ImportError as e:
        raise AssertionError(f"rffl_boxscores.cli import failed: {e}")


def test_cli_help():
    """Test that the CLI command is available and shows help."""
    print("\nTesting CLI help...")

    try:
        result = subprocess.run(
            ["rffl-bs", "--help"], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, "CLI help failed"
        print("✅ CLI help command works")
    except FileNotFoundError:
        raise AssertionError(
            "CLI 'rffl-bs' not found. Install with 'pip install -e .' "
        )
    except subprocess.TimeoutExpired:
        raise AssertionError("CLI help command timed out")


def test_export_help():
    """Test that the export command shows help."""
    print("\nTesting export command help...")

    try:
        result = subprocess.run(
            ["rffl-bs", "export", "--help"], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, "Export help failed"
        print("✅ Export command help works")
    except subprocess.TimeoutExpired:
        raise AssertionError("Export help command timed out")


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
        assert result.returncode == 0, "Validate help failed"
        print("✅ Validate command help works")
    except subprocess.TimeoutExpired:
        raise AssertionError("Validate help command timed out")


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
