"""Defines bot to interact with the MetBull website"""

from datetime import datetime
import hashlib
import logging
import re

import lxml
from bs4 import BeautifulSoup, SoupStrainer

from .core import Bot, JSONResponse


logger = logging.getLogger(__name__)


class MetBullBot(Bot):
    """Defines methods to scrape data from the MetBull website"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrapper", MetBullResponse)
        kwargs["start_param"] = "page"
        kwargs["limit_param"] = self.get_limit
        kwargs["paged"] = True
        super().__init__(*args, **kwargs)

    def get_meteorites(self, **kwargs):
        """Scrapes meteorite data from the MetBull meteorite search"""
        url = "https://www.lpi.usra.edu/meteor/metbull.php"
        params = {
            "sea": "*",
            "sfor": "names",
            "ants": "",
            "falls": "",
            "valids": "",
            "stype": "contains",
            "lrec": 5000,
            "map": "dm",
            "country": "All",
            "srt": "name",
            "categ": "All",
            "mblist": "All",
            "rect": "",
            "phot": "",
            "strewn": "",
            "snew": 0,
            "pnt": "Normal table",
            "dr": "",
            "page": 1,
        }
        params.update(kwargs)
        return self.get(url, params=params)

    @staticmethod
    def get_limit(response):
        """Extracts max page from HTML"""
        pattern = r"Showing data for page (\d+) of (\d+)"
        match = re.search(pattern, response.text)
        return int(match.group(2))


class MetBullResponse(JSONResponse):
    """Defines methods to parse MetBull HTML to JSON"""

    _cached_json = {}

    def __init__(self, response, **kwargs):
        kwargs.setdefault("results_path", [])
        super().__init__(response, **kwargs)

    def cast_to_json(self):
        """Casts HTML returned by MetBull to JSON"""
        meteorites = []

        text = self._response.text
        key = hashlib.md5(text.encode()).hexdigest()

        # Get timestamp from response
        fmt = "%a, %d %b %Y %H:%M:%S %Z"
        timestamp = datetime.strptime(self._response.headers["Date"], fmt)

        try:
            return self._cached_json[key][:]
        except KeyError:
            meteorites = []

            strainer = SoupStrainer("table", attrs={"id": "maintable"})
            soup = BeautifulSoup(text, "lxml", parse_only=strainer)
            trs = soup.find(id="maintable").find_all("tr")
            keys = [th.text.strip().lower() for th in trs[0].find_all("th")]

            for tr in trs[1:]:

                vals = [td.text.strip() for td in tr.find_all("td")]
                rowdict = dict(zip(keys, vals))

                # Get URL for the canonical record
                url = tr.find("a", href=True)["href"]
                rowdict["metbull_id"] = int(re.search(r"code=(\d+)", url).group(1))

                # Clean up keys
                rowdict["name"] = rowdict["name"].strip("* ")
                rowdict["timestamp"] = timestamp

                lat_lng = rowdict["(lat,long)"].strip("()").split(",")
                try:
                    coords = [s.strip() for s in lat_lng]
                    rowdict["lat"], rowdict["lng"] = coords
                except ValueError:
                    rowdict["lat"] = ""
                    rowdict["lng"] = ""
                del rowdict["(lat,long)"]
                meteorites.append(rowdict)

            logger.debug("{:,} meteorites parsed".format(len(meteorites)))

            self._cached_json[key] = meteorites[:]
            return meteorites
