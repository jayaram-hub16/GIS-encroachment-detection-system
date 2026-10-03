"""
core/detector.py - Spatial GIS Encroachment & Discrepancy Detection Engine.

Performs topological geometry intersection, difference, and buffer analysis using Shapely
between registered Cadastral Land Parcels and Satellite-classified built structures to detect:
1. Boundary spillovers into neighboring private plots.
2. Trespasses on Municipal Public Roads and Government Revenue Land.
3. Unauthorized construction within eco-sensitive waterbody conservation buffer zones.
4. Zoning land use mismatches (e.g., agricultural land unlawfully paved with industrial sheds).
5. Building coverage & setback infringements.
"""

from __future__ import annotations
import uuid
from typing import List, Dict, Tuple, Optional
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

from .models import (
    LandParcel,
    DetectedStructure,
    EncroachmentFlag,
    EncroachmentType,
    SeverityLevel,
    DisputeStatus,
    LandUseType,
    OwnerType,
    MunicipalSurveyRegistry,
    calculate_polygon_area_sqm,
)


class EncroachmentDetector:
    """
    Automated spatial discrepancy and encroachment detection engine for municipal GIS surveys.
    """

    def __init__(
        self,
        registry: MunicipalSurveyRegistry,
        tolerance_sqm: float = 2.0,
        waterbody_buffer_meters: float = 30.0,
    ):
        self.registry = registry
        self.tolerance_sqm = tolerance_sqm
        self.waterbody_buffer_meters = waterbody_buffer_meters
        # 30 meters in approximate degrees:
        self.waterbody_buffer_deg = waterbody_buffer_meters / 111139.0

    def run_detection_scan(self) -> List[EncroachmentFlag]:
        """
        Executes a comprehensive GIS audit against all registered parcels and classified structures.
        Clears previous flags and populates the registry with newly identified infractions.
        """
        self.registry.clear_encroachments()
        new_flags: List[EncroachmentFlag] = []

        # 1. Identify and create Waterbody Conservation Buffer Zones
        water_parcels = [
            p for p in self.registry.parcels.values()
            if p.registered_land_use == LandUseType.WATER_BODY
        ]
        water_buffer_union = None
        if water_parcels:
            water_polys = [p.boundary for p in water_parcels]
            water_buffer_union = unary_union(water_polys).buffer(self.waterbody_buffer_deg)

        # 2. Iterate through each detected satellite structure
        for struct_id, structure in self.registry.structures.items():
            flags = self._analyze_structure(structure, water_buffer_union)
            for f in flags:
                self.registry.add_encroachment_flag(f)
                new_flags.append(f)

        # 3. Check for parcel-level land use & excessive ground coverage violations
        coverage_flags = self._analyze_parcel_coverage_and_zoning()
        for f in coverage_flags:
            self.registry.add_encroachment_flag(f)
            new_flags.append(f)

        return new_flags

    def _analyze_structure(
        self,
        structure: DetectedStructure,
        water_buffer_union: Optional[Polygon | MultiPolygon] = None,
    ) -> List[EncroachmentFlag]:
        flags: List[EncroachmentFlag] = []
        s_geom = structure.geometry

        # A. Check for Waterbody Conservation Buffer Infringement
        if water_buffer_union is not None and s_geom.intersects(water_buffer_union):
            infringement_geom = s_geom.intersection(water_buffer_union)
            infr_area = calculate_polygon_area_sqm(infringement_geom)

            if infr_area >= self.tolerance_sqm:
                flag = EncroachmentFlag(
                    flag_id=f"ENC-ECO-{uuid.uuid4().hex[:6].upper()}",
                    encroachment_type=EncroachmentType.WATERBODY_BUFFER_VIOLATION,
                    severity=SeverityLevel.CRITICAL,
                    encroached_geometry=infringement_geom,
                    encroached_area_sqm=infr_area,
                    suspected_violator_parcel_id=None,
                    violator_owner_name="Unauthorized Builder / Lakebed Encroacher",
                    affected_parcel_id="LAKE-BUFFER-RESERVE",
                    affected_owner_name="State Water Resources Department",
                    affected_land_use=LandUseType.CONSERVATION_BUFFER,
                    confidence=structure.confidence,
                    recommended_action=(
                        f"Immediate Stop-Work & Demolition Notice under Wetlands Conservation Rules. "
                        f"Infringes {round(infr_area, 1)} m² of statutory {self.waterbody_buffer_meters}m eco-buffer."
                    ),
                    estimated_penalty=infr_area * 35000.0,
                    status=DisputeStatus.DETECTED,
                )
                flags.append(flag)

        # B. Find primary hosting parcel (parcel with maximum intersection area)
        primary_parcel: Optional[LandParcel] = None
        max_overlap_area = 0.0

        for parcel in self.registry.parcels.values():
            if s_geom.intersects(parcel.boundary):
                inter_area = calculate_polygon_area_sqm(s_geom.intersection(parcel.boundary))
                if inter_area > max_overlap_area:
                    max_overlap_area = inter_area
                    primary_parcel = parcel

        # If structure is entirely on public land with no registered private parcel:
        if primary_parcel is None:
            # Check which public land parcel it sits on
            for parcel in self.registry.parcels.values():
                if s_geom.intersects(parcel.boundary):
                    overlap = s_geom.intersection(parcel.boundary)
                    overlap_area = calculate_polygon_area_sqm(overlap)
                    if overlap_area >= self.tolerance_sqm:
                        flags.append(
                            EncroachmentFlag(
                                flag_id=f"ENC-SQUAT-{uuid.uuid4().hex[:6].upper()}",
                                encroachment_type=EncroachmentType.GOVERNMENT_LAND_TRESPASS,
                                severity=SeverityLevel.CRITICAL if parcel.ownership.is_public_asset else SeverityLevel.HIGH,
                                encroached_geometry=overlap,
                                encroached_area_sqm=overlap_area,
                                suspected_violator_parcel_id=None,
                                violator_owner_name="Unidentified Squatter / Non-Permitted Structure",
                                affected_parcel_id=parcel.parcel_id,
                                affected_owner_name=parcel.ownership.full_name,
                                affected_land_use=parcel.registered_land_use,
                                confidence=structure.confidence,
                                recommended_action=(
                                    f"Eviction & Demolition Order under Municipal Land Protection Act. "
                                    f"Unauthorized structure covering {round(overlap_area, 1)} m² on {parcel.ownership.full_name}."
                                ),
                                estimated_penalty=overlap_area * parcel.assessed_market_rate_per_sqm * 0.35,
                                status=DisputeStatus.DETECTED,
                            )
                        )
            return flags

        # C. Spillover Analysis: Does structure cross outside primary_parcel.boundary?
        spillover_geom = s_geom.difference(primary_parcel.boundary)
        spillover_area = calculate_polygon_area_sqm(spillover_geom)

        if spillover_area >= self.tolerance_sqm:
            # Determine which adjacent parcels are invaded
            for adj_parcel in self.registry.parcels.values():
                if adj_parcel.parcel_id == primary_parcel.parcel_id:
                    continue

                if spillover_geom.intersects(adj_parcel.boundary):
                    invaded_part = spillover_geom.intersection(adj_parcel.boundary)
                    invaded_area = calculate_polygon_area_sqm(invaded_part)

                    if invaded_area >= self.tolerance_sqm:
                        is_gov = adj_parcel.ownership.is_public_asset
                        enc_type = (
                            EncroachmentType.GOVERNMENT_LAND_TRESPASS
                            if is_gov
                            else EncroachmentType.BOUNDARY_SPILLOVER
                        )

                        # Determine severity
                        if is_gov:
                            sev = SeverityLevel.CRITICAL if invaded_area > 30.0 else SeverityLevel.HIGH
                        else:
                            if invaded_area > 50.0:
                                sev = SeverityLevel.HIGH
                            elif invaded_area > 15.0:
                                sev = SeverityLevel.MEDIUM
                            else:
                                sev = SeverityLevel.LOW

                        # Penalty rate
                        rate = adj_parcel.assessed_market_rate_per_sqm
                        penalty = invaded_area * rate * (0.4 if is_gov else 0.15)

                        rec_action = (
                            f"Notice served to {primary_parcel.ownership.full_name} ({primary_parcel.survey_number}) "
                            f"for unauthorized {round(invaded_area, 1)} m² projection into "
                            f"{adj_parcel.ownership.full_name} ({adj_parcel.survey_number})."
                        )

                        flags.append(
                            EncroachmentFlag(
                                flag_id=f"ENC-SPIL-{uuid.uuid4().hex[:6].upper()}",
                                encroachment_type=enc_type,
                                severity=sev,
                                encroached_geometry=invaded_part,
                                encroached_area_sqm=invaded_area,
                                suspected_violator_parcel_id=primary_parcel.parcel_id,
                                violator_owner_name=primary_parcel.ownership.full_name,
                                affected_parcel_id=adj_parcel.parcel_id,
                                affected_owner_name=adj_parcel.ownership.full_name,
                                affected_land_use=adj_parcel.registered_land_use,
                                confidence=structure.confidence,
                                recommended_action=rec_action,
                                estimated_penalty=penalty,
                                status=DisputeStatus.DETECTED,
                            )
                        )

        # D. Setback infringement inside primary_parcel
        setback_envelope = primary_parcel.get_setback_boundary()
        if not setback_envelope.is_empty and s_geom.intersects(primary_parcel.boundary):
            inner_struct = s_geom.intersection(primary_parcel.boundary)
            setback_spill = inner_struct.difference(setback_envelope)
            setback_spill_area = calculate_polygon_area_sqm(setback_spill)

            if setback_spill_area > 8.0:
                flags.append(
                    EncroachmentFlag(
                        flag_id=f"ENC-SETB-{uuid.uuid4().hex[:6].upper()}",
                        encroachment_type=EncroachmentType.SETBACK_EXCESS,
                        severity=SeverityLevel.LOW if setback_spill_area < 25.0 else SeverityLevel.MEDIUM,
                        encroached_geometry=setback_spill,
                        encroached_area_sqm=setback_spill_area,
                        suspected_violator_parcel_id=primary_parcel.parcel_id,
                        violator_owner_name=primary_parcel.ownership.full_name,
                        affected_parcel_id=primary_parcel.parcel_id,
                        affected_owner_name=primary_parcel.ownership.full_name,
                        affected_land_use=primary_parcel.registered_land_use,
                        confidence=structure.confidence,
                        recommended_action=(
                            f"Setback non-compliance on parcel {primary_parcel.survey_number}. "
                            f"Building breaches mandatory {primary_parcel.mandatory_setback_meters}m boundary margin by {round(setback_spill_area, 1)} m²."
                        ),
                        estimated_penalty=setback_spill_area * 2500.0,
                        status=DisputeStatus.DETECTED,
                    )
                )

        return flags

    def _analyze_parcel_coverage_and_zoning(self) -> List[EncroachmentFlag]:
        flags: List[EncroachmentFlag] = []

        for parcel in self.registry.parcels.values():
            # Find all structures intersecting this parcel
            intersecting_structs = []
            for s in self.registry.structures.values():
                if s.geometry.intersects(parcel.boundary):
                    part = s.geometry.intersection(parcel.boundary)
                    intersecting_structs.append((s, part))

            if not intersecting_structs:
                continue

            total_built_area = sum(calculate_polygon_area_sqm(part) for s, part in intersecting_structs)

            # Check 1: Unauthorized Land Use (Agricultural / Eco zone turned into Built-Up)
            if parcel.registered_land_use in [LandUseType.AGRICULTURAL, LandUseType.PUBLIC_PARK]:
                if total_built_area > 50.0:  # Substantial building on non-buildable zone
                    union_built = unary_union([part for s, part in intersecting_structs])
                    flags.append(
                        EncroachmentFlag(
                            flag_id=f"ENC-ZONE-{uuid.uuid4().hex[:6].upper()}",
                            encroachment_type=EncroachmentType.UNAUTHORIZED_LAND_USE,
                            severity=SeverityLevel.HIGH,
                            encroached_geometry=union_built,
                            encroached_area_sqm=total_built_area,
                            suspected_violator_parcel_id=parcel.parcel_id,
                            violator_owner_name=parcel.ownership.full_name,
                            affected_parcel_id=parcel.parcel_id,
                            affected_owner_name=parcel.ownership.full_name,
                            affected_land_use=parcel.registered_land_use,
                            confidence=0.94,
                            recommended_action=(
                                f"Unauthorized commercial/residential construction ({round(total_built_area, 1)} m²) "
                                f"detected on designated {parcel.registered_land_use.value} zone without CLU (Change of Land Use) clearance."
                            ),
                            estimated_penalty=total_built_area * 10000.0,
                            status=DisputeStatus.DETECTED,
                        )
                    )

            # Check 2: Ground Coverage Exceeded (FAR / Coverage violation)
            max_allowed = parcel.max_allowed_built_area
            if total_built_area > max_allowed + 10.0:
                excess_area = total_built_area - max_allowed
                flags.append(
                    EncroachmentFlag(
                        flag_id=f"ENC-COVR-{uuid.uuid4().hex[:6].upper()}",
                        encroachment_type=EncroachmentType.SETBACK_EXCESS,
                        severity=SeverityLevel.MEDIUM,
                        encroached_geometry=parcel.boundary,
                        encroached_area_sqm=excess_area,
                        suspected_violator_parcel_id=parcel.parcel_id,
                        violator_owner_name=parcel.ownership.full_name,
                        affected_parcel_id=parcel.parcel_id,
                        affected_owner_name=parcel.ownership.full_name,
                        affected_land_use=parcel.registered_land_use,
                        confidence=0.91,
                        recommended_action=(
                            f"Ground coverage ratio exceeded on {parcel.survey_number}. Permitted: {round(max_allowed, 1)} m² "
                            f"({int(parcel.max_coverage_ratio*100)}%), Actual: {round(total_built_area, 1)} m²."
                        ),
                        estimated_penalty=excess_area * 5000.0,
                        status=DisputeStatus.DETECTED,
                    )
                )

        return flags

    def analyze_arbitrary_polygon(
        self,
        polygon_coords: List[List[float]],
        claimed_parcel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Interactive Real-Time Analysis:
        Allows municipal surveyors to draw or test an arbitrary geometry on the map
        and instantly verify if it encroaches on any registered cadastre or buffer zone.
        """
        poly = Polygon(polygon_coords)
        if not poly.is_valid:
            poly = poly.buffer(0)

        area = calculate_polygon_area_sqm(poly)
        intersections = []

        for p_id, parcel in self.registry.parcels.items():
            if poly.intersects(parcel.boundary):
                inter = poly.intersection(parcel.boundary)
                inter_area = calculate_polygon_area_sqm(inter)
                if inter_area > 0.5:
                    is_violation = (claimed_parcel_id is not None and p_id != claimed_parcel_id)
                    intersections.append({
                        "parcel_id": p_id,
                        "survey_number": parcel.survey_number,
                        "owner_name": parcel.ownership.full_name,
                        "is_public_asset": parcel.ownership.is_public_asset,
                        "land_use": parcel.registered_land_use.value,
                        "overlap_sqm": round(inter_area, 2),
                        "percentage_of_drawn": round((inter_area / max(area, 1e-6)) * 100, 1),
                        "is_potential_encroachment": is_violation,
                    })

        return {
            "drawn_area_sqm": round(area, 2),
            "intersects_count": len(intersections),
            "intersections": intersections,
            "has_encroachment": any(i["is_potential_encroachment"] for i in intersections),
        }
