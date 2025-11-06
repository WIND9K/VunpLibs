import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()  # nếu bạn dùng .env

from onuslibs.db import healthcheck, query
assert healthcheck() is True, "Healthcheck failed – kiểm tra ENV DB_*"
rows = query("SELECT * FROM onusreport.buy_sell_diary LIMIT 1;")
print(rows[:1])
