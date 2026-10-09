"""Read-only pipeline dashboard: which checkouts run a pipeline, whether it is alive, and safe
terminal text. Nothing here writes a file: checkouts are read only through workflow.py's pinned,
bounded readers, processes only through a ProcSource (`/proc` or a test fixture tree)."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import unicodedata

# No __pycache__: .ai/bin is part of the approved gate digest.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow import (BOX_KEYS, DIR_FLAGS, NOTIFICATIONS_LIMIT, OBSERVATION_LIMIT,  # noqa: E402
                      OBSERVATION_STATES, SMALL_LIMIT, TASKS_LIMIT, checkout_fds, close_fds,
                      git_branch, read_record, state_root, task_blocks)
from watchdog import is_runner  # noqa: E402

PIPELINE_NAMES = ('ai-pipeline', 'ai-recover')
FROM_ENVIRONMENT = object()


class ProcSource:
    """Process facts in watchdog.py's semantics, read from ROOT (`AI_DASHBOARD_PROC`, test
    only, else `/proc`)."""

    def __init__(self, root=None):
        self.root = Path(root if root is not None else os.environ.get('AI_DASHBOARD_PROC', '/proc'))
        self.boot_ns = None

    def pids(self):
        try:
            return sorted((name for name in os.listdir(self.root) if name.isdigit()), key=int)
        except OSError:
            return []

    def process(self, pid):
        """(args, start ticks) of a live, non-zombie process, or None."""
        entry = self.root / str(pid)
        try:
            status = (entry / 'stat').read_bytes().rsplit(b')', 1)[1].split()
            args = (entry / 'cmdline').read_bytes().split(b'\0')
        except (OSError, IndexError):
            return None
        if len(status) < 20 or status[0] == b'Z' or not status[19].isdigit():
            return None
        return args, status[19].decode()

    def cwd(self, pid):
        try:
            return os.readlink(self.root / str(pid) / 'cwd')
        except OSError:
            return None

    def start_ns(self, ticks):
        """Process start (stat field 22, clock ticks since boot) as epoch ns."""
        if self.boot_ns is None:
            btime = re.search(rb'^btime (\d+)$', (self.root / 'stat').read_bytes(), re.M)
            self.boot_ns = int(btime[1]) * 1_000_000_000
        return self.boot_ns + int(ticks) * 1_000_000_000 // os.sysconf('SC_CLK_TCK')


def has_ai(checkout):
    """True for an absolute existing directory whose `.ai` is a real directory."""
    if not isinstance(checkout, str) or not os.path.isabs(checkout) or not os.path.isdir(checkout):
        return False
    fds = checkout_fds(checkout)
    if fds is None:
        return False
    close_fds(*fds)
    return True


def registered_checkouts():
    """Checkout paths named by `<state root>/pipelines/*.json`; unreadable entries skipped."""
    try:
        directory = os.open(state_root() / 'pipelines', DIR_FLAGS)
    except OSError:
        return []
    found = []
    try:
        for name in sorted(os.listdir(directory)):
            if name.startswith('.') or not name.endswith('.json'):
                continue
            record = read_record(directory, name, OBSERVATION_LIMIT)
            try:
                data = json.loads(record[0]) if record else None
            except ValueError:
                continue
            if isinstance(data, dict) and has_ai(data.get('checkout')):
                found.append(data['checkout'])
    except OSError:
        pass
    finally:
        close_fds(directory)
    return found


def inside(path, base):
    return os.path.commonpath([path, base]) == base


def discover(source=None, only_under=FROM_ENVIRONMENT):
    """[(checkout, [(pid, start ticks), ...])] for every registered checkout and every checkout
    a live runner works in, deduplicated by realpath; ONLY_UNDER (`AI_DASHBOARD_ROOT`, test
    only) keeps just the checkouts inside it."""
    source = source or ProcSource()
    if only_under is FROM_ENVIRONMENT:
        only_under = os.environ.get('AI_DASHBOARD_ROOT') or None
    base = os.path.realpath(only_under) if only_under else None
    checkouts = {}

    def add(checkout):
        real = os.path.realpath(checkout)
        if base and not inside(real, base):
            return None
        return checkouts.setdefault(real, (checkout, []))[1]

    for checkout in registered_checkouts():
        add(checkout)
    for pid in source.pids():
        found = source.process(pid)
        if not found or not is_runner(found[0]):
            continue
        cwd = source.cwd(pid)
        if not has_ai(cwd):
            continue
        runners = add(cwd)
        if runners is not None:
            runners.append((int(pid), found[1]))
    return sorted(checkouts.values())


def marker(local_fd):
    """(pid, mtime ns) of `.ai/local/pipeline.active` from one open, or None when it is absent
    or unreadable (a FIFO, a symlink, garbage)."""
    if local_fd is None:
        return None
    record = read_record(local_fd, 'pipeline.active', SMALL_LIMIT)
    if record is None:
        return None
    try:
        return int(record[0].split()[0]), record[1].st_mtime_ns
    except (ValueError, IndexError):
        return None


def liveness(local_fd, runners, source=None):
    """`alive`, `crashed` or `gone`, with watchdog.py's pipeline_died semantics."""
    source = source or ProcSource()
    snapshot = marker(local_fd)
    for _ in range(3):
        if snapshot is None:
            break
        pid, written = snapshot
        found = source.process(pid)
        # A reused PID started after the marker; ai-recover replaces the pipeline (same PID).
        if found and is_runner(found[0], PIPELINE_NAMES) \
                and source.start_ns(found[1]) <= written + 1_000_000_000:
            return 'alive'
        # A run that just finished removes its marker; only an unchanged marker is a crash.
        again = marker(local_fd)
        if again == snapshot:
            return 'crashed'
        snapshot = again
    # No marker: versions without pipeline.active are alive while a runner works there.
    return 'alive' if runners else 'gone'


