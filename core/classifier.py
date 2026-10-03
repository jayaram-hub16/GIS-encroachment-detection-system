"""
core/classifier.py - Multi-spectral GIS Land Cover Classification Engine.

Implements machine learning classification (Decision Tree / Ensemble) on multi-spectral satellite
and remote-sensing observations (Red, Green, Blue, NIR, SWIR bands + NDVI, NDBI, NDWI, BSI indices)
to accurately classify land cover into Built-Up, Vegetation, Water, Road, and Bare Soil.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple, Any
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from .models import LandUseType


class LandCoverClassifier:
    """
    Machine Learning Classifier for Multi-Spectral GIS / Satellite Data.
    Extracts spectral signatures (NDVI, NDBI, NDWI, BSI) to classify land pixels.
    """

    FEATURE_NAMES = ["red", "green", "blue", "nir", "swir", "ndvi", "ndbi", "ndwi", "bsi", "texture_variance"]
    CLASS_LABELS = [
        "BUILT_UP",          # Concrete, rooftops, structures
        "VEGETATION",        # Forest, lawns, agricultural crops
        "WATER_BODY",        # Lakes, rivers, detention ponds
        "ROAD_SURFACE",      # Asphalt, municipal paved roads
        "BARE_SOIL",         # Open earth, unpaved lots
    ]

    def __init__(self, max_depth: int = 8, random_state: int = 42):
        self.model = DecisionTreeClassifier(
            max_depth=max_depth,
            random_state=random_state,
            class_weight="balanced"
        )
        self.is_trained = False
        self.feature_importances_: Dict[str, float] = {}
        self.model_metrics: Dict[str, Any] = {}
        # Pre-train with synthetic spectral library
        self._train_default_spectral_model()

    @staticmethod
    def calculate_spectral_indices(
        red: float, green: float, blue: float, nir: float, swir: float, texture_variance: float = 0.05
    ) -> np.ndarray:
        """
        Derives standard remote sensing indices from multi-spectral reflectances (0.0 to 1.0).
        - NDVI: (NIR - Red) / (NIR + Red + 1e-6)
        - NDBI: (SWIR - NIR) / (SWIR + NIR + 1e-6)
        - NDWI: (Green - NIR) / (Green + NIR + 1e-6)
        - BSI:  ((SWIR + Red) - (NIR + Blue)) / ((SWIR + Red) + (NIR + Blue) + 1e-6)
        """
        eps = 1e-6
        ndvi = (nir - red) / (nir + red + eps)
        ndbi = (swir - nir) / (swir + nir + eps)
        ndwi = (green - nir) / (green + nir + eps)
        bsi = ((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue) + eps)

        return np.array([red, green, blue, nir, swir, ndvi, ndbi, ndwi, bsi, texture_variance], dtype=np.float32)

    def _generate_synthetic_training_data(self, samples_per_class: int = 150) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generates realistic multi-spectral surface reflectance profiles based on USGS/Sentinel-2 spectral libraries:
        - Built-Up: High SWIR & Red, Moderate NIR, positive NDBI (>0.15), low NDVI (<0.18).
        - Vegetation: Very high NIR (0.50-0.80), Low Red & Blue (chlorophyll absorption), high NDVI (>0.55), negative NDBI.
        - Water Body: High Green, Very Low NIR & SWIR (strong water absorption), high NDWI (>0.30).
        - Road Surface: Low-medium uniform reflectance, dark asphalt, low texture variance, moderate NDBI.
        - Bare Soil: High Red & SWIR, moderate NIR, high BSI, low NDWI, low NDVI.
        """
        np.random.seed(42)
        X_list = []
        y_list = []

        # 1. BUILT_UP (Rooftops, concrete, brick, industrial sheds: distinct positive NDBI > 0.15, moderate NIR)
        for _ in range(samples_per_class):
            r = np.clip(np.random.normal(0.22, 0.03), 0.08, 0.45)
            g = np.clip(np.random.normal(0.20, 0.03), 0.08, 0.45)
            b = np.clip(np.random.normal(0.18, 0.03), 0.08, 0.45)
            nir = np.clip(np.random.normal(0.22, 0.03), 0.08, 0.40)
            swir = np.clip(np.random.normal(0.42, 0.04), 0.25, 0.65)
            tex = np.clip(np.random.normal(0.14, 0.02), 0.08, 0.3)
            feats = self.calculate_spectral_indices(r, g, b, nir, swir, tex)
            X_list.append(feats)
            y_list.append("BUILT_UP")

        # 2. VEGETATION (Tree canopies, grass, agricultural fields: high NIR, high NDVI > 0.5)
        for _ in range(samples_per_class):
            r = np.clip(np.random.normal(0.06, 0.02), 0.02, 0.15)
            g = np.clip(np.random.normal(0.15, 0.03), 0.05, 0.30)
            b = np.clip(np.random.normal(0.05, 0.02), 0.01, 0.15)
            nir = np.clip(np.random.normal(0.65, 0.06), 0.45, 0.85)
            swir = np.clip(np.random.normal(0.15, 0.03), 0.05, 0.28)
            tex = np.clip(np.random.normal(0.16, 0.03), 0.06, 0.35)
            feats = self.calculate_spectral_indices(r, g, b, nir, swir, tex)
            X_list.append(feats)
            y_list.append("VEGETATION")

        # 3. WATER_BODY (Lakes, reservoirs, wetlands: strong absorption in NIR & SWIR)
        for _ in range(samples_per_class):
            r = np.clip(np.random.normal(0.04, 0.01), 0.01, 0.10)
            g = np.clip(np.random.normal(0.14, 0.02), 0.05, 0.22)
            b = np.clip(np.random.normal(0.18, 0.02), 0.06, 0.28)
            nir = np.clip(np.random.normal(0.02, 0.005), 0.005, 0.05)
            swir = np.clip(np.random.normal(0.01, 0.005), 0.002, 0.03)
            tex = np.clip(np.random.normal(0.02, 0.008), 0.001, 0.05)
            feats = self.calculate_spectral_indices(r, g, b, nir, swir, tex)
            X_list.append(feats)
            y_list.append("WATER_BODY")

        # 4. ROAD_SURFACE (Asphalt, tarmac: low uniform reflectance, low texture)
        for _ in range(samples_per_class):
            r = np.clip(np.random.normal(0.11, 0.02), 0.05, 0.18)
            g = np.clip(np.random.normal(0.11, 0.02), 0.05, 0.18)
            b = np.clip(np.random.normal(0.12, 0.02), 0.05, 0.20)
            nir = np.clip(np.random.normal(0.12, 0.02), 0.05, 0.20)
            swir = np.clip(np.random.normal(0.13, 0.02), 0.05, 0.22)
            tex = np.clip(np.random.normal(0.03, 0.01), 0.005, 0.07)
            feats = self.calculate_spectral_indices(r, g, b, nir, swir, tex)
            X_list.append(feats)
            y_list.append("ROAD_SURFACE")

        # 5. BARE_SOIL (Open earth, dry soil: higher red and swir than NIR, but lower NDBI than concrete)
        for _ in range(samples_per_class):
            r = np.clip(np.random.normal(0.32, 0.03), 0.20, 0.48)
            g = np.clip(np.random.normal(0.24, 0.03), 0.14, 0.38)
            b = np.clip(np.random.normal(0.16, 0.02), 0.09, 0.28)
            nir = np.clip(np.random.normal(0.34, 0.03), 0.22, 0.48)
            swir = np.clip(np.random.normal(0.36, 0.04), 0.22, 0.52)
            tex = np.clip(np.random.normal(0.06, 0.015), 0.02, 0.10)
            feats = self.calculate_spectral_indices(r, g, b, nir, swir, tex)
            X_list.append(feats)
            y_list.append("BARE_SOIL")

        return np.array(X_list), np.array(y_list)

    def _train_default_spectral_model(self) -> None:
        X, y = self._generate_synthetic_training_data(samples_per_class=150)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
        self.model.fit(X_train, y_train)
        self.is_trained = True

        y_pred = self.model.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))

        importances = self.model.feature_importances_
        self.feature_importances_ = {
            name: round(float(imp), 4) for name, imp in zip(self.FEATURE_NAMES, importances)
        }
        self.model_metrics = {
            "accuracy": round(acc, 4),
            "total_samples": len(X),
            "training_classes": list(self.model.classes_),
            "feature_importance": self.feature_importances_,
        }

    def classify_spectral_profile(
        self, red: float, green: float, blue: float, nir: float, swir: float, texture_variance: float = 0.14
    ) -> Dict[str, Any]:
        """
        Classifies a single spatial sample based on its spectral signature.
        Returns predicted class, confidence, and calculated indices.
        """
        feats = self.calculate_spectral_indices(red, green, blue, nir, swir, texture_variance)
        proba = self.model.predict_proba([feats])[0]
        class_idx = int(np.argmax(proba))
        predicted_class = str(self.model.classes_[class_idx])
        confidence = float(proba[class_idx])

        # Map to LandUseType enum
        class_map = {
            "BUILT_UP": LandUseType.RESIDENTIAL,
            "VEGETATION": LandUseType.AGRICULTURAL,
            "WATER_BODY": LandUseType.WATER_BODY,
            "ROAD_SURFACE": LandUseType.PUBLIC_UTILITY_ROAD,
            "BARE_SOIL": LandUseType.AGRICULTURAL,
        }

        return {
            "predicted_land_cover": predicted_class,
            "corresponding_land_use": class_map.get(predicted_class, LandUseType.RESIDENTIAL).value,
            "confidence": round(confidence, 4),
            "probabilities": {cls: round(float(p), 4) for cls, p in zip(self.model.classes_, proba)},
            "indices": {
                "ndvi": round(float(feats[5]), 4),
                "ndbi": round(float(feats[6]), 4),
                "ndwi": round(float(feats[7]), 4),
                "bsi": round(float(feats[8]), 4),
            },
        }

    def get_model_diagnostics(self) -> Dict[str, Any]:
        return self.model_metrics
