# Utility functions for formatting time data and driver names

def format_lap_time(time_seconds):
    """
    Format lap time from seconds to a readable string format.
    
    Args:
        time_seconds (float): Lap time in seconds
        
    Returns:
        str: Formatted lap time as "M:SS.sss" or "N/A" if time is invalid
    """
    if time_seconds <= 0:
        return "N/A"
    minutes = int(time_seconds // 60)
    seconds = time_seconds % 60
    return f"{minutes}:{seconds:06.3f}"

def format_time_difference(seconds):
    """
    Format time difference for interval and gap display.
    
    Args:
        seconds (float): Time difference in seconds
        
    Returns:
        str: Formatted time difference as "+SS.sss" or "+M:SS.sss" for times over a minute
    """
    if seconds < 60:
        return f"+{seconds:.3f}s"
    else:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"+{minutes}:{remaining_seconds:06.3f}"

def format_driver_name(full_name, format_type="full"):
    """
    Format driver name according to specified format.
    
    Args:
        full_name (str): Full driver name
        format_type (str): Format type - "initial_last" (I.Apellido), "three_letters" (3 letters like F1), or "full" (full name)
        
    Returns:
        str: Formatted driver name
    """
    if not full_name:
        return "Unknown"
        
    # Handle case where there's no space in the name
    if " " not in full_name:
        if format_type == "initial_last":
            return f"{full_name[0]}.{full_name[1:]}" if len(full_name) > 1 else full_name
        elif format_type == "three_letters":
            return full_name[:3].upper() if len(full_name) >= 3 else full_name.upper()
        else:  # full name
            return full_name
    
    # Split the name into parts
    name_parts = full_name.split()
    
    if format_type == "initial_last":
        # First initial + last name (I.Apellido)
        # Skip trailing single-letter parts (e.g. "Ivan Serrano G" → "Serrano", not "G")
        first_initial = name_parts[0][0]
        last_name = next((p for p in reversed(name_parts[1:]) if len(p) > 1), name_parts[-1])
        return f"{first_initial}.{last_name}"

    elif format_type == "three_letters":
        # 3 letters like F1 (typically first 3 letters of last name)
        # Skip trailing single-letter parts for same reason
        last_name = next((p for p in reversed(name_parts) if len(p) > 1), name_parts[-1])
        return last_name[:3].upper()
        
    else:  # full name
        return full_name
