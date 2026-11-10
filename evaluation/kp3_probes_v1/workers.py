"""OWN trusted process-boundary fixture, never generated code or a model response."""
from pathlib import Path
import time


def late_writer(directory,delay):
    from .campaign import private_child
    p=private_child(directory);(p/'started').write_text('own trusted worker entered')
    time.sleep(delay);(p/'late').write_text('own worker completed')
    return dict(completed=True)