ESCAPE = re.compile(r'''
      (?:\x1b\]|\x9d) .*? (?:\x07|\x1b\\|\x9c|\Z)               # OSC (BEL or ST)
    | (?:\x1b[P^_X]|[\x90\x98\x9e\x9f]) .*? (?:\x1b\\|\x9c|\Z)  # DCS, PM, APC, SOS
    | (?:\x1b\[|\x9b) [0-?]* [ -/]* [@-~]?                      # CSI, 7- and 8-bit
    | \x1b [ -/]* [0-~]?                                         # other escapes, bare ESC
''', re.S | re.X)
CONTROL = re.compile('[\x00-\x08\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩]')


def sanitize(text, limit=200):
    """TEXT safe to print: no escape sequences, controls or bidi overrides, whitespace
    collapsed, at most LIMIT characters."""
    text = CONTROL.sub('', ESCAPE.sub('', str(text or '')))
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


STAGES = (*BOX_KEYS, 'none')
EVENT_COUNT = 20
HIDE_AFTER = 24 * 3600
RANK = {'needs_you': 0, 'crashed': 1, 'running': 2, 'paused': 2, 'recovering': 2, 'finished': 3,
        'idle': 4, 'unknown': 5}


def text_field(value, limit=200):
    return sanitize(value, limit) if isinstance(value, str) else ''


def observation_of(local_fd, seen):
    """The validated observation record, or None (absent, malformed, unknown stage or state)."""
    record = read_record(local_fd, 'observation.json', OBSERVATION_LIMIT) if local_fd is not None else None
    if record is None:
        return None
    seen.append(record[1].st_mtime)
    try:
        data = json.loads(record[0])
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get('stage') not in STAGES \
            or data.get('state') not in OBSERVATION_STATES:
        return None
    return {'stage': data['stage'], 'state': data['state'], 'detail': text_field(data.get('detail')),
            'note': text_field(data.get('note'), 400), 'since': text_field(data.get('since'), 40)}


def events_of(local_fd, seen):
    """The last EVENT_COUNT notification lines as {'ts', 'message'}; malformed lines skipped."""
    record = read_record(local_fd, 'notifications.log', NOTIFICATIONS_LIMIT, tail=True) \
        if local_fd is not None else None
    if record is None:
        return []
    seen.append(record[1].st_mtime)
    events = []
    for line in record[0].splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get('message'), str):
            events.append({'ts': text_field(data.get('ts'), 40), 'message': text_field(data['message'], 300)})
    return events[-EVENT_COUNT:]


def tasks_of(ai_fd, seen):
    """{'done', 'total', 'current'} counted like `tasks counts` (DONE over all blocks), or None."""
    record = read_record(ai_fd, 'tasks.md', TASKS_LIMIT)
    if record is None:
        return None
    seen.append(record[1].st_mtime)
    try:
        blocks = task_blocks(record[0])
    except (SystemExit, Exception):
        return None
    current = next((block['title'] for block in blocks if 'Status: IN_PROGRESS' in block['lines']), '')
    return {'done': sum('Status: DONE' in block['lines'] for block in blocks), 'total': len(blocks),
            'current': text_field(current, 120)}


