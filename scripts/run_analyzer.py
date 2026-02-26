# run_analyzer.py
import time
from analyzer import main

if __name__ == '__main__':
    while True:
        main.run()
        time.sleep(120)  # Run every 2 minutes
