from events_tool.dedup import fingerprint


def test_identical_events_produce_same_fingerprint():
    a = fingerprint("Salsa Night!", "2026-08-15T19:00:00", "The Dance Hall")
    b = fingerprint("salsa night", "2026-08-15T19:00:00", "the dance hall")
    assert a == b


def test_minor_formatting_differences_still_dedup():
    a = fingerprint("Salsa Night", "2026-08-15T19:00:00", "The Dance Hall")
    b = fingerprint("Salsa  Night...", "2026-08-15T19:32:11", "The Dance Hall!")
    assert a == b, "same hour, punctuation-insensitive title/location should collide"


def test_different_titles_do_not_collide():
    a = fingerprint("Salsa Night", "2026-08-15T19:00:00", "The Dance Hall")
    b = fingerprint("Book Club", "2026-08-15T19:00:00", "The Dance Hall")
    assert a != b


def test_different_hour_does_not_collide():
    a = fingerprint("Salsa Night", "2026-08-15T19:00:00", "The Dance Hall")
    b = fingerprint("Salsa Night", "2026-08-15T20:00:00", "The Dance Hall")
    assert a != b
