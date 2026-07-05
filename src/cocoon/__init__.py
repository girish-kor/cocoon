import os

# Cocoon does not use pydantic plugins. Disabling the plugin scan avoids
# pydantic iterating the entry_points of every installed distribution on the
# first model-class construction — a scan that is slow in large environments
# and crashes on a corrupted/incomplete *.dist-info in site-packages. Must be
# set before pydantic is first imported; this package __init__ runs before any
# cocoon submodule that imports pydantic.
os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "1")

__version__ = "0.1.0"
