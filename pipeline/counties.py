"""California county codes (Census FIPS, state 06), named as the CDSS file names them."""
CA_COUNTIES = {
    "001": "ALAMEDA", "003": "ALPINE", "005": "AMADOR", "007": "BUTTE", "009": "CALAVERAS", "011": "COLUSA",
    "013": "CONTRA COSTA", "015": "DEL NORTE", "017": "EL DORADO", "019": "FRESNO", "021": "GLENN",
    "023": "HUMBOLDT", "025": "IMPERIAL", "027": "INYO", "029": "KERN", "031": "KINGS", "033": "LAKE",
    "035": "LASSEN", "037": "LOS ANGELES", "039": "MADERA", "041": "MARIN", "043": "MARIPOSA",
    "045": "MENDOCINO", "047": "MERCED", "049": "MODOC", "051": "MONO", "053": "MONTEREY", "055": "NAPA",
    "057": "NEVADA", "059": "ORANGE", "061": "PLACER", "063": "PLUMAS", "065": "RIVERSIDE", "067": "SACRAMENTO",
    "069": "SAN BENITO", "071": "SAN BERNARDINO", "073": "SAN DIEGO", "075": "SAN FRANCISCO",
    "077": "SAN JOAQUIN", "079": "SAN LUIS OBISPO", "081": "SAN MATEO", "083": "SANTA BARBARA",
    "085": "SANTA CLARA", "087": "SANTA CRUZ", "089": "SHASTA", "091": "SIERRA", "093": "SISKIYOU",
    "095": "SOLANO", "097": "SONOMA", "099": "STANISLAUS", "101": "SUTTER", "103": "TEHAMA", "105": "TRINITY",
    "107": "TULARE", "109": "TUOLUMNE", "111": "VENTURA", "113": "YOLO", "115": "YUBA",
}


def county_name(fips):
    """County name for a 5-digit code such as "06067", or "" when it isn't a California county."""
    fips = (fips or "").strip()
    return CA_COUNTIES.get(fips[2:], "") if len(fips) == 5 and fips.startswith("06") else ""
