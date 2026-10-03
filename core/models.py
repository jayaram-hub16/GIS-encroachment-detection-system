"""
core/models.py - Object-Oriented Domain Models for Municipal GIS Encroachment Detection.

Provides robust OOP abstractions for:
- OwnershipRecord: Land title, owner classification, legal metadata.
- LandParcel: Cadastral boundary geometry (Shapely), zoning regulations, setbacks.
- DetectedStructure: Satellite-derived building footprints from GIS classification.
- EncroachmentFlag: Spatial & regulatory violation events with severity and municipal enforcement actions.
- MunicipalSurveyRegistry: In-memory/persistent registry managing cadastral records.
"""

from __future__ import annotations
import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
from shapely.ops import transform


class OwnerType(str, Enum):
    PRIVATE_CITIZEN = "PRIVATE_CITIZEN"
    COMMERCIAL_ENTITY = "COMMERCIAL_ENTITY"
    MUNICIPAL_CORPORATION = "MUNICIPAL_CORPORATION"
    GOVERNMENT_REVENUE = "GOVERNMENT_REVENUE"
    FOREST_DEPARTMENT = "FOREST_DEPARTMENT"
    WATER_RESOURCES_AUTHORITY = "WATER_RESOURCES_AUTHORITY"


class LandUseType(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    INDUSTRIAL = "INDUSTRIAL"
    AGRICULTURAL = "AGRICULTURAL"
    PUBLIC_UTILITY_ROAD = "PUBLIC_UTILITY_ROAD"
    PUBLIC_PARK = "PUBLIC_PARK"
    GOVERNMENT_RESERVE = "GOVERNMENT_RESERVE"
    WATER_BODY = "WATER_BODY"
    CONSERVATION_BUFFER = "CONSERVATION_BUFFER"


class EncroachmentType(str, Enum):
    BOUNDARY_SPILLOVER = "BOUNDARY_SPILLOVER"                   # Structure crosses into private neighbor's plot
    GOVERNMENT_LAND_TRESPASS = "GOVERNMENT_LAND_TRESPASS"       # Structure crosses onto municipal road / gov land
    WATERBODY_BUFFER_VIOLATION = "WATERBODY_BUFFER_VIOLATION"   # Structure inside eco-sensitive lake/river buffer
    UNAUTHORIZED_LAND_USE = "UNAUTHORIZED_LAND_USE"             # Concrete structure on agricultural/conservation land
    SETBACK_EXCESS = "SETBACK_EXCESS"                           # Construction inside mandatory property perimeter setback


class SeverityLevel(str, Enum):
    LOW = "LOW"             # < 10 sqm or minor setback fringe
    MEDIUM = "MEDIUM"       # 10 - 50 sqm overlap on private boundary
    HIGH = "HIGH"           # > 50 sqm or road easement trespass
    CRITICAL = "CRITICAL"   # Water reserve infringement or massive public land grab


class DisputeStatus(str, Enum):
    DETECTED = "DETECTED"
    NOTICE_SERVED = "NOTICE_SERVED"
    UNDER_FIELD_SURVEY = "UNDER_FIELD_SURVEY"
    LEGAL_PROCEEDING = "LEGAL_PROCEEDING"
    REGULARIZED = "REGULARIZED"
    RESOLVED = "RESOLVED"
    DISMISSED_FALSE_POSITIVE = "DISMISSED_FALSE_POSITIVE"


def calculate_polygon_area_sqm(geom: Polygon | MultiPolygon) -> float:
    """
    Calculate approximate surface area in square meters for WGS84 (lat/lon) geometries.
    Uses spherical approximation at the centroid latitude.
    1 deg latitude ~ 111,139 meters.
    1 deg longitude ~ 111,139 * cos(lat) meters.
    """
    if geom.is_empty:
        return 0.0
    centroid = geom.centroid
    lat_rad = math.radians(centroid.y)
    # Scale factors:
    m_per_deg_lat = 111139.0
    m_per_deg_lon = 111139.0 * math.cos(lat_rad)
    # Area in degree^2 * m_per_deg_lat * m_per_deg_lon
    return float(geom.area * m_per_deg_lat * m_per_deg_lon)


class OwnershipRecord:
    """Represents the legal cadastral title holder of a land parcel."""

    def __init__(
        self,
        owner_id: str,
        full_name: str,
        owner_type: OwnerType,
        deed_number: str,
        tax_id: str,
        contact_email: str = "survey.officer@metrocorp.gov",
        contact_phone: str = "+91-9876543210",
        registration_date: str = "2020-01-15",
    ):
        self.owner_id = owner_id
        self.full_name = full_name
        self.owner_type = owner_type if isinstance(owner_type, OwnerType) else OwnerType(owner_type)
        self.deed_number = deed_number
        self.tax_id = tax_id
        self.contact_email = contact_email
        self.contact_phone = contact_phone
        self.registration_date = registration_date

    @property
    def is_public_asset(self) -> bool:
        """Determines if the land belongs to municipal, state, or conservation bodies."""
        return self.owner_type in {
            OwnerType.MUNICIPAL_CORPORATION,
            OwnerType.GOVERNMENT_REVENUE,
            OwnerType.FOREST_DEPARTMENT,
            OwnerType.WATER_RESOURCES_AUTHORITY,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "full_name": self.full_name,
            "owner_type": self.owner_type.value,
            "deed_number": self.deed_number,
            "tax_id": self.tax_id,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "registration_date": self.registration_date,
            "is_public_asset": self.is_public_asset,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OwnershipRecord:
        return cls(
            owner_id=data["owner_id"],
            full_name=data["full_name"],
            owner_type=OwnerType(data["owner_type"]),
            deed_number=data["deed_number"],
            tax_id=data["tax_id"],
            contact_email=data.get("contact_email", ""),
            contact_phone=data.get("contact_phone", ""),
            registration_date=data.get("registration_date", ""),
        )


class LandParcel:
    """
    Represents an officially registered Cadastral Land Parcel with municipal survey boundaries.
    """

    def __init__(
        self,
        parcel_id: str,
        survey_number: str,
        zone_name: str,
        registered_land_use: LandUseType,
        ownership: OwnershipRecord,
        boundary: Polygon | MultiPolygon,
        max_coverage_ratio: float = 0.65,
        mandatory_setback_meters: float = 2.0,
        assessed_market_rate_per_sqm: float = 12000.0,
    ):
        self.parcel_id = parcel_id
        self.survey_number = survey_number
        self.zone_name = zone_name
        self.registered_land_use = (
            registered_land_use
            if isinstance(registered_land_use, LandUseType)
            else LandUseType(registered_land_use)
        )
        self.ownership = ownership
        self.boundary = boundary
        self.max_coverage_ratio = max_coverage_ratio
        self.mandatory_setback_meters = mandatory_setback_meters
        self.assessed_market_rate_per_sqm = assessed_market_rate_per_sqm

    @property
    def area_sqm(self) -> float:
        """Total parcel area in square meters."""
        return calculate_polygon_area_sqm(self.boundary)

    @property
    def max_allowed_built_area(self) -> float:
        """Maximum ground building footprint permissible under zoning regulations."""
        return self.area_sqm * self.max_coverage_ratio

    @property
    def centroid_coordinates(self) -> Tuple[float, float]:
        """Returns (latitude, longitude) of the parcel centroid."""
        c = self.boundary.centroid
        return (c.y, c.x)

    def get_setback_boundary(self) -> Polygon | MultiPolygon:
        """
        Computes the inner buildable envelope by buffering inward by the mandatory setback.
        """
        # Convert setback meters to degrees roughly:
        deg_offset = self.mandatory_setback_meters / 111139.0
        inner_geom = self.boundary.buffer(-deg_offset)
        return inner_geom if not inner_geom.is_empty else self.boundary

    def to_geojson_feature(self) -> Dict[str, Any]:
        """Serializes the parcel into standard GeoJSON Feature format."""
        return {
            "type": "Feature",
            "id": self.parcel_id,
            "geometry": mapping(self.boundary),
            "properties": {
                "parcel_id": self.parcel_id,
                "survey_number": self.survey_number,
                "zone_name": self.zone_name,
                "registered_land_use": self.registered_land_use.value,
                "area_sqm": round(self.area_sqm, 2),
                "max_allowed_built_area": round(self.max_allowed_built_area, 2),
                "max_coverage_ratio": self.max_coverage_ratio,
                "setback_meters": self.mandatory_setback_meters,
                "assessed_market_rate_sqm": self.assessed_market_rate_per_sqm,
                "ownership": self.ownership.to_dict(),
            },
        }

    @classmethod
    def from_geojson_feature(cls, feature: Dict[str, Any]) -> LandParcel:
        geom = shape(feature["geometry"])
        props = feature["properties"]
        owner = OwnershipRecord.from_dict(props["ownership"])
        return cls(
            parcel_id=props["parcel_id"],
            survey_number=props["survey_number"],
            zone_name=props.get("zone_name", "Municipal Central"),
            registered_land_use=LandUseType(props["registered_land_use"]),
            ownership=owner,
            boundary=geom,
            max_coverage_ratio=props.get("max_coverage_ratio", 0.65),
            mandatory_setback_meters=props.get("setback_meters", 2.0),
            assessed_market_rate_per_sqm=props.get("assessed_market_rate_sqm", 12000.0),
        )


class DetectedStructure:
    """
    Represents an actual built footprint detected from multi-spectral satellite GIS imagery classification.
    """

    def __init__(
        self,
        structure_id: str,
        geometry: Polygon | MultiPolygon,
        classified_land_use: LandUseType,
        confidence: float = 0.92,
        spectral_metrics: Optional[Dict[str, float]] = None,
        detected_date: Optional[str] = None,
    ):
        self.structure_id = structure_id
        self.geometry = geometry
        self.classified_land_use = (
            classified_land_use
            if isinstance(classified_land_use, LandUseType)
            else LandUseType(classified_land_use)
        )
        self.confidence = float(confidence)
        self.spectral_metrics = spectral_metrics or {}
        self.detected_date = detected_date or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def area_sqm(self) -> float:
        return calculate_polygon_area_sqm(self.geometry)

    def to_geojson_feature(self) -> Dict[str, Any]:
        return {
            "type": "Feature",
            "id": self.structure_id,
            "geometry": mapping(self.geometry),
            "properties": {
                "structure_id": self.structure_id,
                "classified_land_use": self.classified_land_use.value,
                "area_sqm": round(self.area_sqm, 2),
                "confidence": round(self.confidence, 4),
                "spectral_metrics": self.spectral_metrics,
                "detected_date": self.detected_date,
            },
        }


class EncroachmentFlag:
    """
    Represents a verified spatial or regulatory encroachment event identified by comparing
    cadastral records against actual GIS detected structures and land use.
    """

    def __init__(
        self,
        flag_id: str,
        encroachment_type: EncroachmentType,
        severity: SeverityLevel,
        encroached_geometry: Polygon | MultiPolygon,
        encroached_area_sqm: float,
        suspected_violator_parcel_id: Optional[str],
        violator_owner_name: Optional[str],
        affected_parcel_id: str,
        affected_owner_name: str,
        affected_land_use: LandUseType,
        confidence: float,
        recommended_action: str,
        estimated_penalty: float = 0.0,
        status: DisputeStatus = DisputeStatus.DETECTED,
        created_at: Optional[str] = None,
    ):
        self.flag_id = flag_id
        self.encroachment_type = (
            encroachment_type
            if isinstance(encroachment_type, EncroachmentType)
            else EncroachmentType(encroachment_type)
        )
        self.severity = (
            severity
            if isinstance(severity, SeverityLevel)
            else SeverityLevel(severity)
        )
        self.encroached_geometry = encroached_geometry
        self.encroached_area_sqm = float(encroached_area_sqm)
        self.suspected_violator_parcel_id = suspected_violator_parcel_id
        self.violator_owner_name = violator_owner_name or "Unknown / Unregistered Occupant"
        self.affected_parcel_id = affected_parcel_id
        self.affected_owner_name = affected_owner_name
        self.affected_land_use = (
            affected_land_use
            if isinstance(affected_land_use, LandUseType)
            else LandUseType(affected_land_use)
        )
        self.confidence = float(confidence)
        self.recommended_action = recommended_action
        self.estimated_penalty = estimated_penalty
        self.status = status if isinstance(status, DisputeStatus) else DisputeStatus(status)
        self.created_at = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flag_id": self.flag_id,
            "encroachment_type": self.encroachment_type.value,
            "severity": self.severity.value,
            "encroached_area_sqm": round(self.encroached_area_sqm, 2),
            "suspected_violator_parcel_id": self.suspected_violator_parcel_id,
            "violator_owner_name": self.violator_owner_name,
            "affected_parcel_id": self.affected_parcel_id,
            "affected_owner_name": self.affected_owner_name,
            "affected_land_use": self.affected_land_use.value,
            "confidence": round(self.confidence, 4),
            "recommended_action": self.recommended_action,
            "estimated_penalty": round(self.estimated_penalty, 2),
            "status": self.status.value,
            "created_at": self.created_at,
        }

    def to_geojson_feature(self) -> Dict[str, Any]:
        return {
            "type": "Feature",
            "id": self.flag_id,
            "geometry": mapping(self.encroached_geometry),
            "properties": self.to_dict(),
        }


class MunicipalSurveyRegistry:
    """
    Central repository modeling the Municipal Survey Department Cadastre.
    Maintains all registered land parcels, detected structures, and encroachment flags.
    """

    def __init__(self, municipality_name: str = "Metro City Municipal Corporation"):
        self.municipality_name = municipality_name
        self.parcels: Dict[str, LandParcel] = {}
        self.structures: Dict[str, DetectedStructure] = {}
        self.encroachment_flags: Dict[str, EncroachmentFlag] = {}

    def register_parcel(self, parcel: LandParcel) -> None:
        self.parcels[parcel.parcel_id] = parcel

    def register_structure(self, structure: DetectedStructure) -> None:
        self.structures[structure.structure_id] = structure

    def add_encroachment_flag(self, flag: EncroachmentFlag) -> None:
        self.encroachment_flags[flag.flag_id] = flag

    def clear_encroachments(self) -> None:
        self.encroachment_flags.clear()

    def get_parcel(self, parcel_id: str) -> Optional[LandParcel]:
        return self.parcels.get(parcel_id)

    def get_parcels_geojson(self) -> Dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [p.to_geojson_feature() for p in self.parcels.values()],
        }

    def get_structures_geojson(self) -> Dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [s.to_geojson_feature() for s in self.structures.values()],
        }

    def get_encroachments_geojson(self) -> Dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [f.to_geojson_feature() for f in self.encroachment_flags.values()],
        }

    def get_metrics_summary(self) -> Dict[str, Any]:
        total_parcels = len(self.parcels)
        total_structures = len(self.structures)
        total_flags = len(self.encroachment_flags)

        severity_counts = {sev.value: 0 for sev in SeverityLevel}
        type_counts = {t.value: 0 for t in EncroachmentType}
        total_encroached_area = 0.0
        total_penalties = 0.0

        for f in self.encroachment_flags.values():
            severity_counts[f.severity.value] += 1
            type_counts[f.encroachment_type.value] += 1
            total_encroached_area += f.encroached_area_sqm
            total_penalties += f.estimated_penalty

        # Count affected parcels
        violating_parcels = set(
            f.suspected_violator_parcel_id
            for f in self.encroachment_flags.values()
            if f.suspected_violator_parcel_id
        )

        return {
            "municipality_name": self.municipality_name,
            "total_parcels": total_parcels,
            "total_structures": total_structures,
            "total_encroachment_flags": total_flags,
            "total_violating_parcels": len(violating_parcels),
            "total_encroached_area_sqm": round(total_encroached_area, 2),
            "total_potential_penalties": round(total_penalties, 2),
            "severity_breakdown": severity_counts,
            "type_breakdown": type_counts,
        }
