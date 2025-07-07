#!/usr/bin/env python3
"""
Code Review CLI Tool
A friendly code reviewer powered by Claude for PHP/Laravel projects.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile

try:
    from litellm import completion
    import litellm
except ImportError:
    print("❌ Error: litellm not installed. Run: pip install litellm")
    sys.exit(1)

# Configuration
MAX_SINGLE_FILE_LINES = 500
MAX_TOTAL_DIFF_LINES = 1000
SUPPORTED_EXTENSIONS = {'.php', '.blade.php'}

def run_command(cmd: List[str]) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def is_php_file(filepath: str) -> bool:
    """Check if file is a PHP file we should review."""
    path = Path(filepath)
    return path.suffix in SUPPORTED_EXTENSIONS


def count_lines(content: str) -> int:
    """Count non-empty lines in content."""
    return len([line for line in content.split('\n') if line.strip()])


def get_git_changed_files() -> List[str]:
    """Get list of changed files from git status."""
    success, output = run_command(['git', 'status', '--porcelain'])

    if not success:
        print(f"❌ Error getting git status: {output}")
        return []

    changed_files = []
    for line in output.split('\n'):
        if line.strip():
            # Parse git status output: first two chars are status, rest is filename
            status = line[:2]
            filename = line[3:].strip()

            # Skip deleted files
            if 'D' in status:
                continue

            # Only include PHP files
            if is_php_file(filename) and Path(filename).exists():
                changed_files.append(filename)

    return changed_files


def read_file_content(filepath: str) -> Optional[str]:
    """Read file content, return None if file doesn't exist or can't be read."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        print(f"❌ Error reading {filepath}: {e}")
        return None


def get_git_diff_content(files: List[str]) -> str:
    """Get git diff content for specified files."""
    if not files:
        return ""

    success, output = run_command(['git', 'diff', 'HEAD'] + files)
    if not success:
        print(f"⚠️  Warning: Could not get git diff: {output}")
        return ""

    return output


def format_single_file_review(filepath: str, content: str) -> str:
    """Format content for single file review."""
    return f"""Please review this PHP file: {filepath}

```php
{content}
```

Please provide a friendly code review focusing on readability, Laravel best practices, and potential improvements."""


def format_diff_review(files: List[str], diff_content: str) -> str:
    """Format content for git diff review."""
    file_list = ", ".join(files)
    return f"""Please review the changes in these files: {file_list}

Here's the git diff showing what has changed:

```diff
{diff_content}
```

Please provide a friendly code review focusing on the changes made, highlighting good practices and suggesting improvements where appropriate."""

def get_system_prompt() -> str:
    """Get the system prompt for the code review."""
    if Path("~/.code-review-prompt.md").expanduser().exists():
        with open(Path("~/.code-review-prompt.md").expanduser(), "r", encoding="utf-8") as f:
            return f.read()
    else:
        script_dir = Path(__file__).parent
        with open(script_dir / "system_prompt.md", "r", encoding="utf-8") as f:
            return f.read()

def review_code(content: str, model: str = "openai/gpt-4.1") -> str:
    """Send code to LLM for review."""
    system_prompt = get_system_prompt()
    litellm.drop_params = True
    try:
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            max_tokens=1500,
            temperature=0.3
        )

        return str(response.choices[0].message.content)

    except Exception as e:
        return f"❌ Error getting review from Claude: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Friendly LLM code review tool",
        epilog="Examples:\n  cr                           # Review changed files\n  cr app/Models/User.php       # Review specific file",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'file',
        nargs='?',
        help='Specific file to review (if not provided, reviews git changes)'
    )
    parser.add_argument(
        '--max-lines',
        type=int,
        default=MAX_SINGLE_FILE_LINES,
        help=f'Maximum lines for single file review (default: {MAX_SINGLE_FILE_LINES})'
    )
    parser.add_argument(
        '--model',
        type=str,
        default="openai/gpt-4.1",
        help='Model to use for code review (default: openai/gpt-4.1)'
    )

    args = parser.parse_args()

    # Check for API key

    # Check if we're in a git repository
    success, _ = run_command(['git', 'rev-parse', '--git-dir'])
    if not success:
        print("❌ Error: Not in a git repository")
        sys.exit(1)

    if args.file:
        # Review specific file
        if not Path(args.file).exists():
            print(f"❌ Error: File {args.file} does not exist")
            sys.exit(1)

        if not is_php_file(args.file):
            print(f"❌ Error: {args.file} is not a PHP file")
            sys.exit(1)

        content = read_file_content(args.file)
        if content is None:
            sys.exit(1)

        line_count = count_lines(content)
        if line_count > args.max_lines:
            response = input(f"⚠️  File has {line_count} lines (max: {args.max_lines}). Continue? [y/N]: ")
            if response.lower() != 'y':
                print("Review cancelled.")
                sys.exit(0)

        print(f"🔍 Reviewing {args.file}...")
        review_content = format_single_file_review(args.file, content)

    else:
        # Review git changes
        changed_files = get_git_changed_files()

        if not changed_files:
            print("✅ No PHP files have been changed.")
            sys.exit(0)

        print(f"📁 Found {len(changed_files)} changed PHP file(s): {', '.join(changed_files)}")

        # Get diff content and check size
        diff_content = get_git_diff_content(changed_files)
        if diff_content:
            diff_lines = count_lines(diff_content)
            if diff_lines > MAX_TOTAL_DIFF_LINES:
                print(f"⚠️  Large diff detected ({diff_lines} lines). Consider reviewing files individually.")
                response = input("Continue with full diff review? [y/N]: ")
                if response.lower() != 'y':
                    print("Consider reviewing files one at a time with: cr <filename>")
                    sys.exit(0)

        print("🔍 Reviewing changes...")
        review_content = format_diff_review(changed_files, diff_content)

    # Get review from Claude
    review = review_code(review_content, model="openai/gpt-4.1")

    print("\n" + "="*60)
    # check if we have the `glow` binary available
    if run_command(['which', 'glow'])[0]:
        # use glow to print the review by passing it as stdin
        subprocess.run(['glow', '-s', 'dracula'], input=review.encode('utf-8'))
    else:
        print(review)

    print("="*60)


if __name__ == "__main__":
    main()
