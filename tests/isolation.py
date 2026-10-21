"""Import first in every test module: point the host state at a throwaway directory so no
fixture run registers in the real `ai-toolkit` registry (FL-33). A state directory already
under the temp dir (the parallel runner's workers inherit one) is kept."""
import atexit
import os
from pathlib import Path
import shutil
import tempfile


def under_temp(value):
    if not value or not os.path.isabs(value):
        return False
    temp = os.path.realpath(tempfile.gettempdir())
    return Path(os.path.realpath(value)).is_relative_to(temp)


if not under_temp(os.environ.get('AI_STATE_DIR', '')):
    _state = tempfile.mkdtemp(prefix='ai-test-state-')
    _xdg = tempfile.mkdtemp(prefix='ai-test-xdg-')
    os.environ['AI_STATE_DIR'] = _state
    os.environ['XDG_STATE_HOME'] = _xdg
    atexit.register(shutil.rmtree, _state, ignore_errors=True)
    atexit.register(shutil.rmtree, _xdg, ignore_errors=True)
