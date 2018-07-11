#!/usr/bin/env python3
import asyncio
import atexit
import os
import sys

from scpi.devices import hp6632b

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("run with python -i hp6632b.py /dev/ttyUSB0")
        sys.exit(1)
    # Then put to interactive mode
    os.environ['PYTHONINSPECT'] = '1'
    #dev = hp6632b.rs232(sys.argv[1], rtscts=True)
    dev = hp6632b.rs232(sys.argv[1], rtscts=False)
    loop = asyncio.get_event_loop()
    atexit.register(dev.quit)
    atexit.register(loop.close)
    print(loop.run_until_complete(dev.identify()))
    print("Remember to use loop.run_until_complete() since we are in asuncio land now")
