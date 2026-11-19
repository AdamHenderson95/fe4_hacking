#!/usr/bin/env python3
"""Make a TEST copy of a built ROM whose New Game opens straight on a chapter (kept for old notes;
the code is in fe4teststart.py, which the editor's "Test this chapter" uses too).

    python dev/ch6start.py myhack.smc test6.smc
    python dev/ch6start.py myhack.smc test9.smc --chapter 9
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import fe4teststart  # noqa: E402

if __name__ == '__main__':
    fe4teststart.main()
