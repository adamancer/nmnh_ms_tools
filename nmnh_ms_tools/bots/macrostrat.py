"""Defines bot to interact with the Macrostrat API"""

import logging

from .core import Bot, JSONResponse


logger = logging.getLogger(__name__)


class MacrostratBot(Bot):
    """Defines methods to interact with https://macrostrat.org/api"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrapper", MacrostratResponse)
        super().__init__(*args, **kwargs)

    def get_units(self, **kwargs):
        """Gets snippets matching given criteria from the Macrostrat API"""
        url = "https://macrostrat.org/api/units"
        params = {"response": "long"}
        params.update(kwargs)
        return self.get(url, params=params)

    def get_units_by_id(self, strat_name_id, **kwargs):
        """Gets snippets matching given criteria from the Macrostrat API"""
        return self.get_units(strat_name_id=strat_name_id, **kwargs)

    def get_units_by_name(self, strat_name, **kwargs):
        """Gets snippets matching given criteria from the Macrostrat API"""
        return self.get_units(strat_name=strat_name, **kwargs)


class MacrostratResponse(JSONResponse):
    """Defines path containing results in a Macrostrat API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault("results_path", ["success", "data"])
        super().__init__(response, **kwargs)
