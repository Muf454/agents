"""Shared timeout scale for the test modules.

GitHub's runners are several times slower than a workstation and the workflow file is a gate file,
so the scale lives here instead of in the workflow: AI_TEST_TIMEOUT_SCALE when set (a float > 0),
else 2 when CI is `true`, else 1.
"""
import os


def timeout_scale(environ=None):
    environ = os.environ if environ is None else environ
    raw = environ.get('AI_TEST_TIMEOUT_SCALE')
    if raw is not None:
        try:
            scale = float(raw)
        except ValueError:
            scale = 0
        if not scale > 0 or scale == float('inf'):
            raise SystemExit(f'AI_TEST_TIMEOUT_SCALE must be a number greater than 0, got {raw!r}')
        return scale
    return 2.0 if environ.get('CI') == 'true' else 1.0


TIMEOUT_SCALE = timeout_scale()
