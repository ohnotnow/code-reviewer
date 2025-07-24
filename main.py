#!/usr/bin/env python3
"""
Code Review CLI Tool
A friendly code reviewer powered by an LLM.
"""

import argparse
import os
import shutil
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
DEFAULT_MODEL = "openai/o4-mini"


# Error handling classes
class ReviewError(Exception):
    """Base exception for review operations."""
    pass


class GitError(ReviewError):
    """Git operation failed."""
    pass


class FileError(ReviewError):
    """File operation failed."""
    pass


class LLMError(ReviewError):
    """LLM API operation failed."""
    pass

def run_command(cmd: List[str]) -> str:
    """Run a shell command and return output, raise GitError on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"Command failed: {' '.join(cmd)}\n{e.stderr.strip()}")
    except FileNotFoundError:
        raise GitError(f"Command not found: {cmd[0]}")


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

def get_git_changed_files(since_commit: str = None) -> List[str]:
    """Get list of changed files from git status."""
    try:
        if since_commit:
            output = run_command(['git', 'diff', '--name-only', since_commit, 'HEAD'])
            parse_status = False
        else:
            output = run_command(['git', 'status', '--porcelain'])
            parse_status = True

        changed_files = extract_supported_files(output, parse_status=parse_status)
        return changed_files
    except GitError:
        # Re-raise git errors as-is
        raise

def get_git_last_commit_files() -> List[str]:
    """Get list of files changed in the last commit."""
    try:
        output = run_command(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'])
        return extract_supported_files(output, parse_status=False)
    except GitError:
        # Re-raise git errors as-is
        raise

def read_file_content(filepath: str) -> str:
    """Read file content, raise FileError on failure."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        raise FileError(f"Error reading {filepath}: {e}")

def get_git_diff_content(files: List[str], diff_mode: str) -> str:
    """Get git diff content for specified files."""
    if not files:
        return ""

    try:
        if diff_mode == "uncommitted":
            output = run_command(['git', 'diff', 'HEAD'] + files)
        else:
            output = run_command(['git', 'diff', 'HEAD^', 'HEAD'] + files)
        return output
    except GitError as e:
        print(f"⚠️  Warning: Could not get git diff: {e}")
        return ""

def get_system_prompt(prompt_file: str = None) -> str:
    """Get the system prompt for the code review."""
    if prompt_file:
        prompt_file = Path(prompt_file).expanduser()
        if not prompt_file.exists():
            raise FileError(f"Prompt file {prompt_file} does not exist")
        print(f"Using prompt file: {prompt_file}")
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()
        except (PermissionError, UnicodeDecodeError) as e:
            raise FileError(f"Error reading prompt file {prompt_file}: {e}")

    default_prompt_locations = [Path("~/.code-review-prompt.md").expanduser(), Path(__file__).parent / "system_prompt.md"]
    for prompt_path in default_prompt_locations:
        if prompt_path.exists():
            print(f"Using default prompt file: {prompt_path}")
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read()
            except (PermissionError, UnicodeDecodeError) as e:
                continue  # Try next location

    raise FileError(f"No prompt file found in {default_prompt_locations}")


def review_code(content: str, model: str = DEFAULT_MODEL, prompt_file: str = None, debug: bool = False) -> str:
    """Send code to LLM for review."""
    try:
        system_prompt = get_system_prompt(prompt_file)
    except FileError:
        # Re-raise file errors as-is
        raise
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
        raise LLMError(f"Error getting review from LLM: {e}")


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
        '--since-commit',
        type=str,
        default=None,
        required=False,
        help='Review changes since a specific commit'
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
        default=DEFAULT_MODEL,
        help=f'Model to use for code review (default: {DEFAULT_MODEL})'
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
    try:
        run_command(['git', 'rev-parse', '--git-dir'])
    except GitError:
        print("❌ Error: Not in a git repository")
        sys.exit(1)

    if args.file:
        # Review specific file
        if not Path(args.file).exists():
            print(f"❌ Error: File {args.file} does not exist")
            sys.exit(1)

        try:
            review_content = read_file_content(args.file)
        except FileError as e:
            print(f"❌ {e}")
            sys.exit(1)
            
        if not review_content.strip():
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
        try:
            changed_files = get_git_changed_files(args.since_commit)

            if not changed_files:
                diff_mode = "last-commit"
                changed_files = get_git_last_commit_files()

            if not changed_files:
                print("❌ Error: Couldn't find any changed files.")
                sys.exit(0)
        except GitError as e:
            print(f"❌ {e}")
            sys.exit(1)

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
    try:
        review = review_code(review_content, model=args.model, prompt_file=args.prompt_file, debug=args.debug)
    except (FileError, LLMError) as e:
        print(f"❌ {e}")
        sys.exit(1)

    print("\n" + "="*60)
    # check if we have the `glow` binary available
    if shutil.which('glow'):
        # use glow to print the review by passing it as stdin
        subprocess.run(['glow', '-s', 'dracula'], input=review.encode('utf-8'))
    else:
        print(review)

    print("="*60)


if __name__ == "__main__":
    main()