def inspect(checkout, runners, now, source=None):
    """One checkout as a plain dict; every checkout-derived string is sanitised. A checkout whose
    records cannot be read safely comes back with status `unknown`."""
    run = {'project': text_field(os.path.basename(checkout.rstrip('/')) or checkout, 80),
           'checkout': text_field(checkout, 300), 'branch': 'unknown', 'liveness': 'gone',
           'observation': None, 'events': [], 'last_error': '', 'tasks': None, 'status': 'unknown',
           'stage': 'unknown', 'since': '', 'updated': 0.0}
    fds = checkout_fds(checkout)
    if fds is None:
        return run
    root_fd, ai_fd, local_fd = fds
    try:
        seen = []
        run['branch'] = text_field(git_branch(root_fd) or 'unknown', 120)
        run['liveness'] = liveness(local_fd, runners, source)
        observation = observation_of(local_fd, seen)
        observed = seen[0] if observation else 0.0
        run['observation'] = observation
        run['events'] = events_of(local_fd, seen)
        run['tasks'] = tasks_of(ai_fd, seen)
        error = read_record(local_fd, 'last-error', SMALL_LIMIT) if local_fd is not None else None
        errored = bool(error and error[1].st_mtime > observed)
        if error:
            seen.append(error[1].st_mtime)
        if errored:
            run['last_error'] = text_field((error[0].strip().splitlines() or [''])[0], 300)
        state = observation['state'] if observation else None
        if run['liveness'] == 'crashed':
            status = 'crashed'
        elif run['liveness'] == 'alive':
            status = state if state in ('paused', 'recovering') else 'running'
        elif state == 'stopped' or errored:
            status = 'needs_you'
        elif state == 'done':
            status = 'finished'
        else:
            status = 'idle'
        run.update(status=status, stage=observation['stage'] if observation else 'unknown',
                   since=observation['since'] if observation else '', updated=max(seen, default=0.0))
        return run
    finally:
        close_fds(root_fd, ai_fd, local_fd)


def snapshot(all_runs=False, now=None, source=None):
    """{'state_root', 'runs'}: needs_you, crashed, live, finished, idle, then newest first. Old
    (> 24 h) finished and idle runs are hidden unless ALL_RUNS."""
    now = time.time() if now is None else now
    source = source or ProcSource()
    runs = [inspect(checkout, runners, now, source) for checkout, runners in discover(source)]
    if not all_runs:
        runs = [run for run in runs
                if run['status'] not in ('finished', 'idle') or now - run['updated'] <= HIDE_AFTER]
    runs.sort(key=lambda run: (RANK[run['status']], -run['updated']))
    return {'state_root': str(state_root()), 'runs': runs}


def title_line(run):
    progress = f" · {run['tasks']['done']}/{run['tasks']['total']} tasks" if run['tasks'] else ''
    return f"{run['project']} · {run['branch']} · {run['status']}{progress}"


# The flow, left to right: (stage key, label, compact label, role). `recheck` shares Triage's box.
FLOW = (('plan_review', 'Plan check', 'Plan', 'codex'), ('plan_revision', 'Plan revision', 'Revise', 'claude'),
        ('setup', 'Setup', 'Setup', 'script'), ('build', 'Build', 'Build', 'claude'),
        ('checks', 'Checks', 'Checks', 'script'), ('review', 'Review', 'Review', 'codex'),
        ('triage', 'Triage', 'Triage', 'claude'), ('pr', 'PR', 'PR', 'script'))
BOX_OF = {**{key: index for index, (key, *_rest) in enumerate(FLOW)}, 'recheck': 6}
WIDE_FROM = 120
OVERLAYS = {'paused': '⏸', 'recovering': '🔧', 'crashed': '⚠'}
ACTIVE = ('running', 'paused', 'recovering', 'crashed', 'needs_you')
SINGLE, DOUBLE = '┌─┐│└─┘', '╔═╗║╚═╝'
LABEL_ROOM = 11


def cols(text):
    """Terminal columns of TEXT: wide characters count 2, combining marks 0."""
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in 'WF' else 1
               for char in text)


