from __future__ import annotations

import ast
import os
import sys
import warnings
from pathlib import Path

import pytest

# Suppress warnings early, before any imports that might trigger them
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*Monkey.*patch.*")
warnings.filterwarnings("ignore", message=".*gevent.*")

# Disable langsmith auto-upload to avoid recursion errors with connection pools
# This prevents "error uploading: maximum recursion depth exceeded" errors
# Set these BEFORE any imports that might trigger langsmith plugin loading
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_ENDPOINT", "")
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGSMITH_ENABLED", "false")
os.environ.setdefault("LANGCHAIN_API_KEY", "")  # Empty API key disables tracing

# Try to prevent langsmith plugin from being loaded
try:
    # Mock langsmith pytest plugin before it's imported
    if "pytest_langsmith" not in sys.modules:
        from unittest.mock import MagicMock
        sys.modules["pytest_langsmith"] = MagicMock()
except Exception:
    pass  # Ignore if mocking fails

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

collect_ignore = ["test_performance_locust.py"]

# Files that import dify_plugin or tools that use dify_plugin
# These will be automatically marked with @pytest.mark.dify_plugin
# Note: AST parsing should detect most cases automatically, this is a fallback
# Updated paths after migration to subdirectories
_DIFY_PLUGIN_TEST_FILES = {
    "test_extraction_async.py",  # unit/tools/
    "test_token_truncation.py",  # unit/tools/
    "test_extraction_parameters.py",  # unit/tools/
    "test_extract_long_term_memory.py",  # unit/tools/
    "test_e2e_session_memory.py",  # e2e/
}


def _file_imports_dify_plugin(file_path: Path) -> bool:
    """Check if a test file imports dify_plugin or tools that use it.
    
    This checks for:
    - Direct imports of dify_plugin
    - Imports of tools.extract_long_term_memory (which imports dify_plugin.Tool)
    - Imports of tools.check_extraction_status (which may import dify_plugin)
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                # Check direct imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "dify_plugin" in alias.name:
                            return True
                # Check from imports
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        if "dify_plugin" in node.module:
                            return True
                        # Check for tools that import dify_plugin
                        if node.module in (
                            "tools.extract_long_term_memory",
                            "tools.check_extraction_status",
                        ):
                            return True
    except (SyntaxError, UnicodeDecodeError):
        # If we can't parse the file, fall back to filename check
        pass
    
    # Fallback: check filename
    return file_path.name in _DIFY_PLUGIN_TEST_FILES


def pytest_configure(config):
    """Configure pytest markers for tests that import dify_plugin.
    
    Tests that import dify_plugin may trigger gevent monkey patching,
    which can conflict with pytest if standard library modules (like ssl)
    have already been imported. Use the 'dify_plugin' marker to identify
    such tests, and run them with fork isolation:
    
        pytest -n auto --forked -m dify_plugin
    
    See GEVENT_MONKEY_PATCHING_ANALYSIS.md for detailed explanation.
    """
    config.addinivalue_line(
        "markers",
        (
            "dify_plugin: tests that import dify_plugin "
            "(requires fork isolation to avoid gevent monkey patching conflicts)"
        ),
    )
    
    # Suppress MonkeyPatchWarning from gevent
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="gevent")
    warnings.filterwarnings(
        "ignore",
        message=".*Monkey.*patch.*",
        category=UserWarning,
    )
    
    # Try to disable langsmith plugin to avoid upload recursion errors
    try:
        # Unregister langsmith plugin if it exists
        plugin_manager = config.pluginmanager
        langsmith_plugins = [
            name for name in plugin_manager.list_name_plugin()
            if "langsmith" in name.lower()
        ]
        for plugin_name in langsmith_plugins:
            try:
                plugin_manager.unregister(name=plugin_name)
            except (ValueError, KeyError):
                pass  # Plugin may not be registered or already unregistered
    except Exception:
        pass  # Ignore errors during plugin unregistration


def pytest_report_header(config, start_path):
    """Suppress the default pytest session header (platform, Python version, etc.)."""
    # Return empty list to suppress header output
    return []


def pytest_load_initial_conftests(early_config, parser, args):
    """Early hook to suppress warnings before collection starts."""
    import warnings
    # Suppress all UserWarnings, especially MonkeyPatchWarning
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", message=".*Monkey.*patch.*")
    warnings.filterwarnings("ignore", message=".*gevent.*")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests that import dify_plugin.
    
    This function scans test files and automatically marks them with
    @pytest.mark.dify_plugin if they import dify_plugin or tools that use it.
    """
    for item in items:
        # Get the test file path
        test_file = Path(item.fspath) if hasattr(item, "fspath") else None
        if test_file and _file_imports_dify_plugin(test_file):
            # Add the marker if not already present
            if not any(marker.name == "dify_plugin" for marker in item.iter_markers()):
                item.add_marker(pytest.mark.dify_plugin)


