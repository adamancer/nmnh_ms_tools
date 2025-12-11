"""Manage attachments to other modules during imports"""

from copy import deepcopy
from warnings import warn

from xmu import is_tab


class Attachment:
    """Template for managing attachments to other modules"""

    irns = {}
    fields = []
    unit_conversion_fields = []

    def __init__(self, rec, irns=None):
        # Check for errors in field lists
        for fields in self.unit_conversion_fields:
            for field in fields:
                if field in self.fields:
                    raise ValueError(
                        f"{repr(field)} appears in both {self.__class__.__name}.fields"
                        f" and {self.__class__.__name}.unit_conversion_fields"
                    )

        self.rec = deepcopy(rec)
        if irns:
            self.__class__.irns = irns

    def __str__(self):
        return str(self.rec)

    def to_emu(self):
        """Maps the record in the attachment to EMu

        Returns
        -------
        dict
            the attachment formatted for EMu
        """
        # Return irn-only record if an irn is supplied manually
        if isinstance(self.rec, int):
            return {"irn": self.rec}
        if "irn" in self.rec:
            return {"irn": self.rec["irn"]}
        # Map value to irn
        try:
            irn = self.__class__.irns[str(self)]
            if irn:
                return {"irn": int(irn)}
        except KeyError:
            self.__class__.irns[str(self)] = None
            if isinstance(self.rec, str):
                warn(f"Unmapped string attachment: {repr(self.rec)}")
        # Map data
        rec = deepcopy(self.rec)
        if not self.fields:
            return rec
        for field in self.fields:
            rec.setdefault(field, [] if is_tab(field) else None)
        # EMu includes conversions for some fields, like depths or coordinates, that
        # are populated when the record is created. These will prevent records
        # being matched during import. To get around this, we'll go through a list
        # of equivalent fields for different units. If any are populated, remove the
        # blank fields. If none are, include all related fields as blanks.
        for fields in self.unit_conversion_fields:
            vals = {f: rec.get(f) for f in fields}
            if any(vals.values()):
                for key, val in vals.items():
                    if not val:
                        try:
                            del rec[key]
                        except KeyError:
                            pass
            else:
                for field in fields:
                    rec.setdefault(field, [] if is_tab(field) else None)
        return {f: rec[f] for f in sorted(rec)}


class Location(Attachment):
    """Manages attachments to elocations"""

    irns = {}
    fields = [f"LocLevel{i}" for i in range(1, 9)]

    def __str__(self):
        vals = [self.rec.get(f) for f in self.fields]
        while vals and not vals[-1]:
            vals = vals[:-1]
        return " - ".join(vals)


