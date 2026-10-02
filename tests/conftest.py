"""pytest support for the script-style tests.

Many test functions here count failed checks and return the count instead of
raising; they are written to be run as scripts (see run_tests.sh). Plain pytest
ignores return values, so a test with failed checks would be reported as
passed. This hook fails such a test instead.
"""
import inspect

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    function = pyfuncitem.obj
    if inspect.iscoroutinefunction(function):
        return None                       # leave async tests to their plugin
    names = pyfuncitem._fixtureinfo.argnames
    result = function(**{n: pyfuncitem.funcargs[n] for n in names})
    if isinstance(result, int) and not isinstance(result, bool) and result:
        pytest.fail(f"{result} check(s) failed", pytrace=False)
    return True
