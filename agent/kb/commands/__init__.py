"""commands/__init__.py - Re-exports KBCommandsMixin from sub-mixins."""

from .list import ListMixin
from .query import QueryMixin
from .import_ import ImportMixin
from .graph import GraphMixin
from .classify import ClassifyMixin
from .version import VersionMixin
from .sync import SyncMixin
from .backup import BackupMixin
from .cache import CacheMixin


class KBCommandsMixin(
    ListMixin,
    QueryMixin,
    ImportMixin,
    GraphMixin,
    ClassifyMixin,
    VersionMixin,
    SyncMixin,
    BackupMixin,
    CacheMixin,
):
    """Mixin: all high-level command implementations."""
    pass


__all__ = ["KBCommandsMixin"]
