"""Defines helper functions for the associated database"""

import re

from lxml import etree
from shapely import equals, from_wkb, wkb
from shapely.geometry import Polygon
from shapely.ops import linemerge

from .database import (
    Session,
    AlternativePolygons,
    NaturalEarthCombined,
    PreferredLocalities,
)
from ..natural_earth.database import (
    Session as NaturalEarthSession,
    Counties,
    Countries,
    GeographicRegions,
    Lakes,
    LakesAustralia,
    LakesEurope,
    LakesNorthAmerica,
    ParksAndProtectedLands,
    PopulatedPlaces,
    Playas,
    Reefs,
    RiversAustralia,
    RiversEurope,
    RiversNorthAmerica,
    MarineRegions,
    MinorIslands,
    Ocean,
    StatesProvinces,
)
from ...tools.geographic_operations import GeoMetry
from ...utils import as_list, as_str


def get_alt_geometry(geoname_id):
    """Finds an alternative geometry for a GeoNames feature"""
    session = Session()
    row = (
        session.query(AlternativePolygons.geometry, AlternativePolygons.source)
        .filter(AlternativePolygons.gn_id == geoname_id)
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
            lng, lat, _ = [float(n) for n in triple.split(",")]
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


def composite_natural_earth():
    """Composites multiple features from Natural Earth into a single feature"""
    composites = {"Mediterranean Sea": ["Mediterranean Sea"]}
    session = NaturalEarthSession()
    rows = []
    for comp_name, names in composites.items():
        geoms = []
        for row in session.query(NaturalEarthCombined).filter(
            NaturalEarthCombined.name.in_(names)
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
    session = Session()
    session.bulk_insert_mappings(AlternativePolygons, rows)
    session.commit()
    session.close()


def fill_natural_earth_combined_table():
    """Combines relevant 10 m Natural Earth tables into a single table"""
    session = NaturalEarthSession()

    attrs = (
        "name",
        "name_alt",
        "name_en",
        "gn_id",
        "ogc_fid",
        "wikidataid",
        "ne_id",
        "GEOMETRY",
    )

    rows = []
    for table in (
        Counties,
        Countries,
        GeographicRegions,
        Lakes,
        LakesAustralia,
        LakesEurope,
        LakesNorthAmerica,
        ParksAndProtectedLands,
        PopulatedPlaces,
        Playas,
        Reefs,
        RiversAustralia,
        RiversEurope,
        RiversNorthAmerica,
        MarineRegions,
        MinorIslands,
        Ocean,
        StatesProvinces,
    ):
        for row in session.query(table):
            rowdict = {"table": table.__name__}
            for attr in attrs:
                try:
                    rowdict[attr] = getattr(row, attr)
                except AttributeError:
                    rowdict[attr] = None

            rowdict["ogc_fid"] = "{table}-{ogc_fid}".format(**rowdict)
            if rowdict["gn_id"] and str(rowdict["gn_id"]).startswith("-"):
                rowdict["gn_id"] = None
            rows.append(rowdict)

    session.close()

    session = Session()
    session.bulk_insert_mappings(NaturalEarthCombined, rows)
    session.commit()
    session.close()


def fill_alternative_polygons_table():
    session = Session()

    session.query(AlternativePolygons).delete(synchronize_session=False)
    session.commit()

    # Group by GeoNames ID
    grouped = {}
    for row in session.query(NaturalEarthCombined):
        if row.gn_id and row.GEOMETRY:
            grouped.setdefault(row.gn_id, []).append(row)

    updates = []
    for gn_id, rows in grouped.items():

        geoms = [from_wkb(r.GEOMETRY) for r in rows]
        name = rows[0].name

        row = {
            "name": name.title() if name.isupper() else name,
            "gn_id": gn_id,
            "geometry": geoms[0],
            "fcode": rows[0].fcode,
            "source": "Natural Earth",
        }

        # Combine geometries if multiple are assigned the same ID
        for i, geom in enumerate(geoms[1:]):
            if not equals(geom, geoms[i - 1]):

                # Combine lines
                if all(["Line" in g.__class__.__name__ for g in geoms]):
                    while "MultiLineString" in {g.__class__.__name__ for g in geoms}:
                        geoms_ = []
                        for geom in geoms:
                            try:
                                geoms_.extend(geom.geoms)
                            except AttributeError:
                                geoms_.append(geom)
                        geoms = geoms_
                    row["geometry"] = GeoMetry(linemerge(geoms), crs=4326)

                # Combine other shapes
                else:
                    row["geometry"] = GeoMetry(geoms[0], crs=4326).combine(geoms[1:])

                break

        row["geometry"] = row["geometry"].wkb
        updates.append(row)

    session.bulk_insert_mappings(AlternativePolygons, updates)
    session.commit()
    session.close()
