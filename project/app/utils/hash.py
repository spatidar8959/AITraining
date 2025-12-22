"""
Hash utilities for file integrity and duplicate detection
"""
import hashlib
from typing import BinaryIO


def calculate_md5_hash(file_path: str, chunk_size: int = 8192) -> str:
    """
    Calculate MD5 hash of a file in chunks to handle large files efficiently.

    Args:
        file_path: Path to the file
        chunk_size: Size of chunks to read (default 8KB)

    Returns:
        MD5 hash as hexadecimal string (32 characters)

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    md5_hash = hashlib.md5()

    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                md5_hash.update(chunk)

        return md5_hash.hexdigest()

    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise IOError(f"Error reading file {file_path}: {str(e)}")


def calculate_md5_from_stream(file_stream: BinaryIO, chunk_size: int = 8192) -> str:
    """
    Calculate MD5 hash from a file stream (useful for uploaded files).

    Args:
        file_stream: Binary file stream
        chunk_size: Size of chunks to read (default 8KB)

    Returns:
        MD5 hash as hexadecimal string (32 characters)
    """
    md5_hash = hashlib.md5()

    # Reset stream position to beginning
    file_stream.seek(0)

    while True:
        chunk = file_stream.read(chunk_size)
        if not chunk:
            break
        md5_hash.update(chunk)

    # Reset stream position again for subsequent reads
    file_stream.seek(0)

    return md5_hash.hexdigest()
