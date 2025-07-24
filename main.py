#!/usr/bin/env python3
"""
Code Review CLI Tool - A friendly code reviewer powered by an LLM.

This tool analyzes code files or git changes and provides structured feedback
using an LLM. It supports single file reviews and git diff analysis with
customizable prompts and models.
"""

import argparse
import logging
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

# Loggers to suppress in non-debug mode
SUPPRESSED_LOGGERS = ['LiteLLM', 'httpx']

@dataclass
class Config:
    """Configuration settings for the code reviewer.
    
    Attributes:
        max_single_file_lines: Maximum lines allowed for single file review
        max_total_diff_lines: Maximum lines allowed for diff review
        supported_extensions: File extensions that can be reviewed
        default_model: Default LLM model to use
        max_tokens: Maximum tokens for LLM response
        temperature: LLM temperature setting (0.0-1.0)
        glow_style: Style theme for glow markdown rendering
    """
    max_single_file_lines: int = 500
    max_total_diff_lines: int = 1000
    supported_extensions: Set[str] = frozenset({'.php', '.py', '.js'})
    default_model: str = "openai/o4-mini"
    max_tokens: int = 1500
    temperature: float = 0.3
    glow_style: str = "dracula"
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load config from environment variables if needed.
        
        Returns:
            Config instance with settings from environment or defaults
        """
        # For now, just return defaults. Can be extended later for env vars.
        return cls()
        
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.max_single_file_lines <= 0:
            raise ValueError("max_single_file_lines must be positive")
        if self.max_total_diff_lines <= 0:
            raise ValueError("max_total_diff_lines must be positive")
        if not (0.0 <= self.temperature <= 1.0):
            raise ValueError("temperature must be between 0.0 and 1.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")


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


class UserCancelledError(ReviewError):
    """User cancelled the operation."""
    pass

def run_command(cmd: List[str]) -> str:
    """Run a shell command and return output, raise GitError on failure.
    
    Args:
        cmd: Command and arguments to execute
        
    Returns:
        Command output as string
        
    Raises:
        GitError: If command fails or is not found
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"Command failed: {' '.join(cmd)}\n{e.stderr.strip()}")
    except FileNotFoundError:
        raise GitError(f"Command not found: {cmd[0]}")


def is_supported_file(filepath: str, config: Config) -> bool:
    """Check if file is a supported file we should review.
    
    Args:
        filepath: Path to the file to check
        config: Configuration containing supported extensions
        
    Returns:
        True if file extension is supported, False otherwise
    """
    path = Path(filepath)
    return path.suffix in config.supported_extensions


def count_lines(content: str) -> int:
    """Count non-empty lines in content.
    
    Args:
        content: Text content to count lines in
        
    Returns:
        Number of non-empty lines
    """
    return len([line for line in content.split('\n') if line.strip()])


def setup_logging(debug: bool = False) -> logging.Logger:
    """Setup logging configuration.
    
    Args:
        debug: Enable debug level logging if True
        
    Returns:
        Configured logger instance
    """
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[handler]
    )
    
    # Suppress noisy third-party loggers unless in debug mode
    if not debug:
        for logger_name in SUPPRESSED_LOGGERS:
            logging.getLogger(logger_name).setLevel(logging.ERROR)
    
    return logging.getLogger(__name__)


