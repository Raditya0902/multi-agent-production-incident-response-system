#!/usr/bin/env python3
"""
Entrypoint for Docker sandbox execution.
Runs pytest on /app/test_fix.py and exits with the pytest return code.
Mount test files into /app before running this container.
"""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "/app/test_fix.py", "-v", "--tb=short"],
    capture_output=False,
)
sys.exit(result.returncode)
