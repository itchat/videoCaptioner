import os

def ensure_directory_exists(directory):
    """If the directory does not exist, please create it."""
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_safe_filename(filename):
    """Getting a Safe File Name"""
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in (' ','-','_')]).rstrip()