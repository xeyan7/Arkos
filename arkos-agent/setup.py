"""
setup.py — wheel/sdist build guard.

Arkos is not distributed as a wheel or sdist. This checkout is consumed either
in place or through an internal build that owns its own packaging; neither path
goes through ``bdist_wheel``/``sdist``.

That matters because a generic wheel would ship without bundled assets (locales,
skills, optional-mcps, plugin manifests): those are resolved at runtime from the
source-checkout layout, so an artifact built by these setuptools commands would
be silently incomplete rather than merely unsupported.

This file overrides the ``bdist_wheel`` and ``sdist`` commands to raise an
error. The PEP 517 ``build_wheel`` / ``build_sdist`` hooks in
``setuptools.build_meta`` call these commands internally, so the guard fires for
``uv build``, ``pip wheel``, ``python -m build``, and direct ``setup.py``
invocations alike.

Editable installs (``uv sync``, ``uv pip install -e .``) use
``build_editable``, which does NOT call ``bdist_wheel`` — it calls
``build_ext`` in editable mode. The guard therefore does not affect development.
"""

import os

from setuptools import setup
from setuptools.command.sdist import sdist

_ROOT = os.path.dirname(os.path.abspath(__file__))

_BLOCK_MESSAGE = (
    "Building wheels or sdists for this package is not supported.\n"
    "It is not distributed as a wheel or sdist — use this checkout in place,\n"
    "or the internal build that owns packaging for this project.\n"
    "\n"
    "If you are developing, use an editable install instead:\n"
    "  uv sync          # or: uv pip install -e ."
)


class _GuardedSdist(sdist):
    def run(self, *args, **kwargs):
        raise RuntimeError(_BLOCK_MESSAGE)


cmdclass = {"sdist": _GuardedSdist}

try:
    from setuptools.command.bdist_wheel import bdist_wheel

    class _GuardedBdistWheel(bdist_wheel):
        def run(self, *args, **kwargs):
            raise RuntimeError(_BLOCK_MESSAGE)

    cmdclass["bdist_wheel"] = _GuardedBdistWheel
except ImportError:
    pass


def _root_py_modules():
    try:
        names = os.listdir(_ROOT)
    except OSError:
        return []
    return sorted(
        name[:-3]
        for name in names
        if name.endswith(".py") and name != "setup.py"
    )


setup(cmdclass=cmdclass, py_modules=_root_py_modules())
