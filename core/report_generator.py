"""
core/report_generator.py - Municipal Survey Department Audit & Legal Notice Generator.

Produces statutory legal notices, field inspection orders, and comprehensive audit reports
for municipal survey officers, town planning authorities, and judicial tribunals.
"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from .models import EncroachmentFlag, MunicipalSurveyRegistry, SeverityLevel


class MunicipalReportGenerator:
    """Generates statutory documentation for municipal survey enforcement."""

    def __init__(self, registry: MunicipalSurveyRegistry):
        self.registry = registry

    def generate_legal_notice(self, flag_id: str) -> Dict[str, Any]:
        """
        Generates a formal Statutory Show-Cause & Demolition Notice for a specific encroachment flag.
        """
        flag = self.registry.encroachment_flags.get(flag_id)
        if not flag:
            raise ValueError(f"Flag ID {flag_id} not found in municipal registry.")

        violating_parcel = (
            self.registry.get_parcel(flag.suspected_violator_parcel_id)
            if flag.suspected_violator_parcel_id
            else None
        )
        affected_parcel = self.registry.get_parcel(flag.affected_parcel_id)

        notice_ref = f"MUNI-SURVEY-NOT-{uuid.uuid4().hex[:8].upper()}"
        issue_date = datetime.now(timezone.utc).strftime("%d-%B-%Y")

        centroid = flag.encroached_geometry.centroid
        coords_str = f"Lat: {centroid.y:.6f}° N, Lon: {centroid.x:.6f}° E"

        notice_content = {
            "notice_reference": notice_ref,
            "statutory_act": "Municipal Corporation Act & Public Land Protection Code (Sec. 248/321)",
            "issuing_authority": f"Office of the Chief Survey Officer, {self.registry.municipality_name}",
            "issue_date": issue_date,
            "addressee": {
                "name": flag.violator_owner_name,
                "parcel_id": flag.suspected_violator_parcel_id or "UNREGISTERED_OCCUPANT",
                "survey_number": violating_parcel.survey_number if violating_parcel else "UNAUTHORIZED_SQUATTER",
                "zone": violating_parcel.zone_name if violating_parcel else "Public Domain",
            },
            "infringement_details": {
                "flag_id": flag.flag_id,
                "encroachment_type": flag.encroachment_type.value,
                "severity_level": flag.severity.value,
                "encroached_area_sqm": round(flag.encroached_area_sqm, 2),
                "affected_property": f"{flag.affected_owner_name} ({flag.affected_parcel_id})",
                "affected_land_use": flag.affected_land_use.value,
                "gps_centroid": coords_str,
                "satellite_detection_confidence": f"{int(flag.confidence * 100)}%",
            },
            "statutory_order": (
                f"TAKE NOTICE that multi-spectral satellite GIS remote sensing and cadastral overlay audit has confirmed "
                f"unauthorized construction of approximately {round(flag.encroached_area_sqm, 2)} square meters on "
                f"property designated as '{flag.affected_land_use.value}'.\n\n"
                f"YOU ARE HEREBY DIRECTED to cease all unauthorized operations immediately and show cause in writing "
                f"within SEVEN (7) DAYS of receipt of this notice, or remove the illegal projection. Failure to comply "
                f"shall lead to immediate summary demolition and recovery of punitive statutory penalties of ₹{flag.estimated_penalty:,.2f} "
                f"as land revenue arrears."
            ),
            "estimated_penalty_inr": round(flag.estimated_penalty, 2),
            "compliance_deadline_days": 7 if flag.severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH] else 15,
            "recommended_action": flag.recommended_action,
        }

        return notice_content

    def generate_full_audit_report(self) -> Dict[str, Any]:
        """
        Generates an executive municipal audit report of all surveyed parcels and detected encroachments.
        """
        metrics = self.registry.get_metrics_summary()
        flags_data = [f.to_dict() for f in self.registry.encroachment_flags.values()]

        # High priority actions list
        priority_demolitions = [
            f for f in flags_data
            if f["severity"] in ["CRITICAL", "HIGH"]
        ]

        return {
            "municipality": self.registry.municipality_name,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "audit_summary": metrics,
            "high_priority_enforcements": priority_demolitions,
            "all_flags": flags_data,
        }
