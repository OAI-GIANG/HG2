PRODUCT_ID = "HG"
ARCHITECTURE = "PHONE_PRIMARY_V1"
SCHEMA = "HG_STATE_V1"
ORIGIN = "clean_room_parentless_genesis"


def identity():
    return {"product": PRODUCT_ID, "architecture": ARCHITECTURE, "schema": SCHEMA, "origin": ORIGIN}
