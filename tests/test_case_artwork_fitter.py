"""
Unit tests for core/case_artwork_fitter.py.

Covers: cover/contain/tile modes, focal point, offsets, zoom,
alpha/RGBA handling, output dimensions, and edge cases.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from core.case_artwork_fitter import fit_artwork


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def portrait_art():
    """300x600 portrait artwork (red)."""
    img = Image.new("RGBA", (300, 600), (255, 0, 0, 255))
    return img


@pytest.fixture
def landscape_art():
    """600x300 landscape artwork (green)."""
    img = Image.new("RGBA", (600, 300), (0, 255, 0, 255))
    return img


@pytest.fixture
def square_art():
    """400x400 square artwork (blue)."""
    img = Image.new("RGBA", (400, 400), (0, 0, 255, 255))
    return img


@pytest.fixture
def varied_art():
    """400x400 artwork with distinct quadrants for offset/zoom detection."""
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 199, 199], fill=(255, 0, 0, 255))      # TL: red
    d.rectangle([200, 0, 399, 199], fill=(0, 255, 0, 255))    # TR: green
    d.rectangle([0, 200, 199, 399], fill=(0, 0, 255, 255))   # BL: blue
    d.rectangle([200, 200, 399, 399], fill=(255, 255, 0, 255))  # BR: yellow
    return img


@pytest.fixture
def transparent_art():
    """400x400 RGBA artwork with transparent regions."""
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Top-left quadrant opaque red
    d.rectangle([0, 0, 199, 199], fill=(255, 0, 0, 255))
    # Bottom-right quadrant opaque green
    d.rectangle([200, 200, 399, 399], fill=(0, 255, 0, 255))
    return img


# ─── Cover mode ───────────────────────────────────────────────────────────

class TestCoverMode:

    def test_portrait_into_tall_region(self, portrait_art):
        """Portrait source into a taller region — should fill width."""
        result = fit_artwork(portrait_art, 200, 500, mode="cover")
        assert result.size == (200, 500)
        assert result.mode == "RGBA"

    def test_landscape_into_tall_region(self, landscape_art):
        """Landscape source into a tall region — should fill width, crop sides."""
        result = fit_artwork(landscape_art, 200, 500, mode="cover")
        assert result.size == (200, 500)
        assert result.mode == "RGBA"

    def test_square_source(self, square_art):
        """Square source into a non-square region."""
        result = fit_artwork(square_art, 300, 600, mode="cover")
        assert result.size == (300, 600)

    def test_cover_no_transparency(self, square_art):
        """Cover mode on opaque artwork should produce a fully opaque result."""
        result = fit_artwork(square_art, 200, 200, mode="cover")
        alpha = np.array(result.getchannel("A"))
        assert alpha.min() == 255, "Cover mode should produce fully opaque output"

    def test_cover_rgba_source(self, transparent_art):
        """Cover mode preserves RGBA transparency."""
        result = fit_artwork(transparent_art, 200, 200, mode="cover")
        assert result.size == (200, 200)
        alpha = np.array(result.getchannel("A"))
        # Some pixels should still be transparent (from source)
        assert alpha.min() == 0, "Transparent regions should be preserved"


# ─── Contain mode ─────────────────────────────────────────────────────────

class TestContainMode:

    def test_contain_produces_padding(self, landscape_art):
        """Contain mode fits entirely, leaving transparent padding."""
        result = fit_artwork(landscape_art, 400, 400, mode="contain")
        assert result.size == (400, 400)
        # Landscape into square: fits width, pads height
        alpha = np.array(result.getchannel("A"))
        # Top and bottom rows should be transparent (padding)
        assert alpha[0, 0] == 0, "Top padding should be transparent"
        assert alpha[-1, -1] == 0, "Bottom padding should be transparent"

    def test_contain_square_source(self, square_art):
        """Contain mode on square source into square region — no padding."""
        result = fit_artwork(square_art, 400, 400, mode="contain")
        alpha = np.array(result.getchannel("A"))
        assert alpha.min() == 255, "No padding expected for matching aspect"

    def test_contain_rgba_source(self, transparent_art):
        """Contain mode preserves RGBA."""
        result = fit_artwork(transparent_art, 200, 200, mode="contain")
        assert result.size == (200, 200)
        alpha = np.array(result.getchannel("A"))
        assert alpha.min() == 0, "Transparent regions preserved"


# ─── Tile mode ────────────────────────────────────────────────────────────

class TestTileMode:

    def test_tile_fills_entire_region(self, square_art):
        """Tile mode should fill the entire target with no gaps."""
        result = fit_artwork(square_art, 800, 800, mode="tile")
        assert result.size == (800, 800)
        alpha = np.array(result.getchannel("A"))
        assert alpha.min() == 255, "Tile should fill entirely"

    def test_tile_repeats_pattern(self):
        """Tile mode should produce a repeating pattern."""
        # Create a small tile with a unique marker
        tile = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile)
        d.rectangle([0, 0, 24, 24], fill=(255, 0, 0, 255))
        result = fit_artwork(tile, 100, 100, mode="tile")
        arr = np.array(result)
        # Top-left pixel should be red (from the tile)
        assert tuple(arr[0, 0, :3]) == (255, 0, 0)
        # Pixel at 50,0 should also be red (repeated tile)
        assert tuple(arr[0, 50, :3]) == (255, 0, 0)

    def test_tile_offset(self, varied_art):
        """Tile mode with offset shifts the grid."""
        result_a = fit_artwork(varied_art, 400, 400, mode="tile", offset_x=0.0)
        result_b = fit_artwork(varied_art, 400, 400, mode="tile", offset_x=0.5)
        arr_a = np.array(result_a)
        arr_b = np.array(result_b)
        assert not np.array_equal(arr_a, arr_b), "Offset should shift tile grid"


# ─── Focal point ──────────────────────────────────────────────────────────

class TestFocalPoint:

    def test_focal_point_center(self, landscape_art):
        """Focal point center should show the middle of the source."""
        result = fit_artwork(
            landscape_art, 100, 100, mode="cover", focal_point=(0.5, 0.5)
        )
        assert result.size == (100, 100)

    def test_focal_point_edge(self, landscape_art):
        """Focal point at edge should show the edge of the source."""
        # Create artwork with distinct left and right halves
        art = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(art)
        d.rectangle([0, 0, 299, 299], fill=(255, 0, 0, 255))  # left = red
        d.rectangle([300, 0, 599, 299], fill=(0, 0, 255, 255))  # right = blue

        center = fit_artwork(art, 100, 100, mode="cover", focal_point=(0.5, 0.5))
        left = fit_artwork(art, 100, 100, mode="cover", focal_point=(0.0, 0.5))
        right = fit_artwork(art, 100, 100, mode="cover", focal_point=(1.0, 0.5))

        center_arr = np.array(center)
        left_arr = np.array(left)
        right_arr = np.array(right)

        # Left focal point should show more red
        assert left_arr[:, :50, 0].mean() > center_arr[:, :50, 0].mean(), \
            "Left focal point should favor left (red) side"
        # Right focal point should show more blue
        assert right_arr[:, 50:, 2].mean() > center_arr[:, 50:, 2].mean(), \
            "Right focal point should favor right (blue) side"

    def test_different_focal_points_produce_different_output(self, varied_art):
        """Different focal points should produce different crops."""
        r1 = fit_artwork(varied_art, 100, 200, mode="cover", focal_point=(0.3, 0.5))
        r2 = fit_artwork(varied_art, 100, 200, mode="cover", focal_point=(0.7, 0.5))
        assert not np.array_equal(np.array(r1), np.array(r2))


# ─── Offset ───────────────────────────────────────────────────────────────

class TestOffset:

    def test_positive_offset_x(self, varied_art):
        """Positive offset_x shifts artwork right (portrait target → horizontal crop room)."""
        r0 = fit_artwork(varied_art, 200, 400, mode="cover", offset_x=0.0)
        r1 = fit_artwork(varied_art, 200, 400, mode="cover", offset_x=0.5)
        assert not np.array_equal(np.array(r0), np.array(r1))

    def test_negative_offset_x(self, varied_art):
        """Negative offset_x shifts artwork left."""
        r_pos = fit_artwork(varied_art, 200, 400, mode="cover", offset_x=0.5)
        r_neg = fit_artwork(varied_art, 200, 400, mode="cover", offset_x=-0.5)
        assert not np.array_equal(np.array(r_pos), np.array(r_neg))

    def test_positive_offset_y(self, varied_art):
        """Positive offset_y shifts artwork down (landscape target → vertical crop room)."""
        r0 = fit_artwork(varied_art, 400, 200, mode="cover", offset_y=0.0)
        r1 = fit_artwork(varied_art, 400, 200, mode="cover", offset_y=0.5)
        assert not np.array_equal(np.array(r0), np.array(r1))

    def test_negative_offset_y(self, varied_art):
        """Negative offset_y shifts artwork up."""
        r_pos = fit_artwork(varied_art, 400, 200, mode="cover", offset_y=0.5)
        r_neg = fit_artwork(varied_art, 400, 200, mode="cover", offset_y=-0.5)
        assert not np.array_equal(np.array(r_pos), np.array(r_neg))


# ─── Zoom ─────────────────────────────────────────────────────────────────

class TestZoom:

    def test_zoom_gt_1_enlarges(self, varied_art):
        """Zoom > 1 should enlarge the artwork (less source visible)."""
        r1 = fit_artwork(varied_art, 200, 400, mode="cover", zoom=1.0)
        r2 = fit_artwork(varied_art, 200, 400, mode="cover", zoom=2.0)
        assert r1.size == (200, 400)
        assert r2.size == (200, 400)
        # Different zoom should produce different pixels
        assert not np.array_equal(np.array(r1), np.array(r2))

    def test_zoom_lt_1_shrinks_in_contain(self, square_art):
        """Zoom < 1 in contain mode should shrink the artwork."""
        r1 = fit_artwork(square_art, 400, 400, mode="contain", zoom=1.0)
        r2 = fit_artwork(square_art, 400, 400, mode="contain", zoom=0.5)
        # With 0.5 zoom in contain, more padding should appear
        alpha1 = np.array(r1.getchannel("A"))
        alpha2 = np.array(r2.getchannel("A"))
        # More transparent pixels with zoom=0.5
        assert (alpha2 == 0).sum() >= (alpha1 == 0).sum()


# ─── Output dimensions ────────────────────────────────────────────────────

class TestOutputDimensions:

    @pytest.mark.parametrize("tw,th", [(100, 200), (500, 100), (1, 1), (2000, 3000)])
    def test_output_size_matches_target(self, square_art, tw, th):
        """Output dimensions must match target regardless of source."""
        result = fit_artwork(square_art, tw, th, mode="cover")
        assert result.size == (tw, th)

    def test_output_mode_is_rgba(self, square_art):
        """Output should always be RGBA."""
        result = fit_artwork(square_art, 200, 200, mode="cover")
        assert result.mode == "RGBA"

    def test_rgb_input_converted_to_rgba(self):
        """RGB input should be converted to RGBA output."""
        rgb_art = Image.new("RGB", (200, 200), (128, 128, 128))
        result = fit_artwork(rgb_art, 100, 100, mode="cover")
        assert result.mode == "RGBA"


# ─── Edge cases ───────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_invalid_mode_raises(self, square_art):
        """Unknown mode should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown fit mode"):
            fit_artwork(square_art, 200, 200, mode="invalid")

    def test_zero_target_dimension_raises(self, square_art):
        """Zero target dimensions should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid target"):
            fit_artwork(square_art, 0, 200, mode="cover")
        with pytest.raises(ValueError, match="Invalid target"):
            fit_artwork(square_art, 200, 0, mode="cover")

    def test_no_aspect_ratio_distortion_cover(self, landscape_art):
        """Cover mode should not distort aspect ratio of the source content."""
        # Landscape art 600x300 into 200x200 cover: scale = max(200/600, 200/300) = 2/3
        # Scaled size: 400x200, crop to 200x200 — no distortion
        result = fit_artwork(landscape_art, 200, 200, mode="cover")
        # The green color should be uniform (single color source)
        arr = np.array(result)
        # All opaque pixels should be green
        opaque_mask = arr[:, :, 3] == 255
        if opaque_mask.any():
            green_pixels = arr[opaque_mask]
            # All should be (0, 255, 0)
            assert np.all(green_pixels[:, 1] == 255), "No color distortion expected"
            assert np.all(green_pixels[:, 0] == 0)
            assert np.all(green_pixels[:, 2] == 0)
