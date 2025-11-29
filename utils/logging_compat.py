import sys
import os
import io

def ensure_utf8_stdio():
    """Make stdout/stderr use UTF-8 encoding where possible.

    This helps avoid UnicodeEncodeError on Windows consoles that use cp1252
    when the code prints non-ASCII characters (e.g. checkmarks).

    We try a couple of fallbacks so this is safe on older/newer Python runtimes.
    """
    # Preferred: reconfigure if available (Python 3.7+)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        return True
    except Exception:
        pass

    # Try to force via PYTHONIOENCODING for subprocesses that might be spawned
    try:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    except Exception:
        pass

    # Attempt to detach existing text buffers and wrap with UTF-8
    try:
        if hasattr(sys.stdout, "detach"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.detach(),
                encoding="utf-8",
                errors="replace",
                line_buffering=True
            )
        if hasattr(sys.stderr, "detach"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.detach(),
                encoding="utf-8",
                errors="replace",
                line_buffering=True
            )
        return True
    except Exception:
        pass

    # Windows-specific fallback: reopen streams with UTF-8 encoding
    try:
        if os.name == "nt":
            import msvcrt
            for handle in (sys.stdout, sys.stderr):
                fileno = handle.fileno()
                msvcrt.setmode(fileno, os.O_BINARY)
            sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
            sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
            return True
    except Exception:
        pass

    # As last resort, wrap the file descriptors (best effort; may fail on some platforms)
    try:
        sys.stdout = io.TextIOWrapper(open(sys.stdout.fileno(), 'wb', 0), encoding='utf-8', line_buffering=True)
        sys.stderr = io.TextIOWrapper(open(sys.stderr.fileno(), 'wb', 0), encoding='utf-8', line_buffering=True)
        return True
    except Exception:
        return False