# Suppress langsmith upload errors and pytest session headers by filtering stderr/stdout
_original_stderr = sys.stderr
_original_stdout = sys.stdout

class OutputFilter:
    """Filter to suppress unwanted output: langsmith errors, pytest headers, and warnings."""
    
    def __init__(self, original, stream_name="stderr"):
        self.original = original
        self.stream_name = stream_name
        self._buffer = ""
        # Patterns to suppress
        self.suppress_patterns = [
            "test session starts",
            "platform ",
            "Python ",
            "pytest-",
            "pluggy-",
            "cachedir:",
            "rootdir:",
            "configfile:",
            "plugins:",
            "collecting ...",
            "MonkeyPatchWarning",
            "Monkey-patching",
            "gevent",
        ]
    
    def write(self, text):
        # Buffer text to check for multi-line messages
        self._buffer += text
        
        # Check for langsmith upload errors
        buffer_lower = self._buffer.lower()
        has_upload_error = "error uploading" in buffer_lower
        has_recursion_error = "maximum recursion depth" in buffer_lower
        if has_upload_error and has_recursion_error:
            self._buffer = ""
            return len(text)  # Suppress
        
        # Check for patterns to suppress
        buffer_lower = self._buffer.lower()
        for pattern in self.suppress_patterns:
            if pattern.lower() in buffer_lower:
                # Suppress lines containing these patterns
                if "\n" in text or len(self._buffer) > 500:
                    self._buffer = ""
                    return len(text)  # Suppress
        
        # If buffer is getting too large or we see a newline, flush it
        if len(self._buffer) > 500 or "\n" in text:
            # Only write if it doesn't contain suppress patterns
            should_suppress = False
            for pattern in self.suppress_patterns:
                if pattern.lower() in self._buffer.lower():
                    should_suppress = True
                    break
            
            if not should_suppress:
                result = self.original.write(self._buffer)
            else:
                result = len(self._buffer)  # Suppress but return length
            
            self._buffer = ""
            return result
        
        return len(text)
    
    def flush(self):
        if self._buffer:
            # Check buffer one more time before flushing
            buffer_lower = self._buffer.lower()
            
            # Check for langsmith errors
            has_upload_error = "error uploading" in buffer_lower
            has_recursion_error = "maximum recursion depth" in buffer_lower
            if has_upload_error and has_recursion_error:
                self._buffer = ""
                return self.original.flush()
            
            # Check for suppress patterns
            should_suppress = False
            for pattern in self.suppress_patterns:
                if pattern.lower() in buffer_lower:
                    should_suppress = True
                    break
            
            if not should_suppress:
                self.original.write(self._buffer)
            self._buffer = ""
        return self.original.flush()
    
    def __getattr__(self, name):
        return getattr(self.original, name)

# Install the filter early, before pytest plugins load
if not isinstance(sys.stderr, OutputFilter):
    sys.stderr = OutputFilter(_original_stderr, "stderr")
if not isinstance(sys.stdout, OutputFilter):
    sys.stdout = OutputFilter(_original_stdout, "stdout")
