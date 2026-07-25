from __future__ import annotations

from fairypcbot.place.package_size import DEFAULT_SIZE_MM, estimate_package_size_mm


def test_known_package_matches():
    assert estimate_package_size_mm("R0402") == (1.0, 0.5)
    assert estimate_package_size_mm("SOIC-8") == (4.9, 3.9)
    assert estimate_package_size_mm("LQFP-48") == (7.0, 7.0)


def test_unknown_package_falls_back_to_default():
    assert estimate_package_size_mm("SOME-WEIRD-PACKAGE") == DEFAULT_SIZE_MM


def test_none_package_falls_back_to_default():
    assert estimate_package_size_mm(None) == DEFAULT_SIZE_MM
