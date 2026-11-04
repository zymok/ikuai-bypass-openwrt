#!/usr/bin/python3
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'ikuai-bypass-python'))
from ikb_subscription_guard import run

os.umask(0o077)
try:
    sys.exit(run(sys.argv[1], sys.argv[2:]))
except ValueError as error:
    print('[APPS/CONFIG:ERROR] ' + str(error), flush=True)
    sys.exit(1)
except Exception as error:
    print('[GUARD:ERROR] ' + type(error).__name__ + '; task stopped', flush=True)
    sys.exit(1)
