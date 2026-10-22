"""Import first in every test module: point the host state at throwaway directories so no
fixture run registers in the real `ai-toolkit` registry (FL-33). `AI_STATE_DIR` and
`XDG_STATE_HOME` are each checked on their own: a value already under the temp dir (the
parallel runner's workers inherit both) is kept, otherwise it gets its own temp directory."""
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


for _var, _prefix in (('AI_STATE_DIR', 'ai-test-state-'), ('XDG_STATE_HOME', 'ai-test-xdg-')):
    if not under_temp(os.environ.get(_var, '')):
        _dir = tempfile.mkdtemp(prefix=_prefix)
        os.environ[_var] = _dir
        atexit.register(shutil.rmtree, _dir, ignore_errors=True)
