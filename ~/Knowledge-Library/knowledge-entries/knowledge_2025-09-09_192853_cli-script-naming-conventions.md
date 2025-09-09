# CLI Script Naming Conventions and File Types

## Metadata
- **Created:** 2025-09-09 19:28:53 UTC
- **AI Assistant:** Claude Sonnet 4 (via Cursor)
- **Source Project:** /Users/thorsenk/KTHR-Macbook-Development/src/rffl-boxscores
- **Topic:** CLI Script Naming Conventions and File Types
- **Learning Level:** Beginner
- **Tags:** cli, python, naming-conventions, file-types, command-line, typer

## Original Context
User asked about the naming convention choice of `cli.py` in the RFFL Boxscores project, wanting to understand what to call this file and why it's named this way. This led to a comprehensive explanation of CLI scripts, naming conventions, and how to identify different types of Python files.

## Knowledge Synthesis

### What is this file?
**This is a CLI (Command Line Interface) script** - it's a Python program designed to be run from the terminal/command line, not as a web application or GUI.

### Why is it called `cli.py`?
The naming convention `cli.py` is very common in Python projects and tells you several things:

1. **CLI = Command Line Interface** - It's meant to be run from the terminal
2. **`.py`** - It's a Python file
3. **Location matters** - It's inside the `rffl_boxscores/` package directory

### What makes this a "CLI script"?
Looking at the code structure:

```python
# Line 17: Creates the CLI app using Typer framework
app = typer.Typer(add_completion=False, help="RFFL clean exporter + validator")

# Lines 587-641: Defines commands like "export", "validate", etc.
@app.command("export")
def cmd_export(...):
    """Export ESPN fantasy football boxscores to CSV format."""

# Line 3184: Entry point - runs the CLI when executed
if __name__ == "__main__":
    app()
```

### How you would run it:
```bash
# Direct execution
python rffl_boxscores/cli.py export --league 323196 --year 2024

# Or as a module (if installed)
rffl-bs export --league 323196 --year 2024

# Or via the vibe helper
source ./vibe.sh
bs 2024
```

### Other common naming patterns you might see:
- `main.py` - Entry point script
- `app.py` - Application logic
- `server.py` - Web server
- `run.py` - Simple runner script
- `manage.py` - Django management commands
- `__init__.py` - Package initialization

### Why "CLI" specifically?
The CLI naming convention is helpful because it immediately tells developers:
- ✅ "This runs from the command line"
- ✅ "This has command-line arguments"
- ✅ "This is a standalone tool, not a library"

## Key Insights
- CLI scripts are command-line tools, not web apps or GUIs
- `cli.py` is a standard naming convention that immediately communicates purpose
- The file uses the Typer framework for building command-line interfaces
- It's designed to be run from terminal with various command options
- The naming helps developers understand the file's role at a glance

## Practical Applications
- Use `cli.py` naming for any command-line tool you create
- Follow the pattern: `[purpose].py` (e.g., `server.py`, `migrate.py`, `test.py`)
- Consider using frameworks like Typer or Click for complex CLIs
- Always include `if __name__ == "__main__":` for direct execution

## Related Commands/Files
- `rffl_boxscores/cli.py` - The main CLI script
- `vibe.sh` - Helper script with convenient aliases
- `pyproject.toml` - Project configuration
- `requirements.txt` - Dependencies

## Future Learning Path
- Learn more about the Typer framework for Python CLIs
- Explore other Python CLI frameworks (Click, argparse)
- Understand Python package structure and `__init__.py` files
- Study command-line argument parsing patterns
- Investigate how to package CLI tools for distribution

## Personal Notes
[Space for your own annotations and thoughts]

---
*Synthesized by AI Assistant for your personal knowledge library*
