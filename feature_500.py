# Feature Implementation for Issue #500
from abc import ABC, abstractmethod
from typing import Optional

class FeatureConfig(ABC):
    @abstractmethod
    def validate(self) -> bool:
        pass

class SimpleFeature(FeatureConfig):
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def validate(self) -> bool:
        return True

class FeatureManager:
    def __init__(self):
        self.features = {}

    def register_feature(self, name: str, config: FeatureConfig) -> None:
        if config.validate():
            self.features[name] = config

    def get_feature(self, name: str) -> Optional[FeatureConfig]:
        return self.features.get(name)

    def enable_feature(self, name: str) -> bool:
        feature = self.get_feature(name)
        if feature and hasattr(feature, 'enabled'):
            feature.enabled = True
            return True
        return False

# Tests
manager = FeatureManager()
feature = SimpleFeature(enabled=True)
manager.register_feature("test_feature", feature)
assert manager.get_feature("test_feature") is not None
assert manager.enable_feature("test_feature") == True
print("Feature tests passed!")
