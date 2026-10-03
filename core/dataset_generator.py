"""
core/dataset_generator.py - Generates realistic Municipal Cadastral & Satellite GIS Datasets.

Constructs realistic urban cadastral layouts containing:
- Registered private residential, commercial, and agricultural land parcels.
- Municipal arterial roads, public green parks, and revenue department reserves.
- Eco-sensitive lake conservation buffer zones.
- Simulated satellite-detected physical structures reflecting real-world survey violations:
  * Public road encroachments.
  * Neighboring private boundary disputes.
  * Eco-sensitive lake buffer violations.
  * Unauthorized industrial conversion of agricultural land.
  * Unregistered construction on government revenue land.
"""

from __future__ import annotations
from typing import Tuple
from shapely.geometry import Polygon

from .models import (
    LandParcel,
    OwnershipRecord,
    OwnerType,
    LandUseType,
    DetectedStructure,
    MunicipalSurveyRegistry,
)
from .classifier import LandCoverClassifier


def build_default_municipal_dataset(
    classifier: LandCoverClassifier | None = None,
) -> MunicipalSurveyRegistry:
    """
    Builds a comprehensive simulated municipal cadastral registry centered around
    Sector 7 Municipal Ward (Coordinates approx lat: 12.925, lon: 77.590).
    """
    if classifier is None:
        classifier = LandCoverClassifier()

    registry = MunicipalSurveyRegistry("Metro City Municipal Corporation - Sector 7 Ward")

    # Center origin
    base_lat = 12.9250
    base_lon = 77.5900
    # Step size: ~0.001 deg is ~111 meters
    d = 0.0008  # ~89 meters width/height

    # -------------------------------------------------------------
    # 1. REGISTERED CADASTRAL PARCELS
    # -------------------------------------------------------------

    # Parcel 1: Residential Plot 101 (Ramesh Kumar)
    p1_coords = [
        (base_lon, base_lat),
        (base_lon + d, base_lat),
        (base_lon + d, base_lat + d),
        (base_lon, base_lat + d),
        (base_lon, base_lat),
    ]
    p1 = LandParcel(
        parcel_id="PARCEL-RES-101",
        survey_number="SY-101/A",
        zone_name="Sector 7 Residential Layout",
        registered_land_use=LandUseType.RESIDENTIAL,
        ownership=OwnershipRecord(
            owner_id="OWN-101",
            full_name="Ramesh Kumar",
            owner_type=OwnerType.PRIVATE_CITIZEN,
            deed_number="DEED-2018-8421",
            tax_id="PROP-TAX-99101",
            contact_email="ramesh.kumar@outlook.com",
            contact_phone="+91-9845012345",
            registration_date="2018-04-12",
        ),
        boundary=Polygon(p1_coords),
        max_coverage_ratio=0.65,
        mandatory_setback_meters=2.5,
        assessed_market_rate_per_sqm=14500.0,
    )
    registry.register_parcel(p1)

    # Parcel 2: Residential Plot 102 (Priya Sharma) - directly north of Plot 101
    p2_coords = [
        (base_lon, base_lat + d),
        (base_lon + d, base_lat + d),
        (base_lon + d, base_lat + 2 * d),
        (base_lon, base_lat + 2 * d),
        (base_lon, base_lat + d),
    ]
    p2 = LandParcel(
        parcel_id="PARCEL-RES-102",
        survey_number="SY-102/B",
        zone_name="Sector 7 Residential Layout",
        registered_land_use=LandUseType.RESIDENTIAL,
        ownership=OwnershipRecord(
            owner_id="OWN-102",
            full_name="Priya Sharma",
            owner_type=OwnerType.PRIVATE_CITIZEN,
            deed_number="DEED-2019-1102",
            tax_id="PROP-TAX-99102",
            contact_email="priya.sharma@gmail.com",
            contact_phone="+91-9845023456",
            registration_date="2019-08-20",
        ),
        boundary=Polygon(p2_coords),
        max_coverage_ratio=0.65,
        mandatory_setback_meters=2.5,
        assessed_market_rate_per_sqm=14500.0,
    )
    registry.register_parcel(p2)

    # Parcel 3: Residential Plot 103 (Anil Verma) - directly north of Plot 102
    p3_coords = [
        (base_lon, base_lat + 2 * d),
        (base_lon + d, base_lat + 2 * d),
        (base_lon + d, base_lat + 3 * d),
        (base_lon, base_lat + 3 * d),
        (base_lon, base_lat + 2 * d),
    ]
    p3 = LandParcel(
        parcel_id="PARCEL-RES-103",
        survey_number="SY-103/C",
        zone_name="Sector 7 Residential Layout",
        registered_land_use=LandUseType.RESIDENTIAL,
        ownership=OwnershipRecord(
            owner_id="OWN-103",
            full_name="Anil Verma",
            owner_type=OwnerType.PRIVATE_CITIZEN,
            deed_number="DEED-2021-3904",
            tax_id="PROP-TAX-99103",
            contact_email="anil.verma@yahoo.com",
            contact_phone="+91-9845034567",
            registration_date="2021-02-14",
        ),
        boundary=Polygon(p3_coords),
        max_coverage_ratio=0.65,
        mandatory_setback_meters=2.5,
        assessed_market_rate_per_sqm=14500.0,
    )
    registry.register_parcel(p3)

    # Parcel 4: Municipal 80-Feet Main Arterial Road (Directly East of Plots 101, 102, 103)
    road_w = 0.0003  # ~33 meters wide road
    road_coords = [
        (base_lon + d, base_lat - 0.0005),
        (base_lon + d + road_w, base_lat - 0.0005),
        (base_lon + d + road_w, base_lat + 3.5 * d),
        (base_lon + d, base_lat + 3.5 * d),
        (base_lon + d, base_lat - 0.0005),
    ]
    p_road = LandParcel(
        parcel_id="PARCEL-ROAD-401",
        survey_number="SY-ROAD-80FT",
        zone_name="Municipal Public Right of Way",
        registered_land_use=LandUseType.PUBLIC_UTILITY_ROAD,
        ownership=OwnershipRecord(
            owner_id="OWN-MUNICIPAL-ENG",
            full_name="Metro City Municipal Corporation (Roads Wing)",
            owner_type=OwnerType.MUNICIPAL_CORPORATION,
            deed_number="PUB-ASSET-001",
            tax_id="MUNI-TAX-EXEMPT",
            contact_email="chief.engineer@metrocorp.gov",
            contact_phone="+91-80-22220000",
            registration_date="1985-01-01",
        ),
        boundary=Polygon(road_coords),
        max_coverage_ratio=0.0,
        mandatory_setback_meters=0.0,
        assessed_market_rate_per_sqm=28000.0,
    )
    registry.register_parcel(p_road)

    # Parcel 5: Commercial Complex Plot 201 (Apex Commercial Tower) - East of the 80ft Road
    c_start_lon = base_lon + d + road_w
    p_com_coords = [
        (c_start_lon, base_lat),
        (c_start_lon + 1.2 * d, base_lat),
        (c_start_lon + 1.2 * d, base_lat + 1.5 * d),
        (c_start_lon, base_lat + 1.5 * d),
        (c_start_lon, base_lat),
    ]
    p_com = LandParcel(
        parcel_id="PARCEL-COM-201",
        survey_number="SY-201/COMM",
        zone_name="Sector 7 Commercial High-Street",
        registered_land_use=LandUseType.COMMERCIAL,
        ownership=OwnershipRecord(
            owner_id="OWN-COM-APEX",
            full_name="Apex Realty Holdings Ltd",
            owner_type=OwnerType.COMMERCIAL_ENTITY,
            deed_number="DEED-2017-9099",
            tax_id="CORP-TAX-5522",
            contact_email="legal@apexrealty.com",
            contact_phone="+91-80-41005500",
            registration_date="2017-11-05",
        ),
        boundary=Polygon(p_com_coords),
        max_coverage_ratio=0.75,
        mandatory_setback_meters=3.0,
        assessed_market_rate_per_sqm=32000.0,
    )
    registry.register_parcel(p_com)

    # Parcel 6: Protected Municipal Lake & Wetlands (South of Commercial & Residential)
    lake_coords = [
        (base_lon - 0.0005, base_lat - 2.0 * d),
        (base_lon + 2.5 * d, base_lat - 2.0 * d),
        (base_lon + 2.5 * d, base_lat - 0.0006),
        (base_lon - 0.0005, base_lat - 0.0006),
        (base_lon - 0.0005, base_lat - 2.0 * d),
    ]
    p_lake = LandParcel(
        parcel_id="PARCEL-LAKE-501",
        survey_number="SY-LAKE-77",
        zone_name="Ecological Water Reserve",
        registered_land_use=LandUseType.WATER_BODY,
        ownership=OwnershipRecord(
            owner_id="OWN-WATER-DEPT",
            full_name="State Lake & Wetland Protection Authority",
            owner_type=OwnerType.WATER_RESOURCES_AUTHORITY,
            deed_number="ECO-GAZETTE-1974",
            tax_id="EXEMPT-ECO",
            contact_email="custodian@lakes.state.gov",
            contact_phone="+91-80-22998877",
            registration_date="1974-06-05",
        ),
        boundary=Polygon(lake_coords),
        max_coverage_ratio=0.0,
        mandatory_setback_meters=30.0,
        assessed_market_rate_per_sqm=50000.0,
    )
    registry.register_parcel(p_lake)

    # Parcel 7: Designated Agricultural Land (West fringe, Survey #301)
    agr_coords = [
        (base_lon - 1.2 * d, base_lat),
        (base_lon, base_lat),
        (base_lon, base_lat + 2 * d),
        (base_lon - 1.2 * d, base_lat + 2 * d),
        (base_lon - 1.2 * d, base_lat),
    ]
    p_agr = LandParcel(
        parcel_id="PARCEL-AGR-301",
        survey_number="SY-301/AGRI",
        zone_name="Green Belt Agricultural Periphery",
        registered_land_use=LandUseType.AGRICULTURAL,
        ownership=OwnershipRecord(
            owner_id="OWN-AGR-GOVIND",
            full_name="Govindappa & Heirs",
            owner_type=OwnerType.PRIVATE_CITIZEN,
            deed_number="DEED-1996-0331",
            tax_id="AGRI-TAX-101",
            contact_email="govindappa.farm@gmail.com",
            contact_phone="+91-9448011223",
            registration_date="1996-03-31",
        ),
        boundary=Polygon(agr_coords),
        max_coverage_ratio=0.10,  # Max 10% farm shed allowed
        mandatory_setback_meters=5.0,
        assessed_market_rate_per_sqm=8000.0,
    )
    registry.register_parcel(p_agr)

    # Parcel 8: State Government Revenue Land / Public Reserve (North East)
    gov_coords = [
        (c_start_lon, base_lat + 1.5 * d),
        (c_start_lon + 1.2 * d, base_lat + 1.5 * d),
        (c_start_lon + 1.2 * d, base_lat + 3.0 * d),
        (c_start_lon, base_lat + 3.0 * d),
        (c_start_lon, base_lat + 1.5 * d),
    ]
    p_gov = LandParcel(
        parcel_id="PARCEL-GOV-701",
        survey_number="SY-GOV-RES-04",
        zone_name="Government Revenue Department Land",
        registered_land_use=LandUseType.GOVERNMENT_RESERVE,
        ownership=OwnershipRecord(
            owner_id="OWN-GOV-REV",
            full_name="District Revenue Department (Tahsildar Custody)",
            owner_type=OwnerType.GOVERNMENT_REVENUE,
            deed_number="GOV-CADASTRE-FOLIO-12",
            tax_id="EXEMPT-STATE-GOV",
            contact_email="tahsildar.sector7@revenue.gov",
            contact_phone="+91-80-22114433",
            registration_date="1960-01-01",
        ),
        boundary=Polygon(gov_coords),
        max_coverage_ratio=0.0,
        mandatory_setback_meters=0.0,
        assessed_market_rate_per_sqm=22000.0,
    )
    registry.register_parcel(p_gov)

    # -------------------------------------------------------------
    # 2. SATELLITE-DETECTED STRUCTURES (FROM GIS CLASSIFIER)
    # -------------------------------------------------------------

    # Structure A: Compliant Residential Villa on Parcel 101 (Ramesh Kumar)
    # Perfectly fits inside parcel 101 with setbacks observed.
    s1_coords = [
        (base_lon + 0.00015, base_lat + 0.00015),
        (base_lon + 0.00065, base_lat + 0.00015),
        (base_lon + 0.00065, base_lat + 0.00065),
        (base_lon + 0.00015, base_lat + 0.00065),
        (base_lon + 0.00015, base_lat + 0.00015),
    ]
    # Classify spectral reflectance: Concrete rooftop
    clf_res = classifier.classify_spectral_profile(0.24, 0.22, 0.20, 0.27, 0.39)
    s1 = DetectedStructure(
        structure_id="STRUCT-SAT-101",
        geometry=Polygon(s1_coords),
        classified_land_use=LandUseType.RESIDENTIAL,
        confidence=clf_res["confidence"],
        spectral_metrics=clf_res["indices"],
    )
    registry.register_structure(s1)

    # Structure B: Boundary Spillover Dispute! (Parcel 102 spills into Parcel 103)
    # Priya Sharma's house on 102 extends 0.00012 deg (~13.3m) across northern line into Anil Verma's Plot 103!
    s2_coords = [
        (base_lon + 0.0001, base_lat + d + 0.0002),
        (base_lon + 0.0007, base_lat + d + 0.0002),
        (base_lon + 0.0007, base_lat + 2 * d + 0.00012),  # Crosses 2*d line into Parcel 103!
        (base_lon + 0.0001, base_lat + 2 * d + 0.00012),
        (base_lon + 0.0001, base_lat + d + 0.0002),
    ]
    clf_s2 = classifier.classify_spectral_profile(0.25, 0.23, 0.21, 0.28, 0.40)
    s2 = DetectedStructure(
        structure_id="STRUCT-SAT-102-DISPUTE",
        geometry=Polygon(s2_coords),
        classified_land_use=LandUseType.RESIDENTIAL,
        confidence=clf_s2["confidence"],
        spectral_metrics=clf_s2["indices"],
    )
    registry.register_structure(s2)

    # Structure C: Public Road Encroachment! (Apex Realty Commercial Complex)
    # Commercial tower on Parcel 201 built a concrete showroom/portico extending west into 80-ft Public Road!
    s3_coords = [
        (c_start_lon - 0.00014, base_lat + 0.0002),   # Overhangs 15m into PARCEL-ROAD-401!
        (c_start_lon + 0.0007, base_lat + 0.0002),
        (c_start_lon + 0.0007, base_lat + 0.0009),
        (c_start_lon - 0.00014, base_lat + 0.0009),
        (c_start_lon - 0.00014, base_lat + 0.0002),
    ]
    clf_s3 = classifier.classify_spectral_profile(0.28, 0.25, 0.22, 0.30, 0.45)
    s3 = DetectedStructure(
        structure_id="STRUCT-SAT-201-ROAD-TRESPASS",
        geometry=Polygon(s3_coords),
        classified_land_use=LandUseType.COMMERCIAL,
        confidence=clf_s3["confidence"],
        spectral_metrics=clf_s3["indices"],
    )
    registry.register_structure(s3)

    # Structure D: Eco-Sensitive Lake Buffer Encroachment!
    # Unauthorized banquet hall built inside the 30-meter buffer zone right at the edge of the lake
    lake_north_edge = base_lat - 0.0006
    s4_coords = [
        (base_lon + 0.0005, lake_north_edge - 0.00008),  # Intrudes directly into lake shoreline buffer
        (base_lon + 0.0011, lake_north_edge - 0.00008),
        (base_lon + 0.0011, lake_north_edge + 0.00015),
        (base_lon + 0.0005, lake_north_edge + 0.00015),
        (base_lon + 0.0005, lake_north_edge - 0.00008),
    ]
    clf_s4 = classifier.classify_spectral_profile(0.27, 0.24, 0.20, 0.29, 0.42)
    s4 = DetectedStructure(
        structure_id="STRUCT-SAT-501-LAKE-BUFFER",
        geometry=Polygon(s4_coords),
        classified_land_use=LandUseType.COMMERCIAL,
        confidence=clf_s4["confidence"],
        spectral_metrics=clf_s4["indices"],
    )
    registry.register_structure(s4)

    # Structure E: Illegal Industrial Shed on Agricultural Land (Parcel 301)
    # Huge concrete fabrication warehouse built without change of land use
    s5_coords = [
        (base_lon - 0.0010, base_lat + 0.0003),
        (base_lon - 0.0002, base_lat + 0.0003),
        (base_lon - 0.0002, base_lat + 0.0012),
        (base_lon - 0.0010, base_lat + 0.0012),
        (base_lon - 0.0010, base_lat + 0.0003),
    ]
    clf_s5 = classifier.classify_spectral_profile(0.31, 0.26, 0.21, 0.32, 0.48)
    s5 = DetectedStructure(
        structure_id="STRUCT-SAT-301-ILLEGAL-SHED",
        geometry=Polygon(s5_coords),
        classified_land_use=LandUseType.INDUSTRIAL,
        confidence=clf_s5["confidence"],
        spectral_metrics=clf_s5["indices"],
    )
    registry.register_structure(s5)

    # Structure F: Government Revenue Land Trespass (Squatter / Encroacher on PARCEL-GOV-701)
    # Unauthorized commercial truck yard and office on State Revenue property
    s6_coords = [
        (c_start_lon + 0.0002, base_lat + 1.5 * d + 0.0002),
        (c_start_lon + 0.0008, base_lat + 1.5 * d + 0.0002),
        (c_start_lon + 0.0008, base_lat + 1.5 * d + 0.0007),
        (c_start_lon + 0.0002, base_lat + 1.5 * d + 0.0007),
        (c_start_lon + 0.0002, base_lat + 1.5 * d + 0.0002),
    ]
    clf_s6 = classifier.classify_spectral_profile(0.26, 0.23, 0.20, 0.28, 0.41)
    s6 = DetectedStructure(
        structure_id="STRUCT-SAT-701-GOV-TRESPASS",
        geometry=Polygon(s6_coords),
        classified_land_use=LandUseType.COMMERCIAL,
        confidence=clf_s6["confidence"],
        spectral_metrics=clf_s6["indices"],
    )
    registry.register_structure(s6)

    return registry
