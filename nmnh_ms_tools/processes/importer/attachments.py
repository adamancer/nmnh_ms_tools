"""Manage attachments to other modules during imports"""

from copy import deepcopy

from xmu import is_tab


class Attachment:
    """Template for managing attachments to other modules"""

    irns = {}
    fields = []

    def __init__(self, rec):
        self.rec = deepcopy(rec)

    def __str__(self):
        return str(self.rec)

    def to_emu(self):
        # Return irn-only record if an irn is supplied manually
        if isinstance(self.rec, int):
            return {"irn": self.rec}
        if "irn" in self.rec:
            return self.rec
        # Map to irn
        try:
            irn = self.__class__.irns[str(self)]
            if irn:
                return {"irn": int(irn)}
        except KeyError:
            self.__class__.irns[str(self)] = None
        rec = deepcopy(self.rec)
        if not self.fields:
            return rec
        for field in self.fields:
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
        "AquDepthFromMet",
        "AquDepthFromModifier",
        "AquDepthToMet",
        "AquDepthToModifier",
        "AquDepthDetermination",
        "AquVerbatimDepth",
        "AquBottomDepthFromMet",
        "AquBottomDepthFromModifier",
        "AquBottomDepthToMet",
        "AquBottomDepthToModifier",
        "AquBottomDepthDetermination",
        "AquVerbatimBottomDepth",
        "DepSourceOfSample",
        # Elevation
        "TerElevationFromMet",
        "TerElevationFromModifier",
        "TerElevationToMet",
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
        "LatLatitude_nesttab",
        "LatLongitudeVerbatim_nesttab",
        "LatLongitude_nesttab",
        "LatRadiusNumeric_tab",
        "LatRadiusUnit_tab",
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
