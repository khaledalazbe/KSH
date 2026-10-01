# -*- coding: utf-8 -*-
"""مسودة plan.json من a.json — على تايم-لاين cut.mp4.
python3 plan_init.py <work> [--hook N]   (N = عدد كروت الكابشن اللي تصير هوك كبير، افتراضي: أول جملة)

يكتب:
  words.json  كل كلمة بتوقيتها على التايم-لاين المقصوص (مرجعك لتوقيت البي-رول)
  plan.json   مسودة: hook + captions + shots (لقطة واسعة/قريبة بالتناوب) + broll فاضي
⚠️ يكتب فوق plan.json — لو عدّلته يدوياً، استخدم --words-only"""
import json, sys, os
W = os.path.abspath(sys.argv[1]); args = sys.argv[2:]
cut = json.load(open(os.path.join(W, "cut.json")))
keep = cut["keep"]
off, acc = [], 0.0
for s, e in keep: off.append(acc); acc += e - s
TOTAL = acc

def m(t):
    """زمن المصدر → زمن cut.mp4"""
    i = max(j for j in range(len(keep)) if keep[j][0] <= t + 1e-3) if t >= keep[0][0] else 0
    return round(min(max(t, keep[i][0]), keep[i][1]) - keep[i][0] + off[i], 3)

tr = json.load(open(os.path.join(W, "a.json")))
cards = []
for sg in tr["segments"]:
    ws = [{"w": w["word"], "s": m(w["start"]), "e": m(w["end"])} for w in sg["words"]]
    cards.append({"s": ws[0]["s"], "e": ws[-1]["e"], "text": sg["text"], "words": ws})
words = [w for c in cards for w in c["words"]]
json.dump({"total": round(TOTAL, 3), "words": words}, open(os.path.join(W, "words.json"), "w"),
          ensure_ascii=False, indent=1)
print(f"words.json — {len(words)} كلمة · {TOTAL:.2f}s")
if "--words-only" in args: sys.exit(0)

# الهوك = أول جملة (لين أول ؟ أو . ) لو كانت ≤ ٥ كلمات، وإلا أول كرت · أو --hook N كروت
if "--hook" in args:
    nh = int(args[args.index("--hook") + 1])
else:
    nh, n = 1, 0
    for i, c in enumerate(cards):
        n += len(c["words"])
        if n > 5: break
        if c["text"][-1] in "؟?.!": nh = i + 1; break
hook_words = [w for c in cards[:nh] for w in c["words"]][:5]
hook_end = cards[nh-1]["e"] if nh else 0

# لقطات: الهوك واسع، وبعده تبديل واسع↔قريب عند حدود الكروت كل ~٣ ثواني (القص يصير على بداية كلمة)
starts = sorted({round(c["s"], 3) for c in cards[nh:]} | {round(o, 3) for o in off[1:]})
shots, t0, close = [], 0.0, False
for c in [hook_end] + [x for x in starts if x > hook_end + 0.5] + [TOTAL]:
    if c != TOTAL and c != hook_end and c - t0 < 2.8: continue
    if TOTAL - c < 1.5 and c != TOTAL: continue
    if c - t0 < 0.3: continue
    shots.append({"s": round(t0, 3), "e": round(c, 3), "zoom": 1.32 if close else 1.0, "cy": 0.30})
    t0, close = c, not close

plan = {
    "theme": {"brand": "#0B0B6B", "accent": "#E9B85A", "ink": "#FFFFFF",
              "font": "Tajawal-Bold.ttf", "hook_font": "Tajawal-Black.ttf"},
    "hook": {"words": [{"w": w["w"], "s": w["s"]} for w in hook_words], "e": round(hook_end, 3),
             "side": "left", "kashida": True},
    "captions": [{"s": c["s"], "e": c["e"], "text": c["text"]} for c in cards[nh:]],
    "shots": shots,
    "broll": [],
    "outro": {"dur": 3.2, "logo": "logo.png", "name": "", "bg": None},
}
json.dump(plan, open(os.path.join(W, "plan.json"), "w"), ensure_ascii=False, indent=1)
print(f"plan.json — هوك {len(hook_words)} كلمات حتى {hook_end:.2f}s · {len(plan['captions'])} كابشن · "
      f"{len(shots)} لقطة")
for c in cards:
    print(f"  {c['s']:6.2f}-{c['e']:6.2f}  " + " ".join(f"{w['w']}({w['s']:.2f})" for w in c["words"]))
