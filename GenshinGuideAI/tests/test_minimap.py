import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

HAS_MAP = Path(r"C:\Program Files\BetterGI\Assets\Map\Teyvat\MapBack_0_gray.webp").exists()


@unittest.skipUnless(HAS_MAP, "需要 BetterGI 地图资产")
class MinimapMathTests(unittest.TestCase):
    def test_synthetic_patch_roundtrip(self):
        import cv2
        from minimap_localize import MAP_DIR, load_layers, match_layer

        gray = cv2.imread(str(MAP_DIR / "MapBack_0_gray.webp"), cv2.IMREAD_GRAYSCALE)
        layer = next(item for item in load_layers() if item["LayerId"] == "MapBack_0")
        world = (10264.0, -2762.0)
        mx = int(round((layer["Left"] - world[0]) * layer.get("Scale", 1)))
        my = int(round((layer["Top"] - world[1]) * layer.get("Scale", 1)))
        size = 260
        patch = gray[my - size // 2 : my + size // 2, mx - size // 2 : mx + size // 2]
        mask = np.full((size, size), 255, np.uint8)
        result = match_layer(gray, patch, mask, layer)
        self.assertEqual(result["layer"], "MapBack_0")
        self.assertAlmostEqual(result["world"][0], world[0], delta=2.0)
        self.assertAlmostEqual(result["world"][1], world[1], delta=2.0)

    def test_world_to_map_formula(self):
        from minimap_localize import map_to_world, world_to_map

        layer = {"Left": 12384.0, "Top": 1024.0, "Scale": 1}
        px = world_to_map((10264.0, -2762.0), 1, layer)
        self.assertEqual(px, (2120, 3786))
        world = map_to_world((px[0] - 130, px[1] - 130), 1, 260, layer)
        self.assertAlmostEqual(world[0], 10264.0, delta=0.5)
        self.assertAlmostEqual(world[1], -2762.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
