import csv
import html
import logging
import re
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import yaml
from lxml import etree

from ...bots import Bot
from ...records import CatNum, Record, Site, get_tree
from ...utils import base_to_int, fast_hash, int_to_base, oxford_comma
from vocmap import VocMap
from xmu import EMuDate

logger = logging.getLogger(__name__)

SESAR_DIR = Path(r"~\data\nmnh_ms_tools\sesar").expanduser()
IGSN_PATH = SESAR_DIR / "igsns.csv"


class IGSNData:

    def __init__(self, path):
        self.path = path
        self.df = pl.read_csv(path, dtypes=[pl.Utf8] * 3)

        # Clean up the dataframe
        self.df = self.df.unique().sort("IGSN")
        self.df.write_csv(self.path)

        for cl in [IGSN, SESARRecord]:
            cl._df = self

    def __str__(self):
        return str(self.df)

    def __repr__(self):
        return repr(self.df)

    def filter(self, **kwargs):
        predicate = [(pl.col(col) == val) for col, val in kwargs.items()]
        return self.df.filter(pl.Expr.and_(*predicate))

    def add(self, *args, **kwargs):
        if args:
            new = pl.from_dicts(args[0])
        elif kwargs:
            new = pl.from_dicts([kwargs])
        self.df = pl.concat([self.df, new]).sort("IGSN")
        self.df.write_csv(self.path)
        return self

    def update(self, igsn, **kwargs):
        rows = self.df.filter(pl.col("IGSN") == igsn).to_dicts()
        for row in rows:
            row.update(kwargs)
        schema = {k: pl.Utf8 for k in row}
        self.df = pl.concat(
            [
                self.df.filter(pl.col("IGSN") != igsn),
                pl.from_dicts(rows, schema=schema),
            ]
        ).sort("IGSN")
        self.df.write_csv(self.path)
        return self

    def min(self):
        return IGSN(self.df.select(pl.min("IGSN")).to_dicts()[0]["IGSN"])

    def max(self):
        return IGSN(self.df.select(pl.max("IGSN")).to_dicts()[0]["IGSN"])

    def duplicates(self, col):
        other = {"Name": "IGSN", "IGSN": "Name"}[col]
        vals = {}
        for dct in self.df.filter(pl.col(col).is_duplicated()).to_dicts():
            vals.setdefault(dct[col], []).append(dct[other])
        return {k: sorted(set(v)) for k, v in vals.items() if len(set(v)) > 1}

    def match_name(self, name):
        """Returns the IGSN matching a sample name"""
        try:
            catnum = CatNum(name)
        except ValueError:
            try:
                catnum = CatNum(name.name)
            except (AttributeError, ValueError):
                if not isinstance(name, str):
                    raise ValueError(f"Could extact name from {name}")
                catnum = None

        if catnum is not None:
            catnum.mask = "include_div"
            variants = [str(catnum)]
            if catnum.division == "MIN":
                if catnum.suffix == "00":
                    catnum.suffix = ""
                elif catnum.suffix == "":
                    catnum.suffix = "00"
                variants.append(str(catnum))
        else:
            print(f"Could not parse {repr(name)} as catalog number")
            variants = [name]

        rows = self.df.filter(pl.col("Name").is_in(variants))
        return [r["IGSN"] for r in rows.to_dicts()]

    def match_igsn(self, igsn):
        """Returns the sample name matching an IGSN"""
        rows = self.df.filter(pl.col("IGSN") == igsn)
        return [r["Name"] for r in rows.to_dicts()]

    def find_new_registrations(self):
        """Check SESAR for new registrations"""
        igsn = self.max()
        with SESARRecord.bot.disable_cache():
            while True:
                igsn += 1
                try:
                    rec = igsn.display()
                except ValueError:
                    igsn -= 1
                    break
                else:
                    self.add(Name=rec.name, IGSN=igsn.suffix, Hash=rec.hash())
        return igsn


