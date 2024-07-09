"""Template for record subclasss"""

from .core import Record


class Template(Record):
    """Template for record subclasss"""

    # Dict of attr-defaults used in this class
    attributes = {}

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = []
        # Explicitly define defaults for all reported attributes
        # Define additional attributes required for parse
        super().__init__(*args, **kwargs)
        # Define additional attributes

    def __str__(self):
        return self.name

    @property
    def name(self):
        raise NotImplementedError("name")

    def parse(self, data):
        """Parses data from various sources to populate class"""
        raise NotImplementedError("parse")

    def same_as(self, other, strict=True):
        """Tests if object is the same as another object"""
        raise NotImplementedError("same_as")

    def similar_to(self, other):
        """Tests if object is similar to another object"""
        return self.same_as(other, strict=False)

    def _to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError("to_emu")

    def _sortable(self):
        """Returns a sortable version of the object"""
        raise NotImplementedError("_sortable")
