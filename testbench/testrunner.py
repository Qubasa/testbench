import os
import time
import logging
import subprocess
import threading
import sys
from functools import wraps
import traceback

try:
    import custom_logging
except (ImportError, ModuleNotFoundError):
    from . import custom_logging

# Logging setup
log = logging.getLogger(__name__)


class TestFailed(object):
    def __init__(self, failed):
        self._failed = failed
        self.lock = threading.RLock()

    @property
    def get_failed(self):
        self.lock.acquire()
        return self._failed
        self.lock.release()


    def set_failed(self, x):
        self.lock.acquire()
        self._failed = x
        self.lock.release()


# Test globals
TEST_ARRAY = []
TEST_FAILED = TestFailed(True)
CLEANUP = []

class TestFunc:
    def __init__(self, wrapper, func_name, result=None):
        self.func_name = func_name
        self.wrapper = wrapper
        self.result = result

    def run(self, **kwargs):
        return self.wrapper(**kwargs)


def test(func):
    global TEST_FAILED, CLEANUP, TEST_ARRAY

    @wraps(func)
    def wrapper(*args, **kwds):
        try:
            func(*args, **kwds)
            return None
        except TypeError as ex:
            log.fatal(f"Test function {func.__name__} signature needs a **kwarg argument.")
            return ex

        except Exception as ex:
            return ex

    TEST_ARRAY.append(TestFunc(wrapper, func.__name__))
    return wrapper

def cleanup(func):
    @wraps(func)
    def wrapper(*args, **kwds):
        global TEST_FAILED, CLEANUP, TEST_ARRAY
        kwds["failure"] = TEST_FAILED
        try:
            iterator = func(*args, **kwds)
        except TypeError as ex:
            log.fatal(f"Cleanup function {func.__name__} signature needs a **kwarg argument.")
            exit(1)
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
    global TEST_FAILED, CLEANUP, TEST_ARRAY

    import argparse
    import importlib
    import pathlib 

    parser = argparse.ArgumentParser(
                    prog = 'testbench',
                    description = 'Loads and executes tests')

    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-t", "--test", nargs="?", required=True, action="append")
    parser.add_argument("-bd", "--build_dir", action="store",  default="build")
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
    for test_path in args.test:
        sp = pathlib.Path(test_path)
        script_path = sp.with_suffix("").resolve()
        script_dir = script_path.parent
        sys.path.append("tests")

        test_stem = sp.stem
        log.info(f"Loading test: {test_stem}")
        try:
            mod = importlib.import_module(test_stem)
        except ModuleNotFoundError as ex:
            log.error(f"Couldn't find module: {test_stem}")
            log.error(f"Module search path is: {script_dir}")
            exit(1)
        finally:
            sys.path.pop()

    if len(TEST_ARRAY) == 0:
        log.error("No tests have been found!")
        exit(1)

    width, height = os.get_terminal_size()
    for test_stem in TEST_ARRAY:
        filler = round((width - len(test_stem.func_name)) / 2 -1)
        print("="*filler + f" {test_stem.func_name} " + "="*filler)

        # Test execution phase
        res = test_stem.run(build_dir=build_dir)
        if res is not None:
            log.exception("Test failed. Reason: ", exc_info=res)
            TEST_FAILED.set_failed(True)
        else:
            log.info("Test succeeded")
            TEST_FAILED.set_failed(False)

        # Cleanup phase
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