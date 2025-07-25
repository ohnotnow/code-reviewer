"""
Custom exception classes for the code reviewer.
"""


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