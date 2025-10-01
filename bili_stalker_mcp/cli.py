
import logging

logger = logging.getLogger(__name__)

def main():
    """Provides guidance on how to run the server in the new Smithery framework."""
    print("Server startup has been refactored to comply with the Smithery framework.")
    print("Please use one of the following commands:")
    print("  - To run a local development server: uv run dev")
    print("  - To test with the Smithery Playground: uv run playground")

if __name__ == "__main__":
    main()
