from cocoon.ml.models.ensemble import EnsembleModel
from cocoon.ml.models.lightgbm_model import LightGBMModel
from cocoon.ml.models.tabnet_model import TabNetModel
from cocoon.ml.models.xgboost_model import XGBoostModel

MODEL_REGISTRY = {
    "lightgbm": LightGBMModel,
    "xgboost": XGBoostModel,
    "tabnet": TabNetModel,
}

__all__ = [
    "EnsembleModel",
    "LightGBMModel",
    "MODEL_REGISTRY",
    "TabNetModel",
    "XGBoostModel",
]
