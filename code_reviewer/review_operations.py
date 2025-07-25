"""
High-level review workflow operations for the code reviewer.
"""

import logging
from pathlib import Path
from typing import Optional

from .config import Config
from .exceptions import FileError, UserCancelledError
from .file_utils import read_file_content, count_lines
from .git_helper import GitHelper


def review_single_file(filepath: str, max_lines: int, yes: bool = False) -> str:
    """Review a single file and return its content.
    
    Args:
        filepath: Path to file to review
        max_lines: Maximum lines allowed before user confirmation
        yes: Skip user prompts and automatically proceed
        
    Returns:
        File content as string
        
    Raises:
        FileError: If file doesn't exist, is empty, or can't be read
        UserCancelledError: If user cancels the review
    """
    file_path = Path(filepath)
    if not file_path.exists():
        raise FileError(f"File {filepath} does not exist")

    content = read_file_content(filepath)
        
    if not content.strip():
        raise FileError(f"File {filepath} is empty")

    line_count = count_lines(content)
    if line_count > max_lines:
        if yes:
            # Auto-proceed when --yes flag is used
            pass
        else:
            response = input(f"⚠️  File has {line_count} lines (max: {max_lines}). Continue? [y/N]: ")
            if response.lower() != 'y':
                raise UserCancelledError("Review cancelled by user")
    
    return content


def review_git_changes(git: GitHelper, config: Config, since_commit: Optional[str] = None, 
                      yes: bool = False, logger: Optional[logging.Logger] = None) -> str:
    """Review git changes and return diff content.
    
    Args:
        git: GitHelper instance
        config: Configuration instance
        since_commit: Compare against this commit (optional)
        yes: Skip user prompts and automatically proceed
        logger: Logger for info messages
        
    Returns:
        Git diff content as string
        
    Raises:
        FileError: If no files found
        UserCancelledError: If user cancels the review
        GitError: If git operations fail
    """
    if logger is None:
        logger = logging.getLogger('codereviewer')
        
    if since_commit:
        diff_mode = "since-commit"
        changed_files = git.get_changed_files(since_commit)
    else:
        diff_mode = "uncommitted"
        changed_files = git.get_changed_files()

    if not changed_files:
        diff_mode = "last-commit"
        changed_files = git.get_last_commit_files()

    if not changed_files:
        raise FileError("Couldn't find any changed files")

    logger.info(f"Found {len(changed_files)} changed file(s): {', '.join(changed_files)}")

    # Get diff content and check size
    diff_content = git.get_diff_content(changed_files, diff_mode, since_commit)
    if diff_content:
        diff_lines = count_lines(diff_content)
        if diff_lines > config.max_total_diff_lines:
            if yes:
                # Auto-proceed when --yes flag is used
                pass
            else:
                response = input(f"⚠️  Large diff detected ({diff_lines} lines). Continue with full diff review? [y/N]: ")
                if response.lower() != 'y':
                    raise UserCancelledError("Consider reviewing files one at a time with: cr <filename>")
        
        # Wrap diff content in markdown code block for better LLM understanding
        diff_content = f"```diff\n{diff_content}\n```"
    
    return diff_content