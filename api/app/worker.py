"""Background worker for async tasks"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def worker_main():
    """Main worker loop"""
    logger.info("Worker started")
    
    while True:
        # TODO: Implement actual worker tasks (aggregations, Stripe sync)
        logger.info("Worker tick...")
        await asyncio.sleep(3600)  # Run every hour


if __name__ == "__main__":
    asyncio.run(worker_main())
