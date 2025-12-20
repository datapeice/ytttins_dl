import logging
from config import LOG_DIR

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_DIR / 'bot.log'),
            logging.StreamHandler()
        ]
    )

    # Create logger for user downloads
    download_logger = logging.getLogger('download_tracker')
    download_logger.setLevel(logging.INFO)
    download_handler = logging.FileHandler(LOG_DIR / 'downloads.log')
    download_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    download_logger.addHandler(download_handler)
    
    return download_logger

download_logger = setup_logging()
