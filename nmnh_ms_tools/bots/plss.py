"""Defines bot to interact with the BLM PLSS webservices"""

import logging

from shapely.geometry import Polygon

from .core import Bot, JSONResponse
from ..tools.geographic_operations.geometry import GeoMetry


logger = logging.getLogger(__name__)


class PLSSBot(Bot):
    """Contains methods for interacting with BLM PLSS webservices"""

    defaults = {
        "text": "",
        "objectIds": "",
        "time": "",
        "geometry": "",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "",
        "spatialRel": "esriSpatialRelIntersects",
        "relationParam": "",
        "outFields": "",
        "returnGeometry": "false",
        "returnTrueCurves": "false",
        "maxAllowableOffset": "",
        "geometryPrecision": "",
        "outSR": "",
        "returnIdsOnly": "false",
        "returnCountOnly": "false",
        "orderByFields": "",
        "groupByFieldsForStatistics": "",
        "outStatistics": "",
        "returnZ": "false",
        "returnM": "false",
        "gdbVersion": "",
        "returnDistinctValues": "false",
        "resultOffset": "",
        "resultRecordCount": "",
        "queryByDistance": "",
        "returnExtentOnly": "false",
        "datumTransformation": "",
        "parameterValues": "",
        "rangeValues": "",
        "quantizationParameters": "",
        "f": "json",
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrapper", PLSSResponse)
        super().__init__(*args, **kwargs)
        self.base_url = (
            "https://gis.blm.gov/arcgis/rest/services/Cadastral/"
            "BLM_Natl_PLSS_CadNSDI/MapServer"
        )

    def get_sections(self, state, twp, rng, sec):
        """Finds all sections missing a PLSS coordinate"""
        townships = self.get_townships(state, twp, rng)
        return [self.get_section(plss_id, sec) for plss_id in townships]

    def get_townships(self, state, twp, rng):
        """Finds matching townships and ranges using BLM webservices"""
        url = "{}/1/query".format(self.base_url)
        # Set query params and write WHERE clause
        query = {
            "state": state,
            "twp_no": twp.strip("TNS").zfill(3),
            "twp_dir": twp[-1],
            "rng_no": rng.strip("REW").zfill(3),
            "rng_dir": rng[-1],
        }
        mask = (
            "STATEABBR='{state}'"
            " AND TWNSHPNO='{twp_no}'"
            " AND TWNSHPDIR='{twp_dir}'"
            " AND RANGENO='{rng_no}'"
            " AND RANGEDIR='{rng_dir}'"
        )
        params = {k: v[:] for k, v in self.defaults.items()}
        params.update(
            {
                "where": mask.format(**query),
                "outFields": "PLSSID,STATEABBR,TWNSHPNO,TWNSHPDIR,RANGENO,RANGEDIR",
            }
        )
        response = self.get(url, params=params)
        matches = []
        if response:
            # Match returned features against query
            for feature in response:
                try:
                    attrs = feature["attributes"]
                    if all(
                        [
                            attrs["STATEABBR"] == query["state"],
                            attrs["TWNSHPNO"] == query["twp_no"].zfill(3),
                            attrs["TWNSHPDIR"] == query["twp_dir"],
                            attrs["RANGENO"] == query["rng_no"].zfill(3),
                            attrs["RANGEDIR"] == query["rng_dir"],
                        ]
                    ):
                        matches.append(attrs["PLSSID"])
                except KeyError:
                    pass
        return matches

    def get_section(self, plss_id, sec):
        """Finds a specific section using BLM webservices"""
        if plss_id is None:
            return []
        url = "{}/2/query".format(self.base_url)
        # Set query params and write WHERE clause
        query = {"plss_id": plss_id, "sec": str(sec.lower()).strip("sec. ").zfill(2)}
        mask = "PLSSID='{plss_id}'" " AND FRSTDIVNO='{sec}'" " AND FRSTDIVTYP='SN'"
        params = {k: v[:] for k, v in self.defaults.items()}
        params.update(
            {
                "where": mask.format(**query),
                "outFields": "FRSTDIVNO",
                "returnGeometry": "true",
            }
        )
        response = self.get(url, params=params)
        if response:
            for feature in response:
                try:
                    if feature["attributes"]["FRSTDIVNO"] == query["sec"]:
                        for coords in feature["geometry"]["rings"]:
                            # Reverse order of coordinates and convert to box
                            polygon = Polygon(coords)
                            return GeoMetry(
                                polygon, crs=response.wkid()
                            ).envelope.to_crs(4326)
                except KeyError:
                    pass
        return None


class PLSSResponse(JSONResponse):
    """Defines path containing results in a PLSS API call"""

    def __init__(self, response, **kwargs):
        kwargs.setdefault("results_path", ["features"])
        super().__init__(response, **kwargs)

    def wkid(self, prefix="epsg"):
        """Returns the datum for the response"""
        wkid = self.json["spatialReference"]["latestWkid"]
        return "{}:{}".format(prefix, wkid)
