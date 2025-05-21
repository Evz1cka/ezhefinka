import os
from os import getenv

from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN=os.getenv("BOT_TOKEN")
DB_URL=os.getenv("DB_URL")
ADMIN_ID = int(getenv("ADMIN_ID"))
db_user=os.getenv("DB_USER"),
db_password=os.getenv("DB_PASSWORD"),
database=os.getenv("DB_NAME"),
host=os.getenv("DB_HOST")