class CollectionEvent(Attachment):
    """Manages attachments to ecollectionevents"""

    irns = {}
    fields = [
        # Locality (1)
        "LocRecordClassification",
        "ColSiteVisitNumbers_tab",
        "LocSiteStationNumber",
        "LocSiteNumberSource",
        "LocSiteName_tab",
        "LocOcean",
        "LocSeaGulf",
        "LocBaySound",
        "LocContinent",
        "LocCountry",
        "LocProvinceStateTerritory",
        "LocDistrictCountyShire",
        "LocTownship",
        "LocNoFurtherLocalityData",
        "LocPreciseLocation",
        # Locality (2)
        "LocArchipelago",
        "LocIslandGrouping",
        "LocIslandName",
        "LocMiningDistrict",
        "LocMineName",
        "LocGeomorphologicalLocation",
        "LocGeologicSetting",
        "LocSiteParentRef",
        "LocSiteOwnerRef_tab",
        "LocJurisdiction",
        # Volcano (1)
        "VolVolcanoNumber",
        "VolVolcanoName",
        "VolSubfeature",
        "VolEruptionNotes",
        "VolEruptionID",
        "VolEruptionDateTo",
        "VolEruptionDateFrom",
        "VolEruptionNotes",
        # Collection
        "ColDateVisitedFrom",
        "ColDateVisitedFromModifier",
        "ColDateVisitedConjunction",
        "ColDateVisitedTo",
        "ColDateVisitedToModifier",
        "ColTimeVisitedFrom0",
        "ColTimeVisitedFromModifier_tab",
        "ColTimeVisitedConjunction_tab",
        "ColTimeVisitedTo0",
        "ColTimeVisitedToModifier_tab",
        "ColVerbatimDate",
        "ColParticipantRef_tab",
        "ColParticipantEtAl",
        "ColParticipantRole_tab",
        # Exp/Method
        "ExpExpeditionName",
        "AquVesselName",
        "AquCruiseNumber",
        "ExpProjectNumber",
        "ExpStartDate",
        "ExpCompletionDate",
        "ColCollectionMethod",
        # Depth
        "AquDepthFromModifier",
        "AquDepthToModifier",
        "AquDepthDetermination",
        "AquVerbatimDepth",
        "AquBottomDepthFromModifier",
        "AquBottomDepthToModifier",
        "AquBottomDepthDetermination",
        "AquVerbatimBottomDepth",
        "DepSourceOfSample",
        # Elevation
        "TerElevationFromModifier",
        "TerElevationToModifier",
        "TerElevationDetermination",
        "TerVerbatimElevation",
        # Lat/Long
        "LatDatum_tab",
        "LatDetDate0",
        "LatDetSource_tab",
        "LatDeterminedByRef_tab",
        "LatGeometry_tab",
        "LatGeoreferencingNotes0",
        "LatLatLongDetermination_tab",
        "LatLatitudeVerbatim_nesttab",
        "LatLongitudeVerbatim_nesttab",
        "LatRadiusNumeric_tab",
        "LatRadiusUnit_tab",
        "LatRadiusVerbatim_tab",
        # Mapping (1)
        "MapUTMEastingFloat_tab",
        "MapUTMNorthingFloat_tab",
        "MapUTMZone_tab",
        "MapUTMDatum_tab",
        "MapUTMFalseEasting_tab",
        "MapUTMFalseNorthing_tab",
        "MapUTMMethod_tab",
        "MapUTMDeterminedByRef_tab",
        "MapUTMComment_tab",
        "MapOtherKind_tab",
        "MapOtherCoordA_tab",
        "MapOtherCoordB_tab",
        "MapOtherDatum_tab",
        "MapOtherSource_tab",
        "MapOtherMethod_tab",
        "MapOtherOffset_tab",
        "MapOtherDeterminedByRef_tab",
        "MapOtherComment_tab",
        # Mapping (2)
        "MapType",
        "MapScale",
        "MapName",
        "MapNumber",
        "MapCoords",
        "LocQUAD",
        "MapOriginalCoordinateSystem",
        # References
        "ColBibliographicRef_tab",
        # Contract/Permit
        "ColContractNumber_tab",
        "ColContractRecipientRef_tab",
        "ColContractDescription_tab",
        "ColPermitNumber_tab",
        "ColPermitIssuerRef_tab",
        "ColPermitDescription_tab",
        # Notes
        "NteText0",
        "NteDate0",
        "NteType_tab",
        "NteAttributedToRef_nesttab",
        "NteMetadata_tab",
        # Multimedia
        "MulMultiMediaRef_tab",
        # Admin
        "AdmGUIDIsPreferred_tab",
        "AdmGUIDType_tab",
        "AdmGUIDValue_tab",
    ]
    unit_conversion_fields = [
        ("AquBottomDepthFromFath", "AquBottomDepthFromFt", "AquBottomDepthFromMet"),
        ("AquBottomDepthToFath", "AquBottomDepthToFt", "AquBottomDepthToMet"),
        ("AquDepthFromFath", "AquDepthFromFt", "AquDepthFromMet"),
        ("AquDepthToFath", "AquDepthToFt", "AquDepthToMet"),
        ("LatLatitude_nesttab", "LatLatitudeDecimal_nesttab"),
        ("LatLongitude_nesttab", "LatLongitudeDecimal_nesttab"),
        ("TerElevationFromFt", "TerElevationFromMet"),
        ("TerElevationToFt", "TerElevationToMet"),
    ]
