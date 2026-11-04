from encorelib.query import MAX_SEARCHES, clean_title, primary_artist, search_variants


def test_clean_title_drops_featuring():
    assert clean_title("Stay (feat. Justin Bieber)") == "Stay"
    assert clean_title("Stay [ft. Someone]") == "Stay"
    assert clean_title("Stay feat. Someone") == "Stay"
    assert clean_title("Stay (with Someone)") == "Stay"


def test_clean_title_drops_release_qualifiers():
    assert clean_title("Song - Remastered 2011") == "Song"
    assert clean_title("Blinding Lights (Official Video)") == "Blinding Lights"
    assert clean_title("Song (Lyric Video) [HD]") == "Song"
    assert clean_title("Song - Radio Edit") == "Song"


def test_clean_title_keeps_plain_titles():
    assert clean_title("The Weeknd - Blinding Lights") == "The Weeknd - Blinding Lights"
    assert clean_title("Smells Like Teen Spirit") == "Smells Like Teen Spirit"
    assert clean_title("(Live)") == "(Live)"


def test_primary_artist():
    assert primary_artist("The Kid LAROI, Justin Bieber") == "The Kid LAROI"
    assert primary_artist("A & B") == "A"
    assert primary_artist("A feat. B") == "A"
    assert primary_artist("A x B") == "A"
    assert primary_artist("Artist - Topic") == "Artist"
    assert primary_artist("") == ""


def test_search_variants_raw_first_then_cleaned():
    variants = search_variants("Stay (feat. Justin Bieber)", "The Kid LAROI, Justin Bieber")
    assert variants == [
        ("Stay (feat. Justin Bieber)", "The Kid LAROI, Justin Bieber"),
        ("Stay", "The Kid LAROI"),
    ]


def test_search_variants_browser_title():
    variants = search_variants("The Weeknd - Blinding Lights (Official Video)", "TheWeekndVEVO")
    assert ("Blinding Lights", "The Weeknd") in variants
    assert len(variants) <= MAX_SEARCHES == 3


def test_search_variants_dedupes_clean_tracks():
    assert search_variants("Numb", "Linkin Park") == [("Numb", "Linkin Park")]


def test_search_variants_empty_artist():
    assert search_variants("Numb", "") == [("Numb", "")]
