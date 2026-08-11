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

TERMS = [
    # pork
    "carnitas recipe",
    "ribs recipe",
    "ham recipe",
    # beef
    "burger recipe",
    "meatballs recipe",
    "pot roast recipe",
    "beef stew recipe",
    "steak recipe",
    "brisket recipe",
    "beef stroganoff recipe",
    "birria recipe",
    # chicken
    "fried chicken recipe",
    "chicken noodle soup recipe",
    "chicken breast recipe",
    "chicken wings recipe",
    "chicken pot pie recipe",
    "chicken salad recipe",
    "chicken katsu recipe",
    "chicken adobo recipe",
    "chicken alfredo recipe",
    # lamb / turkey
    "lamb chops recipe",
    "turkey recipe",
    # seafood
    "shrimp scampi recipe",
    "fish and chips recipe",
    "tuna salad recipe",
    "fish tacos recipe",
    "ceviche recipe",
    "crab cakes recipe",
    # pasta / noodles
    "mac and cheese recipe",
    "spaghetti bolognese recipe",
    "pho recipe",
    "lo mein recipe",
    # rice
    "risotto recipe",
    "jambalaya recipe",
    "burrito recipe",
    "sushi recipe",
    # soups / stews
    "potato soup recipe",
    "tomato soup recipe",
    "gumbo recipe",
    "goulash recipe",
    "french onion soup recipe",
    # breakfast / eggs
    "quiche recipe",
    "scrambled eggs recipe",
    "waffle recipe",
    "blueberry muffins recipe",
    "cinnamon rolls recipe",
    "scones recipe",
    "deviled eggs recipe",
    # baked / desserts
    "bread recipe",
    "sourdough bread recipe",
    "pizza recipe",
    "tiramisu recipe",
    "carrot cake recipe",
    "cupcakes recipe",
    "fudge recipe",
    "ice cream recipe",
    "pie crust recipe",
    "pumpkin pie recipe",
    "sugar cookies recipe",
    # international
    "enchiladas recipe",
    "quesadilla recipe",
    "empanadas recipe",
    "dumplings recipe",
    "spring rolls recipe",
    "shepherds pie recipe",
    "jollof rice recipe",
    "tagine recipe",
]

batches = [[ANCHOR] + TERMS[i : i + 4] for i in range(0, len(TERMS), 4)]

results = {}
anchor_means = {}
failed = []
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
            print(f"batch {bi} ok, anchor mean {m[ANCHOR]:.2f}", flush=True)
            break
        except Exception as e:
            print(f"batch {bi} attempt {attempt}: {type(e).__name__}", flush=True)
            time.sleep(12 + attempt * 8)
    else:
        print(f"batch {bi} FAILED", flush=True)
        failed.extend([k for k in kw if k != ANCHOR])
    time.sleep(9)

out = {}
for k, d in results.items():
    bi, v = list(d.items())[0]
    if anchor_means.get(bi):
        out[k] = round(100.0 * v / anchor_means[bi], 1)
json.dump(
    {
        "anchor_means": anchor_means,
        "raw": results,
        "index_anchor100": out,
        "failed": failed,
    },
    open("trends_sweep.json", "w"),
    indent=1,
)
for k, v in sorted(out.items(), key=lambda x: -x[1]):
    print(f"{v:7.1f}  {k}")
if failed:
    print("FAILED:", failed)
