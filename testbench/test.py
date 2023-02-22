import os
import time
import logging
import subprocess
import threading
import sys
from functools import wraps

import custom_logging

# Logging setup
log = logging.getLogger(__name__)

# Test globals
TEST_ARRAY = []
TEST_FAILED = True
CLEANUP = []

class TestFunc:
    def __init__(self, wrapper, func_name, result=None):
        self.func_name = func_name
        self.wrapper = wrapper
        self.result = result

    def run(self, **kwargs):
        return self.wrapper(**kwargs)


def test(func):
    @wraps(func)
    def wrapper(*args, **kwds):
        try:
            func(*args, **kwds)
            return None
        except Exception as ex:
            return ex

    TEST_ARRAY.append(TestFunc(wrapper, func.__name__))
    return wrapper

def cleanup(func):
    @wraps(func)
    def wrapper(*args, **kwds):
        kwds["failure"] = TEST_FAILED
        iterator = func(*args, **kwds)
        CLEANUP.append(iterator)
        return next(iterator)
    return wrapper

def assertEqual(a,b, msg=None):
    if a != b:
        if msg is None:
            raise AssertionError(f"Expected equality is however: {a} != {b}")
        else:
            raise AssertionError(msg)
    else:
        return True



def main():
    import argparse
    import importlib

    parser = argparse.ArgumentParser(
                    prog = 'testbench',
                    description = 'Loads and executes tests')

    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-t", "--test", nargs="?", action="append", default=["test"])
    parser.add_argument("-bd", "--build_dir", action="store", type=argparse.FileType('r'), default="build")
    args = parser.parse_args()

    if args.verbose:
        custom_logging.register(logging.DEBUG)
    else:
        custom_logging.register(logging.INFO)

    build_dir = os.path.join(os.getcwd(), args.build_dir)
    if os.path.isdir(build_dir) is False:
        log.error(f"Build directory does not exist: {build_dir}")
        exit(1)

    # Import tests
    for test in args.test:
        log.info(f"Importing test: ./{test}.py")
        importlib.import_module("." + test)


    width, height = os.get_terminal_size()
    for test in TEST_ARRAY:
        filler = round((width - len(test.func_name)) / 2 -1)
        print("="*filler + f" {test.func_name} " + "="*filler)
        res = test.run(build_dir)
        if res is not None:
            log.exception("Test failed. Reason: ", exc_info=res)
            TEST_FAILED = True
        else:
            log.info("Test succeeded")
            TEST_FAILED = False
        for clean_func in CLEANUP:
            log.debug(f"Cleaning up function: {clean_func.__name__} ")
            try:
                res = next(clean_func)
                log.error(f"Cleanup function {clean_func.__name__} has a second yield. This is not allowed")
                log.error("Failed to cleanup. Zombie processes may be still alive")
            except StopIteration:
                pass

if __name__ == "__main__":
    main()