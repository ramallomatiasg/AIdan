# run_janitor.py
import time
from janitor import main

if __name__ == '__main__':
    while True:
        main.clean_old_data()
        time.sleep(3600)  # Run every hour
