"""
Git operations for the code reviewer.
"""

import logging
from pathlib import Path
from typing import List, Optional

from .config import Config
from .exceptions import GitError
from .file_utils import run_command, is_supported_file
from .time_parser import parse_time_duration, datetime_to_git_format


class GitHelper:
    """Helper class for git operations.
    
    Attributes:
        config: Configuration instance
        logger: Logger for debugging git operations
    """
    
    def __init__(self, config: Config, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger('codereviewer')
    
    def check_git_repo(self) -> None:
        """Check if we're in a git repository.
        
        Raises:
            GitError: If not in a git repository
        """
        try:
            run_command(['git', 'rev-parse', '--git-dir'])
            self.logger.debug("Git repository check passed")
        except GitError:
            raise GitError("Not in a git repository")
    
    def get_commit_from_time(self, time_spec: str) -> Optional[str]:
        """Get the commit hash closest to the specified time.
        
        Args:
            time_spec: Time specification (e.g., '1h', '30m', 'today')
            
        Returns:
            Commit hash if found, None if no commits exist at or before that time
            
        Raises:
            GitError: If git command fails or time format is invalid
        """
        try:
            target_time = parse_time_duration(time_spec)
            git_time = datetime_to_git_format(target_time)
            
            self.logger.debug(f"Looking for commit since: {git_time}")
            
            # Get the first commit at or before the target time
            output = run_command([
                'git', 'rev-list', '-n', '1', 
                f'--before={git_time}', 
                'HEAD'
            ])
            
            commit_hash = output.strip()
            if commit_hash:
                self.logger.debug(f"Found commit: {commit_hash}")
                return commit_hash
            else:
                self.logger.debug("No commits found before target time")
                return None
                
        except ValueError as e:
            raise GitError(f"Invalid time format: {e}")
        except GitError:
            # Re-raise git errors as-is
            raise
    
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
                self.logger.debug(f"Added supported file: {filename}")

        self.logger.debug(f"Extracted {len(changed_files)} supported files")
        return changed_files

    def get_changed_files(self, since_commit: Optional[str] = None) -> List[str]:
        """Get list of changed files from git status.
        
        Args:
            since_commit: Compare against this commit if provided
            
        Returns:
            List of changed file paths
            
        Raises:
            GitError: If git command fails
        """
        try:
            if since_commit:
                self.logger.debug(f"Getting files changed since commit: {since_commit}")
                output = run_command(['git', 'diff', '--name-only', since_commit, 'HEAD'])
                parse_status = False
            else:
                self.logger.debug("Getting staged files from git status")
                output = run_command(['git', 'status', '--porcelain'])
                parse_status = True

            changed_files = self.extract_supported_files(output, parse_status=parse_status)
            return changed_files
        except GitError:
            # Re-raise git errors as-is
            raise

    def get_last_commit_files(self) -> List[str]:
        """Get list of files changed in the last commit.
        
        Returns:
            List of file paths from last commit
            
        Raises:
            GitError: If git command fails
        """
        try:
            self.logger.debug("Getting files from last commit")
            output = run_command(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'])
            files = self.extract_supported_files(output, parse_status=False)
            self.logger.info(f"Found {len(files)} files in last commit")
            return files
        except GitError:
            # Re-raise git errors as-is
            raise

    def get_diff_content(self, files: List[str], diff_mode: str, since_commit: Optional[str] = None) -> str:
        """Get git diff content for specified files.
        
        Args:
            files: List of files to get diff for
            diff_mode: Either 'uncommitted', 'last-commit', or 'since-commit'
            since_commit: Commit to compare against (used when diff_mode is 'since-commit')
            
        Returns:
            Git diff content as string
            
        Raises:
            GitError: If git diff command fails (e.g., invalid commit hash)
        """
        if not files:
            self.logger.debug("No files provided for diff")
            return ""

        try:
            context_arg = f'-U{self.config.diff_context_lines}'
            if diff_mode == "since-commit" and since_commit:
                self.logger.debug(f"Getting diff since commit: {since_commit}")
                output = run_command(['git', 'diff', context_arg, since_commit, 'HEAD'] + files)
            elif diff_mode == "uncommitted":
                self.logger.debug("Getting uncommitted changes diff")
                output = run_command(['git', 'diff', context_arg, 'HEAD'] + files)
            else:
                self.logger.debug("Getting last commit diff")
                output = run_command(['git', 'diff', context_arg, 'HEAD^', 'HEAD'] + files)
            
            word_count = len(output.split())
            self.logger.info(f"Retrieved diff content ({word_count} words)")
            return output
        except GitError:
            # Re-raise git errors - don't hide them with empty string
            raise