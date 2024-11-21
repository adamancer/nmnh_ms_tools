"""Defines methods for depicting simple sites as KML"""

import logging
import os

from lxml import etree

from ...utils import mutable


logger = logging.getLogger(__name__)


class Kml:
    """Writes KML file summarizing a georeference"""

    def __init__(self, max_radius_km=2000):
        self.max_radius_km = max_radius_km
        self.nsmap = {None: "http://www.opengis.net/kml/2.2"}
        self.root = etree.Element("kml", nsmap=self.nsmap)
        self.doc = etree.SubElement(self.root, "Document")
        # Define attribute to track sites that have been added already
        self.sites = []
        self._added = []
        # Polygon for related sites
        line = {"width": 10}
        poly = None
        self.add_style("related", line=line, poly=poly)
        # Polygon for measured sites
        line = {"width": 10, "color": "501400FF"}
        poly = None
        self.add_style("measured", line=line, poly=poly)
        # Polygon for the primary site
        line = {"width": 2, "color": "50F00014"}
        poly = None
        self.add_style("final", line=line, poly=poly)
        # Line for rivers
        # line = {"width": 50, "color": "50F00014"}
        # poly = None
        # self.add_style("river", line=line, poly=poly)

    def add_site(self, site, style, name=None, desc=None):
        """Adds a site to the KML file"""
        # Linear features are always rivers
        # if site.geom_type == "LineString":
        #    style = "river"
        site = site.copy()
        with mutable(site):
            site.geometry = site.geometry.to_crs(4326)
        self.add_placemark(site, style, name=name, desc=desc)
        try:
            for rel in site.related_sites:
                self.add_placemark(rel, "related")
        except AttributeError:
            pass
        return self

    def is_new(self, site):
        """Tests if site is new"""
        centroid = site.centroid
        point = (centroid.y, centroid.x, site.radius_km)
        if not self._added or point not in self._added[1:]:
            self.sites.append(site)
            self._added.append(point)
            return True
        return False

    def add_style(self, style_id, line=None, poly=None):
        """Adds a style to the KML file"""
        if line or poly:
            style = etree.SubElement(self.doc, "Style")
            style.attrib["id"] = style_id
            # Apply line styles
            if line is not None:
                line_style = etree.SubElement(style, "LineStyle")
                for key, val in line.items():
                    etree.SubElement(line_style, key).text = str(val)
            # Apply polygon styles
            if poly is not None:
                poly_style = etree.SubElement(style, "PolyStyle")
                for key, val in poly.items():
                    etree.SubElement(poly_style, key).text = str(val)
            return style

    def add_placemark(self, site, style, name=None, desc=None):
        """Adds a placemark to the KML file"""
        if self.is_new(site):
            placemark = etree.SubElement(self.doc, "Placemark")
            # Add name to placemark
            name_ = etree.SubElement(placemark, "name")
            name_.text = site.summarize() if name is None else name
            # Add description to placemark
            description = etree.SubElement(placemark, "description")
            if desc is None:
                attributes = [
                    "location_id",
                    "site_source",
                    "site_num",
                    "site_kind",
                    "centroid",
                    "radius_km",
                    "continent",
                    "country",
                    "state_province",
                    "county",
                    "island",
                    "island_group",
                    "mine",
                    "volcano",
                    "ocean",
                    "sea_gulf",
                    "bay_sound",
                    "water_body",
                    "locality",
                    "georeference_protocol",
                    "georeference_remarks",
                ]
                metadata = site.to_html(attributes)
                desc = metadata
            description.text = desc
            # Add style
            style_url = etree.SubElement(placemark, "styleUrl")
            style_url.text = "#" + style.lstrip("#")
            # Add multigeometry
            multigeometry = etree.SubElement(placemark, "MultiGeometry")
            # Add centroid
            point = etree.SubElement(multigeometry, "Point")
            coordinates = etree.SubElement(point, "coordinates")
            centroid = site.centroid
            coordinates.text = f"{centroid.x}, {centroid.y}"
            # Add radius
            if site.radius_km is not None:
                if site.geom_type == "LineString":
                    self.add_line(multigeometry, site)
                else:
                    self.add_outline(multigeometry, site)
        return self

    def add_outline(self, parent, site):
        """Adds a box to the KML file"""
        # Large outlines confuse the Google Earth, so do not plot those
        if self.max_radius_km and site.radius_km > self.max_radius_km:
            return self

        drawable = site.geometry.drawable
        try:
            geoms = drawable.geoms
        except AttributeError:
            geoms = [drawable]

        for geom in geoms:
            # Construct elements
            polygon = etree.SubElement(parent, "Polygon")
            extrude = etree.SubElement(polygon, "extrude")
            altitude_mode = etree.SubElement(polygon, "altitudeMode")
            outer_boundary_is = etree.SubElement(polygon, "outerBoundaryIs")
            linear_ring = etree.SubElement(outer_boundary_is, "LinearRing")
            coordinates = etree.SubElement(linear_ring, "coordinates")
            # Populate elements
            extrude.text = "1"
            altitude_mode.text = "relativeToGround"
            try:
                coordinates.text = " ".join(
                    ["{0},{1}".format(*pt) for pt in geom.exterior.coords]
                )
            except AttributeError:
                coordinates.text = " ".join(
                    ["{0},{1}".format(*pt) for pt in geom.coords]
                )
        return self

    def add_line(self, parent, site):
        """Adds a box to the KML file"""
        # Construct elements
        linestring = etree.SubElement(parent, "LineString")
        extrude = etree.SubElement(linestring, "extrude")
        tessellate = etree.SubElement(linestring, "tessellate")
        altitude_mode = etree.SubElement(linestring, "altitudeMode")
        coordinates = etree.SubElement(linestring, "coordinates")
        # Populate elements
        extrude.text = "1"
        tessellate.text = "1"
        altitude_mode.text = "relativeToGround"
        mask = "{0},{1}"
        coordinates.text = " ".join([mask.format(*p) for p in site.coords])
        return self

    def save(self, fp):
        """Saves the KML file to the given path"""
        try:
            os.makedirs(os.path.dirname(fp))
        except OSError:
            pass
        with open(fp, "wb") as f:
            f.write(etree.tostring(self.root, pretty_print=True))


def write_kml(fp, sites):
    """Writes a simple KML file from a list of sites"""
    kml = Kml(max_radius_km=None)
    for i, site in enumerate(sites):
        try:
            assert site.name
            kml.add_site(site, "candidate", name=site.name, desc="")
        except (AssertionError, AttributeError):
            name = "site {}".format(i + 1)
            kml.add_site(site, "candidate", name=name, desc="")
    kml.save(fp)