def clip(text, room):
    """TEXT within ROOM columns, ending in `…` when it was cut."""
    if cols(text) <= room:
        return text
    kept, used = '', 0
    for char in text:
        if used + cols(char) > room - 1:
            break
        kept, used = kept + char, used + cols(char)
    return kept + '…' if room > 0 else ''


def fit(line, width):
    """The segments of LINE cut to WIDTH columns."""
    out, used = [], 0
    for text, style in line:
        room = width - used
        if cols(text) > room:
            out.append((clip(text, room), style))
            break
        out.append((text, style))
        used += cols(text)
    return out


def clock(stamp):
    try:
        moment = datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        return moment.astimezone().strftime('%H:%M')
    except ValueError:
        return stamp[:16] or '--:--'


def position(run):
    """(box index or None, mode): where the flow stands. The box is always the observation's
    stage; the state only decorates it."""
    observation, status = run['observation'], run['status']
    index = BOX_OF.get(run['stage']) if observation else None
    if status == 'finished':
        return len(FLOW), 'done'
    if status == 'needs_you':
        return index, 'stopped'
    if index is None:
        return None, 'unknown'
    return index, {'running': 'active', 'paused': 'paused', 'recovering': 'recovering',
                   'crashed': 'crashed'}.get(status, 'idle')


def box_label(run, index, here):
    key, label, _compact, _role = FLOW[index]
    if run['stage'] == 'recheck' and here:
        label = 'Re-check'
    elif key == 'build' and here and run['tasks'] and run['tasks']['total']:
        label = clip(f"Build {min(run['tasks']['done'] + 1, run['tasks']['total'])}/{run['tasks']['total']}",
                     LABEL_ROOM)
    return label


def role_of(run, index):
    return 'codex' if run['stage'] == 'recheck' and index == BOX_OF['recheck'] else FLOW[index][3]


def stop_note(run):
    observation = run['observation']
    if observation and observation['state'] == 'stopped' and observation['note']:
        return observation['note']
    return run['last_error']


def marker_text(run, index, mode):
    """(text, style) under the active box."""
    observation = run['observation']
    if mode == 'stopped':
        note = stop_note(run)
        if index is None:
            return ' · '.join(part for part in ('⛔ stopped before Plan check', note) if part), 'stopped'
        return f"⛔ {note or 'stopped'}", 'stopped'
    if mode == 'unknown':
        text = 'stage unknown' if observation else 'stage unknown (older toolkit)'
        return text, 'dim'
    if mode == 'crashed':
        return ' · '.join(part for part in ('⚠ pipeline process is gone', observation['detail']) if part), 'stopped'
    parts = [observation['detail'], observation['note'] if mode in ('paused', 'recovering') else '']
    return ' · '.join(part for part in parts if part), 'dim'


def box_rows(run, index, mode):
    """[(top, middle, bottom) segment lists, x offset, width] per box, and the next x."""
    boxes, x = [], 2
    for i, (key, _label, _compact, _role) in enumerate(FLOW):
        here = i == index
        overlay = f' {OVERLAYS[mode]}' if here and mode in OVERLAYS else ''
        label = box_label(run, i, here) + overlay
        if mode == 'done' or (index is not None and i < index):
            style = 'done'
        elif not here:
            style = 'pending'
        elif mode in ('stopped', 'crashed'):
            style = 'stopped'
        elif mode == 'idle':
            style = 'dim'
        else:
            style = 'active_' + role_of(run, i)
        tl, h, tr, v, bl, _h, br = DOUBLE if here and mode != 'idle' else SINGLE
        inner = cols(label) + 2
        boxes.append(((tl + h * inner + tr, f'{v} {label} {v}', bl + h * inner + br), x, inner + 2, style))
        x += inner + 4
    return boxes


def wide_card(run, width):
    index, mode = position(run)
    boxes = box_rows(run, index, mode)
    lines = [[('  ', 'dim')] for _ in range(3)]
    for i, (rows, _x, _w, style) in enumerate(boxes):
        for row, text in enumerate(rows):
            if i:
                lines[row].append(('──' if row == 1 else '  ', 'dim'))
            lines[row].append((text, style))
    marker, used = [], 0

    def place(column, text, style):
        nonlocal used
        marker.extend([(' ' * (column - used), 'dim'), (text, style)])
        used = column + cols(text)

    for i, (_rows, x, _w, _style) in enumerate(boxes):
        if mode == 'done' or (index is not None and i < index):
            place(x + 2, '✓', 'done')
    if mode != 'done':
        text, style = marker_text(run, index, mode)
        start = boxes[index][1] if index is not None else 2
        if start + cols(text) > width:
            start = max(used + 1, width - cols(text))
        if text:
            place(max(start, used + 1 if used else start), text, style)
    return [*lines, marker]


def compact_card(run):
    index, mode = position(run)
    line = [('  ', 'dim')]
    for i, (_key, _label, short, _role) in enumerate(FLOW):
        here = i == index
        if mode == 'done' or (index is not None and i < index):
            mark, style = '✓', 'done'
        elif not here:
            mark, style = '·', 'pending'
        elif mode == 'stopped':
            mark, style = '✗', 'stopped'
        elif mode == 'idle':
            mark, style = '·', 'dim'
        else:
            mark, style = '▶', 'stopped' if mode == 'crashed' else 'active_' + role_of(run, i)
        text = box_label(run, i, here) if here and FLOW[i][0] == 'build' else short
        if here and run['stage'] == 'recheck':
            text = 'Re-check'
        line.append((f'{mark}{text}' + (f' {OVERLAYS[mode]}' if here and mode in OVERLAYS else '') + ' ', style))
    lines = [line]
    if mode == 'stopped' or mode == 'unknown':
        text, style = marker_text(run, index, mode)
        lines.append([('  ' + text, style)])
    return lines


def event_line(run):
    index, mode = position(run)
    if mode == 'done':
        return [('  🏁 ' + (run['observation']['note'] or 'finished') if run['observation'] else '  🏁 finished',
                 'event')]
    if not run['events']:
        return [('  no events', 'dim')]
    event = run['events'][-1]
    return [(f"  {clock(event['ts'])} {event['message']}", 'event')]


def expanded_lines(run):
    lines = [[(f"  path: {run['checkout']}", 'dim')]]
    if run['last_error']:
        lines.append([(f"  error: {run['last_error']}", 'stopped')])
    if run['tasks'] and run['tasks']['current']:
        lines.append([(f"  task: {run['tasks']['current']}", 'dim')])
    for event in run['events'][-8:]:
        lines.append([(f"  {clock(event['ts'])} {event['message']}", 'event')])
    return lines


def card(run, width, selected, expanded):
    title = [(f"{'›' if selected else ' '} {title_line(run)}", 'selected' if selected else 'title')]
    body = wide_card(run, width) if width >= WIDE_FROM else compact_card(run)
    lines = [title, *body, event_line(run), *(expanded_lines(run) if run['checkout'] in expanded else [])]
    return [fit(line, width) for line in lines]


def layout(runs, width, selected=None, expanded=frozenset(), now=None, state_root=''):
    """(header lines, [card lines per run]); a line is a list of (text, style) segments and never
    wider than WIDTH."""
    now = time.time() if now is None else now
    running = sum(run['status'] in ('running', 'paused', 'recovering') for run in runs)
    needs = sum(run['status'] in ('needs_you', 'crashed') for run in runs)
    finished = sum(run['status'] == 'finished' for run in runs)
    header = [fit([(f"AI pipelines  {running} running · {needs} needs you · {finished} finished  "
                    f"{time.strftime('%H:%M', time.localtime(now))}  ↑↓ ⏎ a r q", 'title')], width)]
    if not runs:
        text = (f'No pipelines found (state root {state_root}). '
                'Start one with .ai/bin/ai-pipeline --approved (in tmux).')
        return header, [[fit([(text, 'dim')], width)]]
    return header, [card(run, width, i == selected, expanded) for i, run in enumerate(runs)]


def render(runs, width, selected=None, expanded=frozenset(), now=None, state_root=''):
    """Every line of the view: the header, then the cards separated by a blank line."""
    header, cards = layout(runs, width, selected, expanded, now, state_root)
    lines = list(header)
    for lines_of in cards:
        lines += [[]] + lines_of
    return lines


def render_text(data, width=140, now=None):
    """Plain text of the view (styles dropped) for `--once` and pipes."""
    lines = render(data['runs'], width, None, frozenset(), now, data['state_root'])
    return '\n'.join(''.join(text for text, _style in line).rstrip() for line in lines) + '\n'


