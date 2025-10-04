# 1. Builder Stage: Install dependencies
FROM python:3.12-slim as builder

# Install uv
RUN pip install uv

WORKDIR /app

# Create a virtual environment
RUN uv venv

# Copy dependency definitions and README
COPY pyproject.toml uv.lock README.md ./

# Install dependencies into the virtual environment
# This includes the 'smithery' CLI
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

# The port the container will listen on. Smithery will set this.
EXPOSE 8080
ENV PORT=8080

# The command to run the application using our HTTP server script
CMD ["python", "-m", "bili_stalker_mcp.start_http"]
