"""
core - Municipal GIS Encroachment Detection System.
"""

from .models import (
    OwnerType,
    LandUseType,
    EncroachmentType,
    SeverityLevel,
    DisputeStatus,
    OwnershipRecord,
    LandParcel,
    DetectedStructure,
    EncroachmentFlag,
    MunicipalSurveyRegistry,
    calculate_polygon_area_sqm,
)
from .classifier import LandCoverClassifier
from .detector import EncroachmentDetector
from .dataset_generator import build_default_municipal_dataset
from .report_generator import MunicipalReportGenerator

__all__ = [
    "OwnerType",
    "LandUseType",
    "EncroachmentType",
    "SeverityLevel",
    "DisputeStatus",
    "OwnershipRecord",
    "LandParcel",
    "DetectedStructure",
    "EncroachmentFlag",
    "MunicipalSurveyRegistry",
    "calculate_polygon_area_sqm",
    "LandCoverClassifier",
    "EncroachmentDetector",
    "build_default_municipal_dataset",
    "MunicipalReportGenerator",
]
