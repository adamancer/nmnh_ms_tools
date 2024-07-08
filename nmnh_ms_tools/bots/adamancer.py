"""Defines bot to interact with http://adamancer.pythonanywhere.com"""

import logging

import pandas as pd

from .core import Bot, JSONResponse


logger = logging.getLogger(__name__)


class AdamancerBot(Bot):
    """Defines methods to interact with http://adamancer.pythonanywhere.com"""

    domain = "https://adamancer.pythonanywhere.com"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrapper", AdamancerResponse)
        super().__init__(*args, **kwargs)

    def chronostrat(self, earliest, **kwargs):
        """Gets info about a given named or numeric geologic age"""
        url = "{}/chronostrat".format(self.domain.rstrip("/"))
        params = {"earliest": earliest}
        params.update(kwargs)
        return self.get(url, params=params)

    def metbull(self, name):
        """Gets info about a meteorite"""
        return self.get("{}/metbull/{}".format(self.domain.rstrip("/"), name))

    def tas(self, sample_id, sio2, na2o, k2o):
        url = "{}/tas/name".format(self.domain.rstrip("/"))

        # Convert pandas series to lists
        if isinstance(sample_id, pd.Series):
            sample_id = list(sample_id)
            sio2 = list(sio2)
            na2o = list(na2o)
            k2o = list(k2o)

        n = 50
        resp = None
        if isinstance(sample_id, list) and len(sample_id) > n:
            args = [sample_id, sio2, na2o, k2o]
            while args[0]:
                resp_ = self.tas(*(a[:n] for a in args))
                try:
                    if resp is None:
                        resp = resp_
                    else:
                        resp.append(resp_)
                except KeyError:
                    raise ValueError(f"Invalid resposne: {resp_}")
                args = [a[n:] for a in args]
            return resp

        params = {
            "sample_id": sample_id,
            "sio2": sio2,
            "na2o": na2o,
            "k2o": k2o,
        }
        return self.get(url, params=params)


class AdamancerResponse(JSONResponse):
    """Defines path containing results in a Macrostrat API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault("results_path", ["data"])
        super().__init__(response, **kwargs)
