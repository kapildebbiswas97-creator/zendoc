import os

# CI/unit tests must remain deterministic and offline. Production explicitly
# enables bounded OpenStreetMap POI augmentation through render.yaml.
os.environ.setdefault("ZENDOC_OSM_POI_ENABLED", "false")
