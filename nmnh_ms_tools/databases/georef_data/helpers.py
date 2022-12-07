"""Defines helper functions for the associated database"""
import re

from lxml import etree
from shapely import wkb
from shapely.geometry import Polygon

from .database import Session, AlternativePolygons, PreferredLocalities
from ...utils import as_list, as_str


def get_alt_geometry(geoname_id):
    """Finds an alternative geometry for a GeoNames feature"""
    session = Session()
    row = (
        session.query(AlternativePolygons.geometry, AlternativePolygons.source)
        .filter(AlternativePolygons.geoname_id == geoname_id)
        .order_by(AlternativePolygons.fcode)
        .first()
    )

    # If no rows found, retry search on ID field
    if isinstance(geoname_id, int):
        row = (
            session.query(AlternativePolygons.geometry, AlternativePolygons.source)
            .filter(AlternativePolygons.id == geoname_id)
            .order_by(AlternativePolygons.fcode)
            .first()
        )

    session.close()
    if row:
        return wkb.loads(row.geometry), row.source
    return None, None


def get_preferred(name, country_code=None, admin_code_1=None, admin_code_2=None):
    """Gets the preferred feature for a major locality

    The idea here is to match what you would expect a person would
    conclude based on a locality name with limited context. For example,
    given the name Maine, a reasonable person would assume the name
    referred to the U.S. state even if country is not specified.
    """
    # Construct query
    query = [PreferredLocalities.site_name == name]
    # Add country to query
    if country_code:
        country = "%{}%".format(as_str(country_code))
        query.append(PreferredLocalities.country.like(country))
    else:
        query.append(PreferredLocalities.country == None)
    # Add state to query
    if admin_code_1:
        codes = as_list(admin_code_1)
        query.append(PreferredLocalities.state_province.in_(codes))
    else:
        query.append(PreferredLocalities.state_province == None)
    # Add county to query
    if admin_code_2:
        codes = as_list(admin_code_1)
        query.append(PreferredLocalities.county.in_(codes))
    else:
        query.append(PreferredLocalities.county == None)
    # Run query
    session = Session()
    result = session.query(PreferredLocalities.geonames_id).filter(*query).first()
    session.close()
    return result


def import_from_kml(fp):
    """Imports records from Google Earth KML file"""
    nsmap = {None: "http://www.opengis.net/kml/2.2"}
    root = etree.parse(fp)
    rows = []
    for placemark in root.findall(".//Placemark", namespaces=nsmap):
        name = placemark.find("name", namespaces=nsmap).text

        # Construct polygon from coordinates
        coords = placemark.find(".//coordinates", namespaces=nsmap).text
        xy = []
        for triple in coords.strip().split(" "):
            lng, lat, elev = [float(n) for n in triple.split(",")]
            xy.append((lng, lat))

        # Check name for id
        try:
            name, geoname_id = [s.strip(") ") for s in name.split("(")]
        except ValueError:
            geoname_id = name.upper().replace(" ", "_")

        # Add row
        rows.append(
            {
                "name": name,
                "geoname_id": geoname_id,
                "geometry": wkb.dumps(Polygon(xy)),
                "source": "Google Earth",
            }
        )

    session = Session()
    session.query(AlternativePolygons).filter_by(source="Google Earth").delete()
    session.commit()
    session.bulk_insert_mappings(AlternativePolygons, rows)
    session.commit()
    session.close()


def import_from_natural_earth():
    """Imports records from Natural Earth database file"""
    session = NaturalEarthSession()
    rows = []
    for row in session.query(GeoNamesToNaturalEarth):
        rows.append(
            {
                "name": row.name,
                "geoname_id": row.geonames_id,
                "geometry": row.geometry,
                "fcode": row.fcode,
                "source": "Natural Earth",
                "source_id": row.ne_id,
                "source_class": row.featurecla,
                "ogc_fid": row.ogc_fid,
                "wikidata_id": row.wikidataid,
            }
        )
    session.close()
    session = GeoNamesSession()
    session.bulk_insert_mappings(AlternativePolygons, rows)
    session.commit()
    session.close()


def composite_natural_earth():
    """Composites multiple features from Natural Earth into a single feature"""
    composites = {"Mediterranean Sea": ["Mediterranean Sea"]}
    session = NaturalEarthSession()
    rows = []
    for comp_name, names in composites.items():
        geoms = []
        for row in session.query(GeoNamesToNaturalEarth).filter(
            GeoNamesToNaturalEarth.name.in_(names)
        ):
            geoms.append(wkb.loads(row.geometry))
            GeoMetry(geoms[-1]).draw(title=row.name)
        composite = unary_union(geoms)
        rows.append(
            {
                "name": comp_name,
                "geometry": wkb.dumps(composite),
                "source": "Natural Earth",
                "source_class": "Composite",
            }
        )
        GeoMetry(composite).draw(geoms, title=comp_name)
    session.close()
    session = GeoNamesSession()
    session.bulk_insert_mappings(AlternativePolygons, rows)
    # session.commit()
    session.close()
