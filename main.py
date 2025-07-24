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
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Set
import tempfile
from litellm import completion
import litellm

@dataclass
class Config:
    """Configuration settings for the code reviewer."""
    max_single_file_lines: int = 500
    max_total_diff_lines: int = 1000
    supported_extensions: Set[str] = frozenset({'.php', '.py', '.js'})
    default_model: str = "openai/o4-mini"
    max_tokens: int = 1500
    temperature: float = 0.3
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load config from environment variables if needed."""
        # For now, just return defaults. Can be extended later.
        return cls()


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


def is_supported_file(filepath: str, config: Config) -> bool:
    """Check if file is a supported file we should review."""
    path = Path(filepath)
    return path.suffix in config.supported_extensions


def count_lines(content: str) -> int:
    """Count non-empty lines in content."""
    return len([line for line in content.split('\n') if line.strip()])


class GitHelper:
    """Helper class for git operations."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def check_git_repo(self) -> None:
        """Check if we're in a git repository."""
        try:
            run_command(['git', 'rev-parse', '--git-dir'])
        except GitError:
            raise GitError("Not in a git repository")
    
    def extract_supported_files(self, git_output: str, parse_status: bool = True) -> List[str]:
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

            if is_supported_file(filename, self.config) and Path(filename).exists():
                changed_files.append(filename)

        return changed_files

    def get_changed_files(self, since_commit: str = None) -> List[str]:
        """Get list of changed files from git status."""
        try:
            if since_commit:
                output = run_command(['git', 'diff', '--name-only', since_commit, 'HEAD'])
                parse_status = False
            else:
                output = run_command(['git', 'status', '--porcelain'])
                parse_status = True

            changed_files = self.extract_supported_files(output, parse_status=parse_status)
            return changed_files
        except GitError:
            # Re-raise git errors as-is
            raise

    def get_last_commit_files(self) -> List[str]:
        """Get list of files changed in the last commit."""
        try:
            output = run_command(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'])
            return self.extract_supported_files(output, parse_status=False)
        except GitError:
            # Re-raise git errors as-is
            raise

    def get_diff_content(self, files: List[str], diff_mode: str) -> str:
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


def read_file_content(filepath: str) -> str:
    """Read file content, raise FileError on failure."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        raise FileError(f"Error reading {filepath}: {e}")

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


class CodeReviewer:
    """Core code review functionality."""
    
    def __init__(self, config: Config):
        self.config = config
        
    def review_file(self, filepath: str, max_lines: int, model: str = None, prompt_file: str = None, debug: bool = False) -> str:
        """Review a single file."""
        content = review_single_file(filepath, max_lines)
        return self.get_review(content, model, prompt_file, debug)
        
    def review_changes(self, git: GitHelper, since_commit: str = None, model: str = None, prompt_file: str = None, debug: bool = False) -> str:
        """Review git changes."""
        content = review_git_changes(git, self.config, since_commit)
        return self.get_review(content, model, prompt_file, debug)
        
    def get_review(self, content: str, model: str = None, prompt_file: str = None, debug: bool = False) -> str:
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
                model=model or self.config.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            return str(response.choices[0].message.content)

        except Exception as e:
            raise LLMError(f"Error getting review from LLM: {e}")


def create_parser(config: Config) -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
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
        default=config.max_single_file_lines,
        help=f'Maximum lines for single file review (default: {config.max_single_file_lines})'
    )
    parser.add_argument(
        '--model',
        type=str,
        default=config.default_model,
        help=f'Model to use for code review (default: {config.default_model})'
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
    return parser


def review_single_file(filepath: str, max_lines: int) -> str:
    """Review a single file and return its content."""
    if not Path(filepath).exists():
        print(f"❌ Error: File {filepath} does not exist")
        sys.exit(1)

    try:
        content = read_file_content(filepath)
    except FileError as e:
        print(f"❌ {e}")
        sys.exit(1)
        
    if not content.strip():
        print(f"❌ Error: File {filepath} is empty")
        sys.exit(1)

    line_count = count_lines(content)
    if line_count > max_lines:
        response = input(f"⚠️  File has {line_count} lines (max: {max_lines}). Continue? [y/N]: ")
        if response.lower() != 'y':
            print("Review cancelled.")
            sys.exit(0)
    
    return content


def review_git_changes(git: GitHelper, config: Config, since_commit: str = None) -> str:
    """Review git changes and return diff content."""
    diff_mode = "uncommitted"
    try:
        changed_files = git.get_changed_files(since_commit)

        if not changed_files:
            diff_mode = "last-commit"
            changed_files = git.get_last_commit_files()

        if not changed_files:
            print("❌ Error: Couldn't find any changed files.")
            sys.exit(0)
    except GitError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"📁 Found {len(changed_files)} changed file(s): {', '.join(changed_files)}")

    # Get diff content and check size
    diff_content = git.get_diff_content(changed_files, diff_mode)
    if diff_content:
        diff_lines = count_lines(diff_content)
        if diff_lines > config.max_total_diff_lines:
            print(f"⚠️  Large diff detected ({diff_lines} lines). Consider reviewing files individually.")
            response = input("Continue with full diff review? [y/N]: ")
            if response.lower() != 'y':
                print("Consider reviewing files one at a time with: cr <filename>")
                sys.exit(0)
    
    return diff_content


def display_review(review: str) -> None:
    """Display the review using glow if available, otherwise plain text."""
    print("\n" + "="*60)
    if shutil.which('glow'):
        subprocess.run(['glow', '-s', 'dracula'], input=review.encode('utf-8'))
    else:
        print(review)
    print("="*60)


def main():
    """Main entry point for the code reviewer."""
    config = Config.from_env()
    git = GitHelper(config)
    reviewer = CodeReviewer(config)
    
    parser = create_parser(config)
    args = parser.parse_args()

    # Check if we're in a git repository
    try:
        git.check_git_repo()
    except GitError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    # Get review from LLM
    try:
        if args.file:
            review = reviewer.review_file(args.file, args.max_lines, args.model, args.prompt_file, args.debug)
        else:
            review = reviewer.review_changes(git, args.since_commit, args.model, args.prompt_file, args.debug)
    except (FileError, LLMError) as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Display results
    display_review(review)


if __name__ == "__main__":
    main()
