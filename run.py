import sys
import os
import asyncio

# Add 'src' to sys.path to allow imports like 'from iron_business_hostess...'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from iron_business_hostess.main import main

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
