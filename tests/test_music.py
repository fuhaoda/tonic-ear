import math

import pytest

from app.domain.music import (
    EQUAL_TEMPERAMENT,
    JUST_INTONATION,
    JUST_INTONATION_RATIOS,
    calculate_do_frequency,
    get_note_pool,
    note_frequency,
)


def test_calculate_do_frequency_gender_base_values():
    assert calculate_do_frequency("male", "C") == pytest.approx(130.8)
    assert calculate_do_frequency("female", "C") == pytest.approx(261.6)


def test_calculate_do_frequency_key_shift_for_e():
    expected = 130.8 * (2 ** (4 / 12))
    assert calculate_do_frequency("male", "E") == pytest.approx(expected)


def test_equal_temperament_frequency_formula():
    do_frequency = 200.0
    actual = note_frequency(7, do_frequency, EQUAL_TEMPERAMENT)
    expected = do_frequency * math.pow(2, 7 / 12)
    assert actual == pytest.approx(expected)


def test_just_intonation_frequency_formula():
    do_frequency = 200.0
    actual = note_frequency(7, do_frequency, JUST_INTONATION)
    expected = do_frequency * JUST_INTONATION_RATIOS[7]
    assert actual == pytest.approx(expected)


def test_note_pools_match_expected_sizes():
    assert len(get_note_pool("L1")) == 3
    assert len(get_note_pool("L2")) == 5
    assert len(get_note_pool("L3")) == 7
    assert len(get_note_pool("L4")) == 12
    assert len(get_note_pool("L5")) == 12
    assert len(get_note_pool("L6")) == 12
