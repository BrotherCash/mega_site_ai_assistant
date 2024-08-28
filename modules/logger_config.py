import logging
import sys


def setup_logging():
    logging.basicConfig(stream=sys.stdout, format='%(levelname)s:%(message)s', level=logging.INFO)
    logger = logging.getLogger(__name__)
    return logger
