"""Malcolm and Breeches simulator package."""

from .phase5d_cards import install as _install_phase5d
from .phase9f5_fixes import install as _install_phase9f5

__version__ = "0.1.0"

_install_phase5d()
_install_phase9f5()
del _install_phase5d
del _install_phase9f5
