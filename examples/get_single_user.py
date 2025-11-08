# examples/get_single_user.py
from onuslibs.config.settings import OnusSettings
from onuslibs.unified.api import fetch_json

def main(userid: str):
    s = OnusSettings()  # tự nạp ENV/.env
    fields = [
        "id","name","email",
        "customValues.date_of_birth",
        "customValues.gender",
        "customValues.vip_level",
        "customValues.listed",
        "customValues.document_type",
        "group.name",
        "address.city",
    ]
    rows = fetch_json(
        endpoint="/api/users",
        params={
            "includeGroup": "true",
            "page": 0,
            "pageSize": 1000,
            "usersToInclude": userid,
            "statuses": "active,blocked,disabled",
        },
        fields=fields,          # list/tuple OK, Facade sẽ chuyển thành CSV
        paginate=False,         # one-shot
        settings=s,
    )
    for r in rows:
        print(r)

    # from tools.print_json import print_json
    # print_json(rows, sort_keys=True)
if __name__ == "__main__":
    main("6277729722014433182")
