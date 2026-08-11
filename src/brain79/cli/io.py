import os
from pathlib import Path
import sys

MAX_INPUT_BYTES = 1_048_576  # 1MB


def read_input_field(
    file_path: str | Path | None,
    is_stdin: bool,
    field_name: str,
    max_bytes: int = MAX_INPUT_BYTES,
) -> str:
    """
    Read UTF-8 text strictly from a file path or sys.stdin with a fail-fast 1MB size limit.

    Args:
        file_path: Optional path to a file to read.
        is_stdin: Whether to read from sys.stdin.
        field_name: Name of the field for error reporting.
        max_bytes: Maximum allowed size in bytes (default 1MB).

    Returns:
        str: Cleaned UTF-8 string content.

    Raises:
        FileNotFoundError: If file_path is specified but does not exist.
        ValueError: If input size exceeds max_bytes or encoding is not valid UTF-8.
    """
    if file_path:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File for '{field_name}' not found: {file_path}")
        st = p.stat()
        if st.st_size > max_bytes:
            raise ValueError(
                f"Input for '{field_name}' exceeds maximum allowed size of 1MB ({st.st_size} bytes)"
            )
        raw_bytes = p.read_bytes()

        try:
            return raw_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Input for '{field_name}' contains invalid UTF-8 encoding: {exc}"
            ) from exc

    if is_stdin:
        try:
            st = os.fstat(sys.stdin.fileno())
            if st.st_size > max_bytes:
                raise ValueError(
                    f"Input for '{field_name}' from stdin exceeds maximum allowed size of 1MB ({st.st_size} bytes)"
                )
        except (OSError, AttributeError):
            pass

        raw_bytes = sys.stdin.buffer.read(max_bytes + 1)
        if len(raw_bytes) > max_bytes:
            raise ValueError(
                f"Input for '{field_name}' from stdin exceeds 1MB limit."
            )
        try:
            return raw_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Input for '{field_name}' contains invalid UTF-8 encoding: {exc}"
            ) from exc

    return ""
