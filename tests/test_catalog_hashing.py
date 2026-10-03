"""
Tests for deterministic render fingerprinting.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog_hashing import (
    compute_render_fingerprint,
    fingerprint_prefix,
    RENDERER_VERSION,
)
from core.case_template_loader import load_case_template
from core.contract_ids import is_valid_content_hash


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_ROOT = REPO_ROOT / "assets" / "case_templates"
ARTWORKS_DIR = REPO_ROOT / "tests" / "fixtures" / "artworks"


def _get_template_info(device_id="iphone-17", case_type="hard", view="rear"):
    """Load a template and return (template, template_dir)."""
    from core.catalog_build_plan import find_template_dir
    tpl_dir = find_template_dir(str(TEMPLATES_ROOT), device_id, case_type, view)
    assert tpl_dir is not None
    template = load_case_template(Path(tpl_dir) / "template.json")
    return template, tpl_dir


# ---------------------------------------------------------------------------
# Basic fingerprint properties
# ---------------------------------------------------------------------------

class TestFingerprintBasics:
    def test_returns_sha256_format(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        assert fp.startswith("sha256:")
        hex_part = fp[len("sha256:"):]
        assert len(hex_part) == 64
        # All hex chars
        int(hex_part, 16)

    def test_valid_content_hash_format(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        assert is_valid_content_hash(fp)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestFingerprintDeterminism:
    def test_same_inputs_same_fingerprint(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        assert fp1 == fp2

    def test_different_designs_different_fingerprint(self):
        template, tpl_dir = _get_template_info()
        fp1 = compute_render_fingerprint(
            design_path=str(ARTWORKS_DIR / "color-block.png"),
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=str(ARTWORKS_DIR / "tile-pattern.png"),
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        assert fp1 != fp2

    def test_different_devices_different_fingerprint(self):
        tpl1, dir1 = _get_template_info("iphone-17")
        tpl2, dir2 = _get_template_info("iphone-17e")
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=tpl1,
            template_dir=dir1,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=tpl2,
            template_dir=dir2,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        assert fp1 != fp2

    def test_different_widths_different_fingerprint(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=800,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1600,
            render_options={"fit_mode": "cover"},
        )
        assert fp1 != fp2

    def test_different_fit_modes_different_fingerprint(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "contain"},
        )
        assert fp1 != fp2

    def test_different_zoom_different_fingerprint(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover", "zoom": 1.0},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover", "zoom": 1.5},
        )
        assert fp1 != fp2

    def test_different_view_different_fingerprint(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")
        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="front",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        assert fp1 != fp2


# ---------------------------------------------------------------------------
# What NOT to hash
# ---------------------------------------------------------------------------

class TestWhatIsNotHashed:
    def test_absolute_path_does_not_affect_hash(self, tmp_path):
        """The fingerprint should not depend on absolute file paths.

        Same file content + same filename = same hash, regardless of
        which directory the file is in.
        """
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")

        # Copy design to a different directory, same filename
        alt_dir = tmp_path / "other_dir"
        alt_dir.mkdir()
        alt_design = alt_dir / "color-block.png"
        import shutil
        shutil.copy2(design_path, str(alt_design))

        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=str(alt_design),
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        # Same content + same filename = same fingerprint
        # (absolute directory path does not affect the hash)
        assert fp1 == fp2

    def test_default_options_same_as_explicit_defaults(self):
        template, tpl_dir = _get_template_info()
        design_path = str(ARTWORKS_DIR / "color-block.png")

        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={
                "fit_mode": "cover",
                "zoom": 1.0,
                "offset_x": 0.0,
                "offset_y": 0.0,
                "webp_quality": 85,
            },
        )
        assert fp1 == fp2


# ---------------------------------------------------------------------------
# fingerprint_prefix helper
# ---------------------------------------------------------------------------

class TestFingerprintPrefix:
    def test_default_12_chars(self):
        fp = "sha256:" + "a" * 64
        assert fingerprint_prefix(fp) == "aaaaaaaaaaaa"
        assert len(fingerprint_prefix(fp)) == 12

    def test_custom_length(self):
        fp = "sha256:" + "b" * 64
        assert fingerprint_prefix(fp, length=8) == "bbbbbbbb"

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid fingerprint format"):
            fingerprint_prefix("md5:abc123")

    def test_too_short_raises(self):
        fp = "sha256:abc"
        with pytest.raises(ValueError, match="too short"):
            fingerprint_prefix(fp, length=12)


# ---------------------------------------------------------------------------
# Template layer content affects hash
# ---------------------------------------------------------------------------

class TestTemplateLayerHash:
    def test_changing_template_changes_fingerprint(self, tmp_path):
        """Modifying a template layer file changes the fingerprint."""
        # Create a copy of a template directory
        template, tpl_dir = _get_template_info()
        import shutil

        copy_dir = tmp_path / "template_copy"
        shutil.copytree(tpl_dir, str(copy_dir))

        design_path = str(ARTWORKS_DIR / "color-block.png")

        # Load template from copy
        tpl_copy = load_case_template(copy_dir / "template.json")

        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=tpl_copy,
            template_dir=str(copy_dir),
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )

        # Modify the base.png (write a different image)
        base_path = copy_dir / "base.png"
        img = Image.open(str(base_path))
        # Flip the image to change content
        flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
        flipped.save(str(base_path))

        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=tpl_copy,
            template_dir=str(copy_dir),
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )

        assert fp1 != fp2

    def test_template_json_changes_fingerprint(self, tmp_path):
        """Modifying template.json changes the fingerprint."""
        template, tpl_dir = _get_template_info()
        import shutil
        import copy

        copy_dir = tmp_path / "template_copy"
        shutil.copytree(tpl_dir, str(copy_dir))

        design_path = str(ARTWORKS_DIR / "color-block.png")

        tpl_copy = load_case_template(copy_dir / "template.json")

        fp1 = compute_render_fingerprint(
            design_path=design_path,
            template=tpl_copy,
            template_dir=str(copy_dir),
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )

        # Modify template.json (change canvas size in the JSON)
        tpl_json_path = copy_dir / "template.json"
        with open(tpl_json_path, "r") as f:
            tpl_data = json.load(f)
        tpl_data["canvas"]["width"] = tpl_data["canvas"]["width"] + 100
        with open(tpl_json_path, "w") as f:
            json.dump(tpl_data, f)

        # Reload template
        tpl_modified = load_case_template(tpl_json_path)

        fp2 = compute_render_fingerprint(
            design_path=design_path,
            template=tpl_modified,
            template_dir=str(copy_dir),
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )

        assert fp1 != fp2


# ---------------------------------------------------------------------------
# Design content affects hash
# ---------------------------------------------------------------------------

class TestDesignContentHash:
    def test_different_design_content_different_hash(self, tmp_path):
        template, tpl_dir = _get_template_info()

        # Create two different design images
        img1 = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        img2 = Image.new("RGBA", (100, 100), (0, 0, 255, 255))

        p1 = tmp_path / "design1.png"
        p2 = tmp_path / "design2.png"
        img1.save(str(p1))
        img2.save(str(p2))

        fp1 = compute_render_fingerprint(
            design_path=str(p1),
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )
        fp2 = compute_render_fingerprint(
            design_path=str(p2),
            template=template,
            template_dir=tpl_dir,
            view="rear",
            width=1200,
            render_options={"fit_mode": "cover"},
        )

        assert fp1 != fp2
