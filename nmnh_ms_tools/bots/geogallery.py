"""Defines bot to interact with the GeoGallery portal"""
import logging
import re

from .core import Bot, JSONResponse


logger = logging.getLogger(__name__)


class GeoGalleryBot(Bot):
    """Defines methods to interact with https://geogallery.si.edu/portal"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrapper", GeoGalleryResponse)
        super().__init__(*args, **kwargs)
        self.base_url = "https://geogallery.si.edu/portal"

    def get_specimen_by_id(self, sample_id, **kwargs):
        """Gets specimen record by sample id (catalog number, EZID, etc.)"""
        url = self.base_url
        sample_id = str(sample_id).split("ark:/65665/3", 1)[-1]
        if re.match(r"^1\d{6,7}$", sample_id):
            key = "irn"
        elif re.match(r"^[A-z0-9]{32}$", sample_id) or re.search(
            r"[A-z0-9]{8}(-[A-z0-9]{4,12}){4}$", sample_id
        ):
            key = "guid"
            sample_id = sample_id.replace("-", "")
        else:
            key = "sample_id"
        params = {key: sample_id, "format": "json", "limit": 100}
        params.update(kwargs)
        return self.get(url, params=params)

    def get_specimens(self, **kwargs):
        """Gets specimen records matching given criteria"""
        url = self.base_url
        params = {"format": "json", "limit": 100}
        params.update(kwargs)
        return self.get(url, params=params)


class GeoGalleryResponse(JSONResponse):
    """Defines path containing results in a GeoGallery API call"""

    def __init__(self, response, **kwargs):
        results_path = ["response", "content", "SimpleDarwinRecordSet"]
        kwargs.setdefault("results_path", results_path)
        kwargs.setdefault("result_wrapper", ["SimpleDarwinRecord"])
        super().__init__(response, **kwargs)
