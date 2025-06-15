import sys
import os

# Добавляем путь к виртуальному окружению
INTERP = os.path.expanduser("/home/username/virtualenv/your_site/3.10/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Добавляем путь к директории проекта
sys.path.append(os.getcwd())

# Импортируем приложение
from app import app as application 