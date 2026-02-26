# run_collector.py
import time
from collector import main

if __name__ == '__main__':
    while True:
        main.run()
        time.sleep(600)  # Run every 10 minutes
