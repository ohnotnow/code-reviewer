# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based CLI tool for code review powered by LLMs (specifically designed for PHP/Laravel projects but supports multiple languages). The tool reviews either individual files or git diffs and provides structured feedback using a conversational, emoji-driven approach.

## Development Commands

### Environment Setup
```bash
# Install dependencies using UV
uv sync

# Activate virtual environment (if needed)
source .venv/bin/activate
```

### Running the Tool
```bash
# Review all staged changes
uv run main.py

# Review specific file
uv run main.py path/to/file.php

# Review with custom model
uv run main.py --model openai/gpt-4

# Review changes since specific commit
uv run main.py --since-commit abc123

# Use custom prompt file
uv run main.py --prompt-file custom-prompt.md

# Enable debug mode
uv run main.py --debug
```

### Configuration
- Set `OPENAI_API_KEY` environment variable for LLM access
- Default prompt file: `system_prompt.md` (can be overridden with `~/.code-review-prompt.md`)
- Supported file extensions: `.php`, `.py`, `.js`

## Code Architecture

### Core Components

**main.py** - Single-file application with the following key functions:
- `get_git_changed_files()` - Extracts changed files from git status/diff
- `review_code()` - Interfaces with LLM via litellm for code review
- `get_system_prompt()` - Loads review prompt from configurable locations
- `extract_supported_files()` - Filters files by supported extensions

### Configuration Constants
- `MAX_SINGLE_FILE_LINES = 500` - Line limit for single file reviews
- `MAX_TOTAL_DIFF_LINES = 1000` - Line limit for diff reviews
- `SUPPORTED_EXTENSIONS = {'.php', '.py', '.js'}` - Supported file types

### Dependencies
- **litellm** - LLM interface supporting multiple providers
- Standard library only (subprocess, pathlib, argparse, etc.)

### Review System Architecture

The tool uses a sophisticated prompt system defined in `system_prompt.md` that:
- Provides friendly, constructive feedback using emojis
- Focuses on readability, defensive programming, and modern language patterns
- Includes Laravel-specific guidance for PHP projects
- Structures responses with positive reinforcement and grouped suggestions

### Output Formatting
- Supports `glow` markdown renderer for enhanced terminal display
- Falls back to plain text if glow is not available
- Uses structured markdown format for consistent review presentation

## Key Features
- Supports both single file and git diff review modes
- Configurable line limits with user prompts for large files
- Custom prompt file support for different project types
- Debug mode for troubleshooting LLM interactions
- Graceful fallback for missing files or git repositories