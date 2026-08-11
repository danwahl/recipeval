import json
import time

import requests
from pytrends.request import TrendReq

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


class Pt(TrendReq):
    def GetGoogleCookie(self):
        return dict(
            filter(
                lambda i: i[0] == "NID",
                requests.get(
                    "https://trends.google.com/?geo=US",
                    timeout=30,
                    headers={"User-Agent": UA},
                ).cookies.items(),
            )
        )


ANCHOR = "banana bread recipe"
batches = [
    [
        ANCHOR,
        "meatloaf recipe",
        "chili recipe",
        "pancake recipe",
        "chocolate chip cookies recipe",
    ],
    [
        ANCHOR,
        "french toast recipe",
        "lasagna recipe",
        "tacos recipe",
        "chicken parmesan recipe",
    ],
    [
        ANCHOR,
        "carbonara recipe",
        "chocolate cake recipe",
        "chicken curry recipe",
        "tonkotsu ramen recipe",
    ],
    [
        ANCHOR,
        "pad thai recipe",
        "cobb salad recipe",
        "baked salmon recipe",
        "cookies recipe",
    ],
    [
        ANCHOR,
        "pizza dough recipe",
        "fried rice recipe",
        "biryani recipe",
        "brownie recipe",
    ],
    [
        ANCHOR,
        "omelette recipe",
        "crepe recipe",
        "cheesecake recipe",
        "apple pie recipe",
    ],
    [ANCHOR, "butter chicken recipe", "paella recipe", "ramen recipe", "salmon recipe"],
]

results = {}
anchor_means = {}
for bi, kw in enumerate(batches):
    for attempt in range(8):
        try:
            pt = Pt(hl="en-US", tz=0, requests_args={"headers": {"User-Agent": UA}})
            pt.build_payload(kw, timeframe="today 12-m", geo="")
            df = pt.interest_over_time()
            m = df.drop(columns=["isPartial"]).mean()
            anchor_means[bi] = float(m[ANCHOR])
            for k in kw:
                if k != ANCHOR:
                    results.setdefault(k, {})[bi] = float(m[k])
            print(f"batch {bi} ok, anchor mean {m[ANCHOR]:.2f}")
            break
        except Exception as e:
            print(f"batch {bi} attempt {attempt}: {type(e).__name__}")
            time.sleep(12 + attempt * 8)
    else:
        print(f"batch {bi} FAILED")
    time.sleep(8)

# normalize: anchor = 100
out = {ANCHOR: 100.0}
for k, d in results.items():
    bi, v = list(d.items())[0]
    if anchor_means.get(bi):
        out[k] = round(100.0 * v / anchor_means[bi], 1)
json.dump(
    {"anchor_means": anchor_means, "raw": results, "index_anchor100": out},
    open("trends_results.json", "w"),
    indent=1,
)
for k, v in sorted(out.items(), key=lambda x: -x[1]):
    print(f"{v:7.1f}  {k}")
