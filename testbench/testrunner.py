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
DEBUG = False

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



def get_term_filler(name):
    width, height = os.get_terminal_size()
    filler = round((width - len(name)) / 2 -2)
    return filler

def main():
    global TEST_FAILED, CLEANUP, TEST_ARRAY, DEBUG

    import argparse
    import importlib
    import pathlib

    parser = argparse.ArgumentParser(
                    prog = 'testbench',
                    description = 'Loads and executes tests')

    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-t", "--test", nargs="?", required=True, action="append")
    parser.add_argument("-bd", "--build_dir", action="store",  default="build")
    parser.add_argument("-tf", "--test_func", nargs="?", action="append")
   # parser.add_argument("-d", "--debug", action="store_true")
    args = parser.parse_args()

   # DEBUG = args.debug

    if args.verbose:
        custom_logging.register(logging.DEBUG)
    else:
        custom_logging.register(logging.INFO)

    build_dir = os.path.join(os.getcwd(), args.build_dir)
    if os.path.isdir(build_dir) is False:
        log.error(f"Build directory does not exist: {build_dir}")
        exit(1)

    whitelist = set()
    if args.test_func is not None:
        for func in args.test_func:
            whitelist.add(func)

    # Import tests
    for test_path in args.test:
        sp = pathlib.Path(test_path)
        script_dir = sp.with_suffix("").resolve().parent.as_posix()
        sys.path.append(script_dir)

        test_stem = sp.stem
        log.info(f"Loading test: {test_stem}")
        try:
            mod = importlib.import_module(test_stem)
        except ModuleNotFoundError as ex:
            log.error(f"Module search path is: {script_dir}")
            log.error(f"Couldn't load module: {test_stem}", exc_info=ex)
            exit(1)
        finally:
            sys.path.pop()

    if len(TEST_ARRAY) == 0:
        log.error("No tests have been found!")
        exit(1)

    def run_cleanup():
        # Cleanup phase
        for clean_func in CLEANUP:
            log.debug(f"Cleaning up function: {clean_func.__name__} ")
            try:
                res = next(clean_func)
                log.error(f"Cleanup function {clean_func.__name__} has a second yield. This is not allowed")
                log.error("Failed to cleanup. Zombie processes may be still alive")
            except StopIteration:
                pass


    try:
        for i, test in enumerate(TEST_ARRAY):
            if test.func_name not in whitelist and len(whitelist) > 0:
                continue

            filler = get_term_filler(test.func_name)
            print("="*filler + f" {test.func_name} " + "="*filler)

            # Test execution phase
            res = test.run(build_dir=build_dir)
            if res is not None:
                log.exception("Test failed. Reason: ", exc_info=res)
                TEST_FAILED.set_failed(True)
            else:
                log.info("Test succeeded")
                TEST_FAILED.set_failed(False)

            # Run cleanup functions
            run_cleanup()

            # Skip wait if last test function
            if i != len(TEST_ARRAY)-1:
                time.sleep(1)
    except KeyboardInterrupt:
        while True:
            try:
                run_cleanup()
                exit(0)
            except KeyboardInterrupt:
                log.error("Please wait for the cleanup to finish")


if __name__ == "__main__":
    main()