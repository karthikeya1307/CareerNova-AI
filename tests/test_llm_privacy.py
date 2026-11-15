"""Shared AI privacy scrubber (used for every request to the optional AI provider)."""

import pytest

from backend.services.llm_privacy import find_personal_data, scrub_personal

DETAILS = {
    "name": "Asha Rao",
    "email": "asha@example.com",
    "phone": "+91 98765 43210",
    "linkedin": "linkedin.com/in/asharao",
    "location": "Bengaluru",
    "address": "12 MG Road, Indiranagar, Bengaluru 560001",
}

ANSWER = ("I am Asha. You can reach me at asha@example.com or +91 98765 43210, or on linkedin.com/in/asharao. "
          "I live at 12 MG Road, Indiranagar, Bengaluru 560001 in Flat No. 4B. Rao is my surname and my old "
          "house was at 221 Baker Street, PIN 110 001. An inner join returned 200 rows and we cut latency by 35% "
          "using 3 indexes in 2025, so lookups became O(log n).")


@pytest.mark.parametrize("secret", [
    "Asha", "Rao", "asha@example.com", "98765 43210", "linkedin.com/in/asharao", "12 MG Road", "Indiranagar",
    "Bengaluru", "560001", "Flat No. 4B", "221 Baker Street", "110 001",
])
def test_scrub_removes_each_kind_of_personal_data(secret):
    assert secret.lower() not in scrub_personal(ANSWER, DETAILS).lower()


def test_scrub_keeps_technical_content():
    cleaned = scrub_personal(ANSWER, DETAILS)
    for kept in ("An inner join returned 200 rows", "35%", "3 indexes in 2025", "O(log n)"):
        assert kept in cleaned


def test_detection_before_and_after_scrubbing():
    assert set(find_personal_data(ANSWER, DETAILS)) >= {"name", "email", "phone", "address", "street_address",
                                                         "pin_code", "link"}
    assert find_personal_data(scrub_personal(ANSWER, DETAILS), DETAILS) == []


def test_name_parts_are_matched_as_whole_words():
    details = {"name": "Ram Kumar"}
    text = "I wrote a program that caches data in RAM. Ram presented it and Kumar reviewed it."
    cleaned = scrub_personal(text, details)
    assert "program" in cleaned and "Ram presented" not in cleaned and "Kumar" not in cleaned


@pytest.mark.parametrize("text", ["Contact me at 560 001.", "PIN code 400076", "Flat no 7, Sector 15 colony"])
def test_pin_codes_and_house_numbers_without_stored_address(text):
    assert find_personal_data(text, {}) != []
    assert find_personal_data(scrub_personal(text, {}), {}) == []


def test_missing_details_are_handled():
    assert scrub_personal("", {}) == ""
    assert find_personal_data("A plain technical answer about joins.", {"name": None, "address": None}) == []
