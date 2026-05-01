FROM python:3.11-slim

WORKDIR /app

# Pre-install pytest so runtime doesn't need internet access
RUN pip install pytest==8.0.0 --no-cache-dir

# Test files are volume-mounted at runtime — nothing to COPY here
CMD ["python", "-m", "pytest", "test_fix.py", "-v", "--tb=short"]
