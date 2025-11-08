# tools/diag_token_capabilities.py
from onuslibs.config.settings import OnusSettings
from onuslibs.security.headers import build_headers, preview_headers
from onuslibs.unified.api import fetch_json

FIELDS = [
  "id","name","username","email",
  "customValues.gender","customValues.date_of_birth",
  "customValues.vip_level","customValues.listed","customValues.document_type",
  "group.name","address.city",
]

def get_in(item, path):
    cur = item
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur

def main(userid: str):
    s = OnusSettings()
    hdr = build_headers(s)
    print("HEADERS:", preview_headers(hdr, s))
    rows = fetch_json(
        endpoint="/api/users",
        params={
            "includeGroup":"true",
            "includeAddress":"true",
            "statuses":"active,blocked,disabled",
            "usersToInclude": userid,
        },
        fields=FIELDS,
        paginate=False,
        settings=s,
    )
    if not rows:
        print("No rows returned (check userid or permissions).")
        return
    u = rows[0]
    print("\n== Field check ==")
    for f in FIELDS:
        v = get_in(u, f)
        status = "PASS" if v is not None else "FAIL"
        print(f"{status:4}  {f}  -> {repr(v)}")

if __name__ == "__main__":
    main("6277729722014433182")
