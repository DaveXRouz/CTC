"""Entry point: python -m conductor"""

import asyncio
from conductor.main import run

if __name__ == "__main__":
    asyncio.run(run())
