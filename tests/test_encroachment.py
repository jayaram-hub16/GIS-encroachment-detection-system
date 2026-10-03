import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shapely.geometry import Polygon

from core.models import (
    OwnerType,
    LandUseType,
    EncroachmentType,
    SeverityLevel,
    OwnershipRecord,
    LandParcel,
    DetectedStructure,
    EncroachmentFlag,
    MunicipalSurveyRegistry,
    calculate_polygon_area_sqm,
)
from core.classifier import LandCoverClassifier
from core.detector import EncroachmentDetector
from core.dataset_generator import build_default_municipal_dataset
from core.report_generator import MunicipalReportGenerator


class TestMunicipalGISEncroachment(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.classifier = LandCoverClassifier()
        cls.registry = build_default_municipal_dataset(cls.classifier)
        cls.detector = EncroachmentDetector(cls.registry)
        cls.report_gen = MunicipalReportGenerator(cls.registry)

    def test_ownership_and_parcel_models(self):
        owner = OwnershipRecord(
            owner_id="OWN-TEST-1",
            full_name="Test Owner",
            owner_type=OwnerType.PRIVATE_CITIZEN,
            deed_number="DEED-001",
            tax_id="TAX-001",
        )
        self.assertFalse(owner.is_public_asset)

        poly = Polygon([(77.59, 12.92), (77.591, 12.92), (77.591, 12.921), (77.59, 12.921), (77.59, 12.92)])
        parcel = LandParcel(
            parcel_id="PARCEL-T1",
            survey_number="SY-999",
            zone_name="Test Zone",
            registered_land_use=LandUseType.RESIDENTIAL,
            ownership=owner,
            boundary=poly,
            max_coverage_ratio=0.6,
            mandatory_setback_meters=2.0,
        )

        area = parcel.area_sqm
        self.assertGreater(area, 5000.0)
        self.assertGreater(parcel.max_allowed_built_area, 3000.0)

        # GeoJSON check
        geojson = parcel.to_geojson_feature()
        self.assertEqual(geojson["properties"]["parcel_id"], "PARCEL-T1")
        self.assertEqual(geojson["properties"]["survey_number"], "SY-999")

    def test_spectral_classifier(self):
        # 1. Built-up sample (High SWIR, moderate NIR, positive NDBI)
        res_built = self.classifier.classify_spectral_profile(0.24, 0.22, 0.20, 0.26, 0.38)
        self.assertEqual(res_built["predicted_land_cover"], "BUILT_UP")
        self.assertGreater(res_built["confidence"], 0.7)
        self.assertGreater(res_built["indices"]["ndbi"], 0.0)

        # 2. Vegetation sample (High NIR, low Red, high NDVI)
        res_veg = self.classifier.classify_spectral_profile(0.05, 0.15, 0.05, 0.65, 0.15)
        self.assertEqual(res_veg["predicted_land_cover"], "VEGETATION")
        self.assertGreater(res_veg["indices"]["ndvi"], 0.5)

        # 3. Water body sample (High green/blue, near zero NIR, positive NDWI, calm surface)
        res_water = self.classifier.classify_spectral_profile(0.03, 0.15, 0.18, 0.01, 0.005, texture_variance=0.01)
        self.assertEqual(res_water["predicted_land_cover"], "WATER_BODY")
        self.assertGreater(res_water["indices"]["ndwi"], 0.3)

    def test_encroachment_detection_scan(self):
        flags = self.detector.run_detection_scan()
        self.assertGreater(len(flags), 0)

        flag_types = [f.encroachment_type for f in flags]

        # Ensure our expected violations are captured
        self.assertIn(EncroachmentType.BOUNDARY_SPILLOVER, flag_types)
        self.assertIn(EncroachmentType.GOVERNMENT_LAND_TRESPASS, flag_types)
        self.assertIn(EncroachmentType.WATERBODY_BUFFER_VIOLATION, flag_types)
        self.assertIn(EncroachmentType.UNAUTHORIZED_LAND_USE, flag_types)

        # Test waterbody buffer violation
        lake_flags = [f for f in flags if f.encroachment_type == EncroachmentType.WATERBODY_BUFFER_VIOLATION]
        self.assertTrue(len(lake_flags) > 0)
        self.assertEqual(lake_flags[0].severity, SeverityLevel.CRITICAL)

        # Test road encroachment
        road_flags = [
            f for f in flags
            if f.encroachment_type == EncroachmentType.GOVERNMENT_LAND_TRESPASS and "ROAD" in f.affected_parcel_id
        ]
        self.assertTrue(len(road_flags) > 0)
        self.assertEqual(road_flags[0].suspected_violator_parcel_id, "PARCEL-COM-201")

    def test_report_generation(self):
        self.detector.run_detection_scan()
        summary = self.report_gen.generate_full_audit_report()
        self.assertEqual(summary["municipality"], self.registry.municipality_name)
        self.assertGreater(summary["audit_summary"]["total_encroachment_flags"], 0)

        # Test legal notice generation
        first_flag_id = list(self.registry.encroachment_flags.keys())[0]
        notice = self.report_gen.generate_legal_notice(first_flag_id)
        self.assertIn("notice_reference", notice)
        self.assertIn("statutory_order", notice)
        self.assertGreater(notice["estimated_penalty_inr"], 0)

    def test_interactive_arbitrary_polygon_analyzer(self):
        base_lat = 12.9250
        base_lon = 77.5900
        d = 0.0008
        test_poly_coords = [
            [base_lon + 0.0005, base_lat + 0.0002],
            [base_lon + d + 0.0002, base_lat + 0.0002],  # Extends into road
            [base_lon + d + 0.0002, base_lat + 0.0006],
            [base_lon + 0.0005, base_lat + 0.0006],
            [base_lon + 0.0005, base_lat + 0.0002],
        ]
        res = self.detector.analyze_arbitrary_polygon(test_poly_coords, claimed_parcel_id="PARCEL-RES-101")
        self.assertGreater(res["drawn_area_sqm"], 0)
        self.assertTrue(res["has_encroachment"])
        road_overlap = [i for i in res["intersections"] if "ROAD" in i["parcel_id"]]
        self.assertTrue(len(road_overlap) > 0)


if __name__ == "__main__":
    unittest.main()