def terminal_attributes(curses):
    """Style name -> curses attribute: 256-colour pairs matching the flow chart, basic colours
    on poorer terminals, bold/reverse without colour."""
    names = ('title', 'selected', 'active_claude', 'active_codex', 'active_script', 'done', 'pending',
             'stopped', 'dim', 'event')
    plain = {'title': curses.A_BOLD, 'selected': curses.A_REVERSE, 'active_claude': curses.A_BOLD,
             'active_codex': curses.A_BOLD, 'active_script': curses.A_BOLD, 'done': curses.A_DIM,
             'pending': curses.A_DIM, 'stopped': curses.A_REVERSE, 'dim': curses.A_DIM, 'event': 0}
    if not curses.has_colors():
        return plain
    curses.use_default_colors()
    rich = curses.COLORS >= 256
    colours = {'active_claude': (208 if rich else curses.COLOR_YELLOW),
               'active_codex': (33 if rich else curses.COLOR_BLUE),
               'active_script': (245 if rich else curses.COLOR_WHITE),
               'stopped': curses.COLOR_RED, 'done': (71 if rich else curses.COLOR_GREEN),
               'pending': (240 if rich else -1), 'dim': (245 if rich else -1)}
    attributes = dict(plain)
    for number, name in enumerate(names, 1):
        if name in colours:
            curses.init_pair(number, colours[name], -1)
            bold = curses.A_BOLD if name.startswith('active_') or name == 'stopped' else 0
            attributes[name] = curses.color_pair(number) | bold
    attributes['selected'] = curses.A_REVERSE | curses.A_BOLD
    return attributes


def draw(screen, header, cards, selected, offset, attributes):
    """Paint the header and the visible slice of the cards; returns the scroll offset that keeps
    the selected card in view."""
    import curses
    height, width = screen.getmaxyx()
    body = [line for lines in cards for line in [[], *lines]][1:]
    room = max(height - len(header), 1)
    if selected is not None and cards:
        start = sum(len(lines) + 1 for lines in cards[:selected])
        end = start + len(cards[selected])
        if start < offset:
            offset = start
        elif end > offset + room:
            offset = min(start, end - room)
    offset = max(0, min(offset, max(len(body) - room, 0)))
    screen.erase()
    for row, line in enumerate([*header, *body[offset:offset + room]][:height]):
        column = 0
        for text, style in fit(line, width):
            try:
                screen.addstr(row, column, text, attributes.get(style, 0))
            except curses.error:
                pass  # The bottom-right cell cannot be written.
            column += cols(text)
    screen.refresh()
    return offset


def interface(screen, all_runs):
    import curses
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    attributes = terminal_attributes(curses)
    screen.keypad(True)
    screen.timeout(2000)
    data, selected, expanded, offset = snapshot(all_runs), 0, set(), 0
    while True:
        runs = data['runs']
        selected = min(selected, len(runs) - 1) if runs else None
        header, cards = layout(runs, screen.getmaxyx()[1], selected, expanded, None, data['state_root'])
        offset = draw(screen, header, cards, selected, offset, attributes)
        key = screen.getch()
        if key in (ord('q'), ord('Q')):
            return
        if key == curses.KEY_DOWN and runs:
            selected = min(selected + 1, len(runs) - 1)
        elif key == curses.KEY_UP and runs:
            selected = max(selected - 1, 0)
        elif key in (10, 13, curses.KEY_ENTER) and runs:
            expanded ^= {runs[selected]['checkout']}
        elif key in (ord('a'), ord('A')):
            all_runs = not all_runs
        if key in (-1, ord('r'), ord('R'), ord('a'), ord('A')):
            current = runs[selected]['checkout'] if runs else None
            data = snapshot(all_runs)
            paths = [run['checkout'] for run in data['runs']]
            selected = paths.index(current) if current in paths else selected


def main(arguments=None):
    parser = argparse.ArgumentParser(prog='ai-dashboard', description='Watch all pipelines on this machine.')
    parser.add_argument('--once', action='store_true', help='print the text view once and exit')
    parser.add_argument('--json', action='store_true', help='print the snapshot as JSON and exit')
    parser.add_argument('--all', action='store_true', help='also show old finished and idle runs')
    args = parser.parse_args(arguments)
    if args.json:
        print(json.dumps(snapshot(args.all), ensure_ascii=False, indent=2))
    elif args.once or not (sys.stdin.isatty() and sys.stdout.isatty()):
        width = shutil.get_terminal_size((140, 24)).columns
        sys.stdout.write(render_text(snapshot(args.all), width))
    else:
        import curses
        import locale
        locale.setlocale(locale.LC_ALL, '')
        try:
            curses.wrapper(interface, args.all)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
