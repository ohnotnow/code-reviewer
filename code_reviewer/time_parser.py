"""
Time parsing utilities for the code reviewer.
"""

import re
from datetime import datetime, timedelta
from typing import Optional


def parse_time_duration(time_str: str) -> datetime:
    """Parse a time duration string and return the corresponding datetime.
    
    Supports formats:
    - 'today' - midnight of current day
    - '1h', '2h' etc. - hours ago
    - '30m', '45m' etc. - minutes ago
    - '1d', '7d' etc. - days ago
    
    Args:
        time_str: Time duration string
        
    Returns:
        datetime object representing the target time
        
    Raises:
        ValueError: If time format is invalid
    """
    time_str = time_str.strip().lower()
    
    if time_str == 'today':
        # Return midnight of current day
        now = datetime.now()
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Parse relative time patterns like '1h', '30m', '2d'
    pattern = r'^(\d+)([hmd])$'
    match = re.match(pattern, time_str)
    
    if not match:
        raise ValueError(f"Invalid time format: '{time_str}'. Use formats like '1h', '30m', '2d', or 'today'")
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    now = datetime.now()
    
    if unit == 'h':
        return now - timedelta(hours=amount)
    elif unit == 'm':
        return now - timedelta(minutes=amount)
    elif unit == 'd':
        return now - timedelta(days=amount)
    
    # This should never be reached due to regex pattern
    raise ValueError(f"Invalid time unit: '{unit}'")


def datetime_to_git_format(dt: datetime) -> str:
    """Convert datetime to git-compatible format.
    
    Args:
        dt: datetime object
        
    Returns:
        Git-compatible date string
    """
    return dt.strftime('%Y-%m-%d %H:%M:%S')