class IGSN:

    _df = None

    def __init__(self, val, code=None, prefix="10.58151"):
        if isinstance(val, self.__class__):
            val = str(val)
        if isinstance(val, int):
            val = int_to_base(val, 36)
        if not val.startswith("10."):
            val = f"{prefix}/{val}"
        # Map a specimen name to an IGSN
        if not re.match(r"10\.\d{5}/[A-Z]{3}[A-Z0-9]{6}$", val):
            igsn = self.df.filter(Name=val)[0]["IGSN"]
            if self.name == val:
                val = igsn
        if not val.startswith("10."):
            raise ValueError(f"No prefix: {val}")
        self.value = val
        self._code = code

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"IGSN({self.value})"

    def __int__(self):
        return base_to_int(str(self.suffix), 36)

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.value == other.value

    @property
    def code(self):
        if self._code is None:
            if self.suffix.startswith("IE") and self.suffix[:5].isalpha():
                return self.suffix[:5]
            return self.suffix[:3]
        return self._code

    @property
    def prefix(self):
        return self.split()[0]

    @property
    def suffix(self):
        return self.split()[1]

    @property
    def name(self):
        return self.df.filter(IGSN=self.suffix).to_dicts()[0]["Name"]

    @property
    def df(self):
        return self.__class__._df

    def display(self):
        return SESARRecord(str(self))

    def split(self):
        return self.value.split("/", 1)

    def __add__(self, val):
        return self.__class__(int(self) + val)

    def __radd__(self, val):
        return self.__class__(int(self) + val)

    def __iadd__(self, val):
        return self.__class__(int(self) + val)

    def __sub__(self, val):
        return self.__class__(int(self) - val)

    def __radd__(self, val):
        return self.__class__(val - int(self))

    def __isub__(self, val):
        return self.__class__(int(self) - val)


class SESARBot(Bot):

    debug = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wait", 0.2)
        super().__init__(*args, **kwargs)
        self._params = {}
        try:
            with open("config.yml") as f:
                config = yaml.safe_load(f)
                self._params.update(
                    {
                        "username": config["username"],
                        "password": config["password"],
                    }
                )
        except FileNotFoundError:
            print("No config file found! Cannot register or update records")

    @property
    def url(self):
        if self.debug:
            return "https://app-sandbox.geosamples.org/webservices"
        return "https://app.geosamples.org/webservices"

    def display(self, igsn):
        igsn = IGSN(igsn)
        igsns = [igsn.value]
        for val in igsns:
            params = {"igsn": val}
            params.update(self._params)
            resp = self.get(f"{self.url}/display.php", params=params)
            if resp.status_code == 200:
                break
        if resp.status_code == 200:
            self._log_result(resp, False)
        return resp

    def register(self, content):
        if not self._params:
            raise ValueError("Username and password must be supplied in config.yml")
        data = {"content": content}
        data.update(self._params)
        resp = self.post(f"{self.url}/upload.php", data=data)
        if resp.status_code == 200:
            self._log_result(resp, False)
        return resp

    def update(self, content):
        if not self._params:
            raise ValueError("Username and password must be supplied in config.yml")
        data = {"content": content}
        data.update(self._params)
        resp = self.post(f"{self.url}/update.php", data=data)
        if resp.status_code == 200:
            self._log_result(resp, False)
        return resp

    def delete_url(self, igsn, puburl):
        if not self._params:
            raise ValueError("Username and password must be supplied in config.yml")
        data = {"igsn": str(IGSN(igsn)), "puburl": puburl}
        data.update(self._params)
        resp = self.post(f"{self.url}/deletePubURL.php", data=data)
        if resp.status_code == 200:
            self._log_result(resp, False)
        return resp

    def handle_error(self, resp):
        self._log_result(resp)

    @staticmethod
    def _log_result(resp, include_text=True):
        result = "succeeded"
        logfunc = logger.info
        if resp.status_code != 200:
            result = "failed"
            logfunc = logger.warning

        req = resp.request

        # Hide password and content in body and url
        if "display" in req.url:
            url = re.sub(r"(username|password)=.*?(&|$)", "", req.url).rstrip("&")
        else:
            url = re.sub(r"password=.*?(&|$)", r"password=********\1", req.url)
        body = {}
        for key, val in parse_qs(req.body).items():
            if key != "password":
                val = val[0]
                if key == "content" and resp.status_code == 200:
                    for key_ in ("igsn", "name"):
                        try:
                            val = (
                                "..."
                                + re.search(rf"<{key_}>.*?</{key}>", val).group()
                                + "..."
                            )
                            break
                        except AttributeError:
                            pass
                    else:
                        val = "..."
                elif key == "content":
                    val = re.sub(r"\n +", "", val)
                body[key] = val

        # Check for cache
        try:
            from_cache = resp.from_cache
        except AttributeError:
            from_cache = False
        cached = " (from cache)" if from_cache else ""

        # Set base message
        msg = f"Request {result}: {url} [{req.method}, {resp.status_code}{cached}, {body}] "
        msg = msg.replace(", {}", "")

        if "<results>" in resp.text:
            results = _xml_to_dict(etree.fromstring(resp.text))["results"]
            if isinstance(results, dict):
                results = [results]
            for result in results:
                logfunc(msg + str(result))
        elif resp.text and (include_text or resp.status_code != 200):
            logfunc(msg + resp.text)
        elif resp.status_code != 200:
            logfunc(msg + "No error provided")
        else:
            logfunc(msg.rstrip(" "))


class SESARRecord(Record):
    """Template for record subclasss"""

    bot = SESARBot()
    schema = etree.XMLSchema(etree.parse(SESAR_DIR / "sample.xsd"))
    update_schema = etree.XMLSchema(etree.parse(SESAR_DIR / "updateSample.xsd"))
    template = etree.parse(SESAR_DIR / "sample.xml")
    tree = get_tree()

    _df = None
    _types = None
    _vocabs = None

    terms = [
        c.tag.split("}")[1]
        for c in template.xpath(
            "/g:samples/g:sample", namespaces={"g": "http://app.geosamples.org"}
        )[0]
    ]

    map_unknown_terms = True

    def __init__(self, *args, **kwargs):
        # Set lists of original class attributes and reported properties
        self._class_attrs = set(dir(self))
        self._properties = ["name"]
        # Explicitly define defaults for all reported attributes
        self.user_code = ""
        self.sample_type = ""
        self.sample_subtype = ""
        self._name = ""
        self.material = ""
        self.igsn = None
        self.parent_igsn = None
        self.publish_date = ""
        self.classification = {}
        self.classification_comment = ""
        self.field_name = ""
        self.description = ""
        self.age_min = ""
        self.age_max = ""
        self.age_unit = ""
        self.geological_age = ""
        self.geological_age = ""
        self.geological_unit = ""
        self.collection_method = ""
        self.collection_method_descr = ""
        self.size = ""
        self.size_unit = ""
        self.sample_comment = ""
        self.purpose = ""
        self.latitude = ""
        self.longitude = ""
        self.latitude_end = ""
        self.longitude_end = ""
        self.elevation = ""
        self.elevation_end = ""
        self.elevation_unit = ""
        self.vertical_datum = ""
        self.northing = ""
        self.easting = ""
        self.zone = ""
        self.navigation_type = ""
        self.primary_location_type = ""
        self.primary_location_name = ""
        self.location_description = ""
        self.locality = ""
        self.locality_description = ""
        self.country = ""
        self.province = ""
        self.county = ""
        self.city = ""
        self.cruise_field_prgrm = ""
        self.platform_type = ""
        self.platform_name = ""
        self.platform_descr = ""
        self.launch_platform_name = ""
        self.launch_id = ""
        self.launch_type_name = ""
        self.collector = ""
        self.collector_detail = ""
        self.collection_start_date = ""
        self.collection_end_date = ""
        self.collection_date_precision = ""
        self.current_archive = ""
        self.original_archive = ""
        self.original_archive_contact = ""
        self.depth_min = ""
        self.depth_max = ""
        self.depth_scale = ""
        self.sample_other_names = []
        self.external_urls = []
        # Define additional attributes required for parse
        self.verbatim = None
        self.inferred_igsn = False
        super().__init__(*args, **kwargs)
        # Check for IGSN if none provided
        if not self.igsn:
            self.infer_igsn()
        # Validate record
        self.validate()

    def __str__(self):
        return f"SESARRecord({self.to_dict()})"

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, val):
        self._name = val

    @property
    def vocabs(self):
        if self.__class__._vocabs is None:
            path = SESAR_DIR / "vocabs.csv"
            try:
                vocabs = VocMap(path)
            except OSError:
                vocabs = VocMap()

            with open(
                SESAR_DIR / "suggested.csv", encoding="utf-8-sig", newline=""
            ) as f:
                for row in csv.DictReader(f):
                    vocabs.add([row["value"]], name=row["name"])

            mask = "https://api.geosamples.org/v1/vocabularies/{}/all"
            for endpoint in (
                "classifications",
                "countries",
                "launchtypes",
                "navtypes",
                "sampletypes",
            ):
                resp = self.bot.get(mask.format(endpoint))
                terms = []
                for key, val in resp.json().items():
                    if isinstance(val, str):
                        terms.append(val)
                    else:
                        terms.extend([f"{key}>{v}" for v in val])
                vocabs.add(terms, name=endpoint)

            vocabs.save(path)
            self.__class__._vocabs = vocabs

        return self.__class__._vocabs

    @property
    def types(self):
        if self._types is None:
            with open(SESAR_DIR / "classifications.xsd") as f:
                types = list(set(re.findall(r'"([A-Za-z]+)Type"', f.read())))
                del types[types.index("Igneous")]
                self.__class__._types = types
        return self.__class__._types

    @property
    def df(self):
        return self.__class__._df

    def parse(self, data):
        """Parses data from various sources to populate class"""
        self.verbatim = data
        if isinstance(data, int):
            data = IGSN(data)
        if isinstance(data, (bytes, str, IGSN)):
            self._parse_sesar(data)
        elif "CatNumber" in data:
            self._parse_emu(data)
        else:
            raise ValueError(f"Could not parse {repr(data)}")

        # Look up IGSN if not provided
        if self.name and not self.igsn:
            try:
                self.igsn = self.df.filter(Name=self.name).to_dict()[0]["igsn"]
            except KeyError:
                pass

        # Set IGSNs
        if self.igsn:
            self.igsn = IGSN(self.igsn)
        if self.parent_igsn:
            self.parent_igsn = IGSN(self.parent_igsn)

        # Format attributes
        for attr in self.attributes:
            val = getattr(self, attr)
            if not val:
                setattr(self, attr, None)
            elif isinstance(val, str) and re.match("-?\d+\.\d+$", val):
                setattr(self, attr, re.sub("0+$", "", val))

    def same_hash(self):
        if not self.igsn:
            raise ValueError("No IGSN in record")
        return self.hash() in self.df.filter(IGSN=self.igsn.suffix)["Hash"].to_list()

    def diff(self, check_sesar=True):

        # Records that haven't been registered return an empty dict
        if not self.igsn:
            return {}

        # Record hash matches database
        if self.same_hash():
            return {}

        # Find differences
        rec = self.__class__(self.igsn)
        self.publish_date = rec.publish_date
        diff = {}
        for attr in self.attributes:
            old = getattr(rec, attr)
            new = getattr(self, attr)

            # Handle collection dates, which are uploaded as datetimes but
            # displayed using simpler formats
            if attr in ["collection_start_date", "collection_end_date"]:
                try:
                    fmt = {
                        "year": "%Y",
                        "month": "%Y",
                        "day": "%Y-%m-%d",
                    }[self.collection_date_precision]
                except KeyError:
                    pass
                else:
                    if old:
                        old = EMuDate(old.split("T")[0]).strftime(fmt)
                    if new:
                        new = EMuDate(new.split("T")[0]).strftime(fmt)

            if new != old:
                diff[attr] = (old, new)

        # Country must be populated if state is populated
        for key in ("province", "county", "city"):
            if key in diff and not "country" in diff:
                diff["country"] = (getattr(rec, "country"), getattr(self, "country"))
                break

        # Latitude and longitude must appear as a pair
        missing = set(("latitude", "longitude")) - set(diff)
        if len(missing) == 1:
            attr = list(missing)[0]
            diff[attr] = (getattr(rec, attr), getattr(self, attr))

        # Catch IGSN and name mismatches, which are serious errors
        for attr in ["igsn", "name"]:
            if attr in diff:
                raise ValueError(f"Mismatched {attr} ({diff[attr]}(")

        return diff

    def register(self):
        if self.igsn:
            raise ValueError(f"IGSN already registered: {self.igsn}")
        resp = self.bot.register(self.to_xml_string(schema=self.schema))
        if resp.status_code == 200:
            # Get IGSN from response
            result = _xml_to_dict(etree.fromstring(resp.text))["results"]["sample"]
            igsn = IGSN(result["igsn"])
            self.df.add(
                Name=self.name,
                IGSN=igsn.suffix,
                Hash=self.hash(),
            )
        return resp

    def update(self):
        if not self.igsn:
            raise ValueError(f"No IGSN")
        attrs = self.diff()
        if attrs:
            attrs = set(["igsn", "name"] + list(attrs))
            resp = self.bot.update(
                self.to_xml_string(
                    attrs=attrs,
                    schema=self.update_schema,
                ),
            )
            if resp.status_code == 200:
                self.df.update(self.igsn.suffix, Hash=self.hash())
            return resp

    def delete_url(self, puburl):
        self.bot.delete_url(self.igsn, puburl)

    def infer_igsn(self):
        if not self.igsn:
            igsns = self._df.match_name(self.name)
            if len(igsns) == 1:
                self.igsn = igsns[0]
                self.inferred_igsn = True
            elif igsns:
                raise ValueError(f"Multiple IGSNs match {repr(self.name)} ({igsns})")

    def hash(self):
        attrs = {k for k, v in self.to_dict().items() if v and k != "publish_date"}
        return fast_hash(
            self.to_xml_string(attrs=attrs, norm_dates=True).encode("utf-8")
        )

    def validate(self):
        try:
            self.to_xml_string(schema=self.schema)
        except Exception as exc:
            raise Exception(f"Invalid XML: {self.to_xml_string()} ({self})") from exc

    def same_as(self, other, strict=True):
        """Tests if object is the same as another object"""
        raise NotImplementedError("same_as")

    def similar_to(self, other):
        """Tests if object is similar to another object"""
        return self.same_as(other, strict=False)

    def to_xml(self, obj=None, xml=None, output=None, attrs=None, schema=None):

        # Set up attributes
        xmlns_xs = etree.QName("http://app.geosamples.org", "xs")
        xmlns_xsi = etree.QName("http://app.geosamples.org", "xsi")
        xsi_schema = etree.QName(
            "http://www.w3.org/2001/XMLSchema-instance", "schemaLocation"
        )

        root = None
        if xml is None:
            obj = self.to_dict()
            root = etree.Element(
                "samples",
                attrib={xsi_schema: "http://app.geosamples.org/4.0/sample.xsd"},
                nsmap={
                    None: "http://app.geosamples.org",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
                },
            )
            xml = etree.SubElement(root, "sample")

        if isinstance(obj, dict):
            for key, val in obj.items():
                if attrs is None or key in attrs:
                    if key == "classification":
                        elem = etree.SubElement(
                            xml,
                            key,
                            attrib={
                                xsi_schema: "http://app.geosamples.org/classifications.xsd",
                            },
                            nsmap={
                                None: "http://app.geosamples.org",
                                "xs": "http://www.w3.org/2001/XMLSchema",
                                "xsi": "http://www.w3.org/2001/XMLSchema-instance",
                            },
                        )
                    else:
                        elem = etree.SubElement(xml, key)
                    self.to_xml(val, elem)
        elif isinstance(obj, list):
            for val in obj:
                self.to_xml(val, xml)
        elif obj and (attrs is None or xml.tag in attrs):
            xml.text = str(obj)
        else:
            xml.getparent().remove(xml)

        if root is not None:
            xml = etree.fromstring(etree.tostring(root))
            if schema is self.schema:
                xml = prune_empty_nodes(xml)
            if schema:
                schema.assertValid(xml)

        return xml

    def to_xml_string(self, attrs=None, schema=None, norm_dates=False, **kwargs):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("pretty_print", True)
        kwargs.setdefault("xml_declaration", True)
        xml_string = etree.tostring(
            self.to_xml(attrs=attrs, schema=schema), **kwargs
        ).decode("UTF-8")

        # Simplify datetimes to match the SESAR display format
        if norm_dates:
            for orig in re.findall("<collection_[a-z]+_date>(.*?T.*?)<", xml_string):
                fmt = {
                    "year": "%Y",
                    "month": "%Y",
                    "day": "%Y-%m-%d",
                }[self.collection_date_precision]
                val = EMuDate(orig.split("T")[0]).strftime(fmt)
                xml_string = xml_string.replace(f"_date>{orig}<", f"_date>{val}<")

        return xml_string.strip()

    def save_xml(self, path, attrs=None, schema=None, **kwargs):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("pretty_print", True)
        kwargs.setdefault("xml_declaration", True)
        self.to_xml(attrs=attrs, schema=schema).getroottree().write(path, **kwargs)

    def map_term(self, term, vocab):
        try:
            return self.vocabs[vocab][term]
        except KeyError:
            if self.map_unknown_terms:
                print(self.verbatim["irn"])
                return self.vocabs[vocab].get(term)
            else:
                raise

    def _parse_emu(self, data):
        evt = data.get("BioEventSiteRef", {})
        other_nums = data.grid("CatOtherNumbersValue_tab").add_columns()
        taxa = [t["ClaScientificName"] for t in data.get("IdeTaxonRef_tab", [])]

        # Map primary taxon to a SESAR classification
        if not taxa[0]:
            raise ValueError(f"No identification provided: {data}")
        primary = self.tree.place(taxa[0])
        parents = [t["sci_name"] for t in primary.official().parents(True)]
        if "Minerals" in parents:
            if parents[-1][0].isnumeric():
                key = f"Mineral>{str(primary)}"
            else:
                key = f"Mineral>{parents[-1]}"
        else:
            key = " > ".join(parents)
        classification = self.map_term(key, "classifications")

        # Some rock names (like impactites) do not map to useful official
        # taxa. Fall back to the specific classification in that case.
        if classification is None and "Minerals" not in parents:
            parents = [t["sci_name"] for t in primary.parents(True)]
            key = " > ".join(parents)
            classification = self.map_term(key, "classifications")
        if classification is None:
            raise ValueError(
                f"No classification found: {repr(key)} (irn={data['irn']})"
            )
        classification = classification.replace("materials>", "").split(">")

        # Handle special cases for material
        material = classification[0]
        if material not in {"Biology", "Rock", "Mineral"}:
            classification = []

        # Unknown is a top-level classification despite appearing as a
        # second-level classification in some of the SESAR vocabs (e.g.,
        # Rock > Unknown). Any material can use Unknown.
        if (
            material != "Mineral"
            and len(classification) == 2
            and classification[1] == "Unknown"
        ):
            classification = ["Unknown"]

        # Add ClassficationType fields
        for type_ in self.types:
            if type_ in classification:
                if classification[-2] == type_:
                    classification.insert(-1, f"{type_}Type")
                    break

        self.user_code = "NHB"

        # Sample type defaults to Individual Sample if empty
        self.sample_type = self.map_term(evt.get("ColCollectionMethod"), "sampletypes")
        if self.sample_type is not None:
            self.sample_type = self.sample_type.replace("objecttypes>", "")
        if not self.sample_type:
            self.sample_type = "Individual Sample"
        self.sample_subtype = None

        self.name = CatNum(data).summarize("include_div")
        self.material = material

        try:
            igsn = other_nums[{"CatOtherNumbersType_tab": "IGSN"}][0][
                "CatOtherNumbersValue_tab"
            ]
        except IndexError:
            pass
        else:
            self.igsn = igsn

        try:
            igsn = other_nums[{"CatOtherNumbersType_tab": "Parent IGSN"}][0][
                "CatOtherNumbersValue_tab"
            ]
        except IndexError:
            pass
        else:
            self.parent_igsn = igsn

        # Publish date is ET
        self.publish_date = (datetime.now() + +timedelta(hours=8)).date().isoformat()

        if len(classification) > 1:
            self.classification = {}
            dct = self.classification
            i = -2 if classification[-2].endswith("Type") else -1
            for val in classification[:i]:
                dct.setdefault(val, {})
                dct = dct[val]
            if i == -2:
                dct[classification[-2]] = classification[-1]
            else:
                dct[classification[-1]] = []
        elif classification:
            self.classification = {classification[0]: ""}

        self.classification_comment = None
        self.field_name = self.tree.name_item(taxa)
        self.descripton = data.get("BioLiveSpecimen")

        self.age_min = None
        self.age_max = None
        self.age_unit = None

        fields = (
            "AgeGeologicAgeEra_tab",
            "AgeGeologicAgeSystem_tab",
            "AgeGeologicAgeSeries_tab",
            "AgeGeologicAgeStage_tab",
        )
        grid = data.grid(fields[0]).add_columns()
        self.geological_age = self._format_range(grid, fields)

        fields = (
            "AgeStratigraphyGroup_tab",
            "AgeStratigraphyFormation_tab",
            "AgeStratigraphyMember_tab",
        )
        grid = data.grid(fields[0]).add_columns()
        self.geological_unit = self._format_range(grid, fields)

        self.collection_method = self.map_term(
            evt.get("ColCollectionMethod"), "methods"
        )
        self.collection_method_descr = None

        # Use Site for named places
        site = Site(evt)
        try:
            site.map_admin()
        except ValueError:
            pass

        self.country = self.map_term(site.country, "countries")

        # SESAR limitation: SESAR requires country if any of these fields
        # are populated, so omit them if country cannot be mapped
        if self.country:
            self.province = site.state_province
            self.county = site.county
            self.city = site.municipality

        for location_type, field in {
            "Island": "island",
            "Island Group": "island_group",
            "Bay/Sound": "bay_sound",
            "Feature": "features",
            "Sea/Gulf": "sea_gulf",
            "Ocean": "ocean",
        }.items():
            val = getattr(site, field)
            if not isinstance(val, list):
                val = val.split(";")
            for val in val:
                if val:
                    self.primary_location_type = location_type
                    self.primary_location_name = val.strip()
                    break

        for attr in (
            "site_num",
            "mine",
            "volcano",
            "settings",
        ):
            val = getattr(site, attr)
            if val and isinstance(val, list):
                val = val[0]
            if val:
                self.locality = val
                break
        loc = evt.get("LocPreciseLocation")
        if not loc.lower().startswith("locality key"):
            self.locality_description = loc

        # Use original event record for everything else
        grid = evt.grid("LatLatitude_nesttab").add_columns()
        for row in grid[{"LatPreferred_tab": "Yes"}]:
            lat = row["LatCentroidLatitudeDec_tab"]
            lon = row["LatCentroidLongitudeDec_tab"]
            if lat and lon:
                # Truncate mineral coordinates to degree
                if self.material == "Mineral":
                    lat = int(lat)
                    lon = int(lon)
                self.latitude = str(lat)
                self.longitude = str(lon)
                self.location_description = row["LatGeoreferencingNotes0"]

        # Map depth and elevation
        for root, prefix, units in (
            ("TerElevation", "", {0: "Met", 1: "Ft"}),
            ("AquBottomDepth", "-", {0: "Met", 1: "Ft", 2: "Fath"}),
        ):
            elevs = []
            for key in ("From", "To"):
                try:
                    unit = units[evt[f"{root}{key}Orig"]]
                    if unit == "Fath":
                        unit = "Met"
                    val = evt[f"{root}{key}{unit}"]
                    elevs.append(int(float(f"{prefix}{val}")))
                except KeyError:
                    pass

            if elevs:
                self.elevation = elevs[0]
                self.elevation_end = elevs[-1]
                self.elevation_unit = {
                    "Ft": "feet",
                    "Fath": "fathoms",
                    "Met": "meters",
                }[unit]

        # Map expedition and vessel
        expedition = evt.get("ExpExpeditionName")
        cruise_num = evt.get("AquCruiseNumber")
        if expedition and cruise_num:
            expedition = re.sub(r" *\(.*?\)", "", expedition)
            cruise_field_prgrm = f"{expedition} ({cruise_num})"
        else:
            cruise_field_prgrm = expedition or cruise_num

        platform = evt.get("AquVesselName")
        try:
            platform, launch = [s.strip() for s in platform.split(";")]
            launch_id = cruise_field_prgrm
            cruise_field_prgrm = None
        except (AttributeError, ValueError):
            launch = None
            launch_id = None

        if platform in (
            "Alvin",
            "DSV-4 (Sea Cliff)",
            "Jason II",
            "Makali’i",
            "Pisces IV",
            "Pisces V",
        ):
            launch = platform
            platform = None

        self.cruise_field_prgrm = cruise_field_prgrm
        self.platform_type = self.map_term(platform, "platformtypes")
        self.platform_name = platform
        self.platform_descr = None
        self.launch_platform_name = launch
        self.launch_id = launch_id
        self.launch_type_name = self.map_term(launch, "launchtypes")

        # Map collector
        collectors = []
        for row in evt.grid("ColParticipantRef_tab").add_columns():
            if row["ColParticipantRole_tab"] == "Collector":
                party = row["ColParticipantRef_tab"]
                for key in ["NamFullName", "NamOrganisation"]:
                    name = party[key]
                    if name:
                        collectors.append(name)
                        break
        self.collector = oxford_comma(collectors)
        self.collector_detail = None

        dates = [
            evt.get("ColDateVisitedFrom"),
            evt.get("ColDateVisitedTo"),
        ]
        dates = [d for d in dates if d]
        # SESAR limitation: SESAR does not support dates before 1900,
        # so filter any collection dates that predate that year
        if dates and all((d.year >= 1900 for d in dates)):
            # Dates must be datetimes to validate
            self.collection_start_date = str(dates[0].min_value) + "T00:00:00"
            self.collection_end_date = str(dates[-1].min_value) + "T00:00:00"
            for attr in ("day", "month", "year"):
                if getattr(dates[0], attr) is not None:
                    self.collection_date_precision = attr
                    break

        coll, contact = {
            "Gems": ("Gem", "featherr@si.edu"),
            "Minerals": ("Mineral", "pohwatp@swi.edu"),
            "Rock & Ore Collections": ("Rock & Ore", "halel@si.edu"),
        }[data["CatCatalog"]]
        self.current_archive = f"National {coll} Collection, Smithsonian Institution"
        self.current_archive_contact = contact
        self.original_archive = None
        self.original_archive_contact = None

        self.sample_other_names = []
        for row in other_nums:
            if row["CatOtherNumbersType_tab"] not in ("Accession number", "IGSN"):
                self.sample_other_names.append(
                    {"sample_other_name": row["CatOtherNumbersValue_tab"]}
                )

        ezid = data.grid("AdmGUIDValue_tab")[{"AdmGUIDType_tab": "EZID"}][0][
            "AdmGUIDValue_tab"
        ]
        self.external_urls = []
        for url, desc in (
            (
                f"http://n2t.net/{ezid}",
                f"Smithsonian collections record for {self.name}",
            ),
        ):
            self.external_urls.append(
                {
                    "external_url": {
                        "url": url,
                        "description": desc,
                        "url_type": "regular URL",
                    }
                }
            )

    def _parse_sesar(self, data):
        if isinstance(data, str):
            if "<" in data:
                data = data.encode("utf-8")
            else:
                data = IGSN(data)

        if isinstance(data, IGSN):
            resp = self.bot.display(data)
            if resp.status_code != 200:
                raise ValueError(f"Invalid IGSN: {data}")
            data = resp.content

        # Fix incorrectly escaped tags
        content = re.sub(rb"&amp;lt;(/?[a-z_]+)&amp;gt;", rb"<\1>", data)

        # Preserve the original XML in verbatim
        self.verbatim = data.decode("utf-8")

        dct = _xml_to_dict(etree.fromstring(content))["samples"][0]["sample"]
        for key, val in dct.items():
            setattr(self, key, val if val else None)

        # Convert collection dates to datetimes if necessary
        if self.collection_start_date and ":" not in self.collection_start_date:
            self.collection_start_date += "T00:00:00"
        if self.collection_end_date and ":" not in self.collection_end_date:
            self.collection_end_date += "T00:00:00"

    def _to_emu(self, **kwargs):
        """Formats record for EMu"""
        raise NotImplementedError("to_emu")

    def _sortable(self):
        """Returns a sortable version of the object"""
        return self.igsn

    @staticmethod
    def _format_range(grid, fields):
        vals = {}
        for row in grid:
            vals[" > ".join([row[f] for f in fields if row[f]])] = None
        if vals:
            vals = list(vals)
            if len(vals) > 1:
                return f"{vals[0]} to {vals[-1]}"
            return vals[0]


def _xml_to_dict(xml, dct=None):
    if dct is None:
        dct = {}
    if xml.text and xml.text.strip():
        dct[xml.tag] = html.unescape(xml.text)
    elif xml.tag in ["external_urls", "samples", "sample_other_names"]:
        dct.setdefault(xml.tag, [])
        for child in xml:
            dct[xml.tag].append({})
            _xml_to_dict(child, dct[xml.tag][-1])
    else:
        dct[xml.tag] = {}
        for child in xml:
            _xml_to_dict(child, dct[xml.tag])
    return dct


def prune_empty_nodes(xml):
    for child in xml:
        # Empty nodes are allowed in classification
        if not str(child.tag).endswith("classification"):
            if not child.text and not len(child):
                child.getparent().remove(child)
            prune_empty_nodes(child)
    return xml


def lookup_igsn(igsn):
    return str(igsn).split("/")[-1]


def display_igsn(igsn, prefix=""):
    return f"{prefix}/{igsn}".lstrip("/")
