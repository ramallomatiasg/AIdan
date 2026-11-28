"""Baja los datos de P86-P88 a .cache_p86/.cache_p87/.cache_p88 (Yahoo ajustado). Solo descarga."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from fetch_p82_p84_cache import yahoo, show

if __name__ == '__main__':
    for s in ['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'SPY']:
        show('P86 ' + s, yahoo(s, '.cache_p86'))
    for s in ['VWEHX', 'VFITX', 'VFINX']:
        show('P87 ' + s, yahoo(s, '.cache_p87'))
    for s in ['^PUT', 'SPY']:
        show('P88 ' + s, yahoo(s, '.cache_p88'))