class GitHelper:
    """Helper class for git operations.
    
    Attributes:
        config: Configuration instance
        logger: Logger for debugging git operations
    """
    
    def __init__(self, config: Config, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
    
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
            # Removed redundant log - the file list below is more informative
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

    def get_diff_content(self, files: List[str], diff_mode: str) -> str:
        """Get git diff content for specified files.
        
        Args:
            files: List of files to get diff for
            diff_mode: Either 'uncommitted' or 'last-commit'
            
        Returns:
            Git diff content as string
        """
        if not files:
            self.logger.debug("No files provided for diff")
            return ""

        try:
            if diff_mode == "uncommitted":
                self.logger.debug("Getting uncommitted changes diff")
                output = run_command(['git', 'diff', 'HEAD'] + files)
            else:
                self.logger.debug("Getting last commit diff")
                output = run_command(['git', 'diff', 'HEAD^', 'HEAD'] + files)
            
            word_count = len(output.split())
            self.logger.info(f"Retrieved diff content ({word_count} words)")
            return output
        except GitError as e:
            self.logger.warning(f"Could not get git diff: {e}")
            return ""


def read_file_content(filepath: str) -> str:
    """Read file content, raise FileError on failure.
    
    Args:
        filepath: Path to file to read
        
    Returns:
        File content as string
        
    Raises:
        FileError: If file cannot be read
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        raise FileError(f"Error reading {filepath}: {e}")

def get_system_prompt(prompt_file: Optional[str] = None, logger: Optional[logging.Logger] = None) -> str:
    """Get the system prompt for the code review.
    
    Args:
        prompt_file: Custom prompt file path (optional)
        logger: Logger instance for debug output
        
    Returns:
        System prompt content as string
        
    Raises:
        FileError: If no prompt file can be found or read
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    if prompt_file:
        prompt_file_path = Path(prompt_file).expanduser()
        if not prompt_file_path.exists():
            raise FileError(f"Prompt file {prompt_file_path} does not exist")
        logger.info(f"Using custom prompt file: {prompt_file_path}")
        try:
            with open(prompt_file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (PermissionError, UnicodeDecodeError) as e:
            raise FileError(f"Error reading prompt file {prompt_file_path}: {e}")

    default_prompt_locations = [
        Path("~/.code-review-prompt.md").expanduser(), 
        Path(__file__).parent / "system_prompt.md"
    ]
    
    for prompt_path in default_prompt_locations:
        if prompt_path.exists():
            logger.info(f"Using default prompt file: {prompt_path}")
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    return f.read()
            except (PermissionError, UnicodeDecodeError) as e:
                logger.debug(f"Failed to read {prompt_path}: {e}")
                continue  # Try next location

    raise FileError(f"No prompt file found in {default_prompt_locations}")


class CodeReviewer:
    """Core code review functionality.
    
    Attributes:
        config: Configuration instance
        logger: Logger for debugging review operations
    """
    
    def __init__(self, config: Config, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
    def review_file(self, filepath: str, max_lines: int, model: Optional[str] = None, 
                   prompt_file: Optional[str] = None, debug: bool = False) -> str:
        """Review a single file.
        
        Args:
            filepath: Path to file to review
            max_lines: Maximum lines allowed for review
            model: LLM model to use (optional)
            prompt_file: Custom prompt file (optional)
            debug: Enable debug output
            
        Returns:
            Review content from LLM
        """
        self.logger.debug(f"Starting single file review: {filepath}")
        content = review_single_file(filepath, max_lines)
        return self.get_review(content, model, prompt_file, debug)
        
    def review_changes(self, git: GitHelper, since_commit: Optional[str] = None, 
                      model: Optional[str] = None, prompt_file: Optional[str] = None, 
                      debug: bool = False) -> str:
        """Review git changes.
        
        Args:
            git: GitHelper instance
            since_commit: Compare against this commit (optional)
            model: LLM model to use (optional)
            prompt_file: Custom prompt file (optional)
            debug: Enable debug output
            
        Returns:
            Review content from LLM
        """
        self.logger.debug(f"Starting git changes review (since_commit: {since_commit})")
        content = review_git_changes(git, self.config, since_commit, self.logger)
        return self.get_review(content, model, prompt_file, debug)
        
    def get_review(self, content: str, model: Optional[str] = None, 
                  prompt_file: Optional[str] = None, debug: bool = False) -> str:
        """Send code to LLM for review.
        
        Args:
            content: Code content to review
            model: LLM model to use (optional)
            prompt_file: Custom prompt file (optional)
            debug: Enable debug output
            
        Returns:
            Review response from LLM
            
        Raises:
            FileError: If prompt file cannot be read
            LLMError: If LLM API call fails
        """
        try:
            system_prompt = get_system_prompt(prompt_file, self.logger)
        except FileError:
            # Re-raise file errors as-is
            raise
        
        model_to_use = model or self.config.default_model
        self.logger.debug(f"Sending review request to {model_to_use}")
        self.logger.debug(f"Content length: {len(content)} characters")
        
        # Check if content is too large (rough estimate: 4 chars per token)
        estimated_tokens = len(content + system_prompt) // 4
        if estimated_tokens > 100000:  # Conservative limit for most models
            raise LLMError(f"Content too large ({estimated_tokens:,} estimated tokens). Consider reviewing smaller chunks or individual files.")
        
        litellm.drop_params = True
        if debug:
            litellm._turn_on_debug()  # Enable LiteLLM debugging
            print("="*60)
            print(f"SYSTEM PROMPT: {system_prompt}")
            print("="*60)
            print(f"CONTENT: {content}")
            print("="*60)
            
        try:
            response = completion(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            # Extract response content
            if not hasattr(response, 'choices') or not response.choices:
                self.logger.debug(f"LLM response object: {response}")
                raise LLMError("LLM response has no choices")
                
            choice = response.choices[0]
            if not hasattr(choice, 'message') or not hasattr(choice.message, 'content'):
                self.logger.debug(f"Choice object: {choice}")
                raise LLMError("LLM response has invalid structure")
                
            content_value = choice.message.content
            self.logger.debug(f"Raw content value: {repr(content_value)}")
            
            if content_value is None:
                # Sometimes models return None content for various reasons
                self.logger.warning("LLM returned None content - possibly due to content filters or token limits")
                raise LLMError("LLM returned empty content (None). This may be due to content size, filters, or model limits.")
                
            review_content = str(content_value).strip()
            if not review_content:
                self.logger.warning(f"LLM returned empty string content. Raw value was: {repr(content_value)}")
                raise LLMError("LLM response content is empty after processing")
                
            self.logger.debug(f"Received review response ({len(review_content)} characters)")
            return review_content

        except Exception as e:
            self.logger.error(f"LLM API call failed: {e}")
            raise LLMError(f"Error getting review from LLM: {e}")


def validate_max_lines(value: str) -> int:
    """Validate max-lines argument.
    
    Args:
        value: String value from command line
        
    Returns:
        Validated integer value
        
    Raises:
        argparse.ArgumentTypeError: If value is invalid
    """
    try:
        int_value = int(value)
        if int_value <= 0:
            raise argparse.ArgumentTypeError(f"max-lines must be positive, got {int_value}")
        if int_value > 10000:
            raise argparse.ArgumentTypeError(f"max-lines too large (max 10000), got {int_value}")
        return int_value
    except ValueError:
        raise argparse.ArgumentTypeError(f"max-lines must be an integer, got '{value}'")


def validate_model_name(value: str) -> str:
    """Validate model name argument.
    
    Args:
        value: Model name from command line
        
    Returns:
        Validated model name
        
    Raises:
        argparse.ArgumentTypeError: If model name format is invalid
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("model name cannot be empty")
    
    # Basic validation - should contain provider/model format
    if '/' not in value:
        raise argparse.ArgumentTypeError(f"model should be in format 'provider/model', got '{value}'")
    
    return value.strip()


def validate_prompt_file(value: str) -> str:
    """Validate prompt file argument.
    
    Args:
        value: Prompt file path from command line
        
    Returns:
        Validated file path
        
    Raises:
        argparse.ArgumentTypeError: If file doesn't exist or isn't readable
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("prompt file path cannot be empty")
    
    file_path = Path(value.strip()).expanduser()
    if not file_path.exists():
        raise argparse.ArgumentTypeError(f"prompt file does not exist: {file_path}")
    
    if not file_path.is_file():
        raise argparse.ArgumentTypeError(f"prompt file path is not a file: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Try to read first few bytes to check if it's readable
            f.read(100)
    except (PermissionError, UnicodeDecodeError) as e:
        raise argparse.ArgumentTypeError(f"cannot read prompt file {file_path}: {e}")
    
    return str(file_path)


def create_parser(config: Config) -> argparse.ArgumentParser:
    """Create and configure the argument parser.
    
    Args:
        config: Configuration instance for defaults
        
    Returns:
        Configured argument parser
    """
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
        metavar='COMMIT',
        help='Review changes since a specific commit'
    )
    parser.add_argument(
        '--max-lines',
        type=validate_max_lines,
        default=config.max_single_file_lines,
        metavar='N',
        help=f'Maximum lines for single file review (default: {config.max_single_file_lines})'
    )
    parser.add_argument(
        '--model',
        type=validate_model_name,
        default=config.default_model,
        metavar='PROVIDER/MODEL',
        help=f'Model to use for code review (default: {config.default_model})'
    )
    parser.add_argument(
        '--prompt-file',
        type=validate_prompt_file,
        default=None,
        metavar='FILE',
        help='Specific prompt file to use for this run'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode with verbose logging'
    )
    return parser


def review_single_file(filepath: str, max_lines: int) -> str:
    """Review a single file and return its content.
    
    Args:
        filepath: Path to file to review
        max_lines: Maximum lines allowed before user confirmation
        
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
        response = input(f"⚠️  File has {line_count} lines (max: {max_lines}). Continue? [y/N]: ")
        if response.lower() != 'y':
            raise UserCancelledError("Review cancelled by user")
    
    return content


def review_git_changes(git: GitHelper, config: Config, since_commit: Optional[str] = None, logger: Optional[logging.Logger] = None) -> str:
    """Review git changes and return diff content.
    
    Args:
        git: GitHelper instance
        config: Configuration instance
        since_commit: Compare against this commit (optional)
        logger: Logger for info messages
        
    Returns:
        Git diff content as string
        
    Raises:
        FileError: If no files found
        UserCancelledError: If user cancels the review
        GitError: If git operations fail
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        
    diff_mode = "uncommitted"
    changed_files = git.get_changed_files(since_commit)

    if not changed_files:
        diff_mode = "last-commit"
        changed_files = git.get_last_commit_files()

    if not changed_files:
        raise FileError("Couldn't find any changed files")

    logger.info(f"Found {len(changed_files)} changed file(s): {', '.join(changed_files)}")

    # Get diff content and check size
    diff_content = git.get_diff_content(changed_files, diff_mode)
    if diff_content:
        diff_lines = count_lines(diff_content)
        if diff_lines > config.max_total_diff_lines:
            response = input(f"⚠️  Large diff detected ({diff_lines} lines). Continue with full diff review? [y/N]: ")
            if response.lower() != 'y':
                raise UserCancelledError("Consider reviewing files one at a time with: cr <filename>")
    
    return diff_content


def display_review(review: str, config: Config) -> None:
    """Display the review using glow if available, otherwise plain text.
    
    Args:
        review: Review content to display
        config: Configuration containing glow style settings
    """
    print("\n" + "="*60)
    
    # Check if review content exists
    if not review or not review.strip():
        print("⚠️  No review content received from LLM")
        print("="*60)
        return
    
    # Try to use glow for better formatting
    if shutil.which('glow'):
        try:
            result = subprocess.run(
                ['glow', '-s', config.glow_style], 
                input=review.encode('utf-8'),
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout:
                print(result.stdout.decode('utf-8'))
            else:
                # Fallback to plain text if glow fails
                print(review)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # Fallback to plain text if glow has issues
            print(review)
    else:
        print(review)
    
    print("="*60)


def main() -> None:
    """Main entry point for the code reviewer.
    
    Raises:
        SystemExit: On configuration errors, git errors, or LLM errors
    """
    # Parse arguments first to get debug flag
    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument('--debug', action='store_true')
    temp_args, _ = temp_parser.parse_known_args()
    
    # Setup logging based on debug flag
    logger = setup_logging(temp_args.debug)
    logger.debug("Starting code reviewer application")
    
    try:
        config = Config.from_env()
        logger.debug(f"Configuration loaded: {config}")
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
        
    git = GitHelper(config, logger)
    reviewer = CodeReviewer(config, logger)
    
    parser = create_parser(config)
    args = parser.parse_args()
    logger.debug(f"Arguments parsed: {args}")

    # Check if we're in a git repository
    try:
        git.check_git_repo()
    except GitError as e:
        logger.error(f"Git repository check failed: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)

    # Get review from LLM
    try:
        if args.file:
            logger.info(f"Starting single file review: {args.file}")
            review = reviewer.review_file(args.file, args.max_lines, args.model, args.prompt_file, args.debug)
        else:
            logger.debug("Starting git changes review")
            review = reviewer.review_changes(git, args.since_commit, args.model, args.prompt_file, args.debug)
    except (FileError, LLMError, GitError) as e:
        logger.error(f"Review failed: {e}")
        print(f"❌ {e}")
        sys.exit(1)
    except UserCancelledError as e:
        logger.info(f"Review cancelled: {e}")
        print(str(e))
        sys.exit(0)

    # Display results
    logger.debug("Displaying review results")
    display_review(review, config)


if __name__ == "__main__":
    main()
