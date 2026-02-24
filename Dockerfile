# 1. Builder Stage: Install dependencies
FROM python:3.12-slim AS builder

# Install uv
RUN pip install uv

WORKDIR /app

# Create a virtual environment
RUN uv venv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY ./bili_stalker_mcp ./bili_stalker_mcp

# Install dependencies and the project itself into the virtual environment
RUN . .venv/bin/activate && uv sync --no-dev

# 2. Final Stage: Setup the runtime environment
FROM python:3.12-slim

WORKDIR /app

# Copy the virtual environment with all dependencies from the builder stage
COPY --from=builder /app/.venv ./.venv

# Copy the application source code
COPY ./bili_stalker_mcp ./bili_stalker_mcp

# Set the PATH to include the virtual environment's binaries
# This ensures that 'python' and any installed CLIs are found
ENV PATH="/app/.venv/bin:$PATH"

# Default command: run the MCP server via CLI
CMD ["bili-stalker-mcp"]
