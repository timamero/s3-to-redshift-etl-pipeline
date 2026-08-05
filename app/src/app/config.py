from dotenv import dotenv_values
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s %(levelname)s:%(message)s", level=logging.INFO)

config = dotenv_values(".env")
