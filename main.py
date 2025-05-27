import asyncio
import logging
import os
from dotenv import load_dotenv
from bot.core.bot_manager import BotManager


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():

    load_dotenv()
    

    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    try:

        bot_manager = BotManager()
        await bot_manager.start()

        logger.info("Bot is running. Press Ctrl+C to stop.")
        await bot_manager.bot.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bot_manager.stop()
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        if 'bot_manager' in locals():
            await bot_manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
