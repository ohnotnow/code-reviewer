#!/usr/bin/env python3
"""
Code Review CLI Tool
A friendly code reviewer powered by an LLM.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile
from litellm import completion
import litellm

# Configuration
MAX_SINGLE_FILE_LINES = 500
MAX_TOTAL_DIFF_LINES = 1000
SUPPORTED_EXTENSIONS = {'.php', '.py', '.js'}

def run_command(cmd: List[str]) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def is_supported_file(filepath: str) -> bool:
    """Check if file is a supported file we should review."""
    path = Path(filepath)
    return path.suffix in SUPPORTED_EXTENSIONS


def count_lines(content: str) -> int:
    """Count non-empty lines in content."""
    return len([line for line in content.split('\n') if line.strip()])


def extract_supported_files(git_output: str, parse_status: bool = True) -> List[str]:
    """Extract supported files from git output.

    Args:
        git_output: Output from a git command.
        parse_status: Whether to parse the first 2 characters as git status.

    Returns:
        List of supported file paths.
    """
    changed_files = []
    for line in git_output.splitlines():
        line = line.strip()
        if not line:
            continue

        if parse_status:
            status = line[:2]
            filename = line[2:].strip()
            if 'D' in status:
                continue
        else:
            filename = line

        if is_supported_file(filename) and Path(filename).exists():
            changed_files.append(filename)

    return changed_files

def get_git_changed_files() -> List[str]:
    """Get list of changed files from git status."""
    success, output = run_command(['git', 'status', '--porcelain'])

    if not success:
        print(f"❌ Error getting git status: {output}")
        return []

    changed_files = extract_supported_files(output, parse_status=True)

    return changed_files

def get_git_last_commit_files() -> List[str]:
    """Get list of files changed in the last commit."""
    success, output = run_command(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'])
    if not success:
        print(f"❌ Error getting git last commit files: {output}")
        return []

    return extract_supported_files(output, parse_status=False)

def read_file_content(filepath: str) -> Optional[str]:
    """Read file content, return None if file doesn't exist or can't be read."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        print(f"❌ Error reading {filepath}: {e}")
        return None

def get_git_diff_content(files: List[str], diff_mode: str) -> str:
    """Get git diff content for specified files."""
    if not files:
        return ""

    if diff_mode == "uncommitted":
        success, output = run_command(['git', 'diff', 'HEAD'] + files)
    else:
        success, output = run_command(['git', 'diff', 'HEAD^', 'HEAD'] + files)

    if not success:
        print(f"⚠️  Warning: Could not get git diff: {output}")
        return ""

    return output

def get_system_prompt(prompt_file: str = None) -> str:
    """Get the system prompt for the code review."""
    if prompt_file:
        prompt_file = Path(prompt_file).expanduser()
        if prompt_file.exists():
            print(f"Using prompt file: {prompt_file}")
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()
        else:
            print(f"❌ Error: Prompt file {prompt_file} does not exist")
            sys.exit(1)

    default_prompt_locations = [Path("~/.code-review-prompt.md").expanduser(), Path(__file__).parent / "system_prompt.md"]
    for prompt_file in default_prompt_locations:
        if prompt_file.exists():
            print(f"Using default prompt file: {prompt_file}")
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()

    print(f"❌ Error: No prompt file found in {default_prompt_locations}")
    sys.exit(1)


def review_code(content: str, model: str = "openai/gpt-4.1", prompt_file: str = None, debug: bool = False) -> str:
    """Send code to LLM for review."""
    system_prompt = get_system_prompt(prompt_file)
    litellm.drop_params = True
    if debug:
        print("="*60)
        print(f"SYSTEM PROMPT: {system_prompt}")
        print("="*60)
        print(f"CONTENT: {content}")
        print("="*60)
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
        return f"❌ Error getting review from LLM: {e}"


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
    parser.add_argument(
        '--prompt-file',
        type=str,
        default=None,
        help='Specific prompt file to use for this run'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    args = parser.parse_args()

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

        review_content = read_file_content(args.file)
        if review_content is None:
            print(f"❌ Error: File {args.file} is empty")
            sys.exit(1)

        line_count = count_lines(review_content)
        if line_count > args.max_lines:
            response = input(f"⚠️  File has {line_count} lines (max: {args.max_lines}). Continue? [y/N]: ")
            if response.lower() != 'y':
                print("Review cancelled.")
                sys.exit(0)

    else:
        # Review git changes
        diff_mode = "uncommitted"
        changed_files = get_git_changed_files()

        if not changed_files:
            diff_mode = "last-commit"
            changed_files = get_git_last_commit_files()

        if not changed_files:
            print("❌ Error: Couldn't find any changed files.")
            sys.exit(0)

        print(f"📁 Found {len(changed_files)} changed file(s): {', '.join(changed_files)}")

        # Get diff content and check size
        diff_content = get_git_diff_content(changed_files, diff_mode)
        if diff_content:
            diff_lines = count_lines(diff_content)
            if diff_lines > MAX_TOTAL_DIFF_LINES:
                print(f"⚠️  Large diff detected ({diff_lines} lines). Consider reviewing files individually.")
                response = input("Continue with full diff review? [y/N]: ")
                if response.lower() != 'y':
                    print("Consider reviewing files one at a time with: cr <filename>")
                    sys.exit(0)
        review_content = diff_content

    # Get review from LLM
    review = review_code(review_content, model=args.model, prompt_file=args.prompt_file, debug=args.debug)

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
