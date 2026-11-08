from prawo_pl_mcp.local_docs import route, cache_id, uodo_signature, looks_truncated

def test_auto_saos():
    assert route("auto","saos:514638") == ("saos","514638")
    assert cache_id("saos","514638") == "saos:514638"

def test_auto_eli():
    assert route("auto","eli:DU/2026/490") == ("isap","DU/2026/490")
    assert cache_id("isap","DU/2026/490") == "eli:DU/2026/490"

def test_uodo_urn():
    assert uodo_signature("urn:ndoc:gov:pl:uodo:2022_dkn_5131_27") == "DKN.5131.27.2022"
    assert uodo_signature("urn:ndoc:gov:pl:uodo:2022:dkn_5131_27") == "DKN.5131.27.2022"

def test_truncated_nsa():
    assert looks_truncated("[...] Skrocono. Pelna tresc: https://orzeczenia.nsa.gov.pl/")
    assert not looks_truncated("Pelna tresc orzeczenia")
