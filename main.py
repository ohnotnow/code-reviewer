#!/usr/bin/env python3
"""
Code Review CLI Tool - A friendly code reviewer powered by an LLM.

This tool analyzes code files or git changes and provides structured feedback
using an LLM. It supports single file reviews and git diff analysis with
customizable prompts and models.
"""

import argparse
import logging
import sys

from code_reviewer.cli import create_parser
from code_reviewer.config import Config
from code_reviewer.display import display_review
from code_reviewer.exceptions import FileError, LLMError, GitError, UserCancelledError
from code_reviewer.git_helper import GitHelper
from code_reviewer.review_engine import CodeReviewer
from code_reviewer.review_operations import review_single_file, review_git_changes


# Loggers to suppress in non-debug mode
SUPPRESSED_LOGGERS = ['LiteLLM', 'httpx']


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
    
    # Create a custom formatter for more readable timestamps
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%B %d, %I:%M%p'  # Removed %-I for Windows compatibility
    )
    handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True  # Allow reconfiguration
    )
    
    # Suppress noisy third-party loggers unless in debug mode
    if not debug:
        for logger_name in SUPPRESSED_LOGGERS:
            logging.getLogger(logger_name).setLevel(logging.ERROR)
    
    return logging.getLogger('codereviewer')


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
        logger.error(f"Configuration error: {e}")
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
        sys.exit(1)

    # Get review from LLM
    try:
        if args.file:
            logger.info(f"Starting single file review: {args.file}")
            content = review_single_file(args.file, args.max_lines, args.yes)
            review = reviewer.get_review(content, args.model, args.prompt_file, args.debug)
        else:
            # Determine which since argument to use - prioritize explicit since_commit
            if args.since_commit:
                since_time = None
                since_commit = args.since_commit
            else:
                since_time = args.since
                since_commit = None
            
            content = review_git_changes(git, config, since_commit, since_time, args.yes, logger)
            
            # Check if we're in summary mode
            if hasattr(args, 'summary') and args.summary is not None:
                logger.debug("Starting work summary generation")
                # Use summary prompt and add user context if provided
                summary_prompt_file = config.get_summary_prompt_file()
                user_context = args.summary.strip() if args.summary else ""
                if user_context:
                    content = f"User context: {user_context}\n\n{content}"
                review = reviewer.get_review(content, args.model, summary_prompt_file, args.debug)
            else:
                logger.debug("Starting git changes review")
                review = reviewer.get_review(content, args.model, args.prompt_file, args.debug)
    except (FileError, LLMError, GitError) as e:
        logger.error(f"Review failed: {e}")
        sys.exit(1)
    except UserCancelledError as e:
        logger.info(f"Review cancelled: {e}")
        sys.exit(0)

    # Display results
    logger.debug("Displaying review results")
    display_review(review, config, logger)


if __name__ == "__main__":
    main()
