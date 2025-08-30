#!/usr/bin/env python3
"""
Example usage of rffl-boxscores CLI tool.

This script demonstrates how to use the tool programmatically
and shows common usage patterns.
"""

import subprocess
import os
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and print the result."""
    print(f"\n🔧 {description}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("✅ Command completed successfully")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
        else:
            print(f"❌ Command failed: {result.stderr.strip()}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
        return False
    except FileNotFoundError:
        print("❌ Command not found")
        return False

def main():
    """Demonstrate various usage patterns."""
    print("🚀 RFFL Boxscores - Example Usage\n")
    
    # Example 1: Show help
    print("=" * 60)
    print("EXAMPLE 1: Show CLI help")
    print("=" * 60)
    run_command(["rffl-bs", "--help"], "Show main CLI help")
    
    # Example 2: Show export help
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Show export command help")
    print("=" * 60)
    run_command(["rffl-bs", "export", "--help"], "Show export command help")
    
    # Example 3: Show validate help
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Show validate command help")
    print("=" * 60)
    run_command(["rffl-bs", "validate", "--help"], "Show validate command help")
    
    # Example 4: Try to export (will fail without valid league, but shows usage)
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Attempt export (will fail but shows usage)")
    print("=" * 60)
    print("Note: This will fail because we're not providing a real league ID,")
    print("but it demonstrates the command structure.")
    run_command(["rffl-bs", "export", "--league", "123456", "--year", "2024"], 
                "Attempt export with dummy league ID")
    
    # Example 5: Show environment variable usage
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Environment variable usage")
    print("=" * 60)
    print("For private leagues, you can set environment variables:")
    print("export ESPN_S2=\"your_espn_s2_cookie_value\"")
    print("export SWID=\"{your_swid_cookie_value}\"")
    print("rffl-bs export --league 123456 --year 2024")
    
    # Example 6: Show validation usage
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Validation usage")
    print("=" * 60)
    print("After exporting, validate the data:")
    print("rffl-bs validate validated_boxscores_2024.csv")
    print("rffl-bs validate validated_boxscores_2024.csv --tolerance 0.02")
    
    # Example 7: Complete workflow
    print("\n" + "=" * 60)
    print("EXAMPLE 7: Complete workflow")
    print("=" * 60)
    print("Complete workflow for a season:")
    print("1. rffl-bs export --league <league_id> --year 2024")
    print("2. rffl-bs validate validated_boxscores_2024.csv")
    print("3. Check for validation report if issues found")
    
    print("\n" + "=" * 60)
    print("🎯 Ready to use!")
    print("=" * 60)
    print("The tool is now ready for use. Key points:")
    print("• Use --league and --year for export")
    print("• Set ESPN_S2 and SWID env vars for private leagues")
    print("• Validate exported data with the validate command")
    print("• Check the README.md for detailed documentation")

if __name__ == "__main__":
    main()
