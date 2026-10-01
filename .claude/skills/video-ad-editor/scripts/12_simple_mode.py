# -*- coding: utf-8 -*-
"""الوضع البسيط — «الصور ورا الراس». بديل الخطوة 7 و9 (المشاهد المرسومة) فقط؛ كل الباقي مشترك.
  python3 12_simple_mode.py <work> init                  → simple.json (مسودة من caps.json + theme.json)
  python3 12_simple_mode.py <work> preview 0.5 3 7.8 ... → simple-sheet.jpg (ورقة لقطات بلا رندر كامل)
  python3 12_simple_mode.py <work> range 6 10            → simple-range.mp4 (تجربة نافذة)
  python3 12_simple_mode.py <work> render                → ad-final.mp4 (صورة + صوت cutz + sfx.wav لو موجود)
بعدها: 06b_master.sh و09_srt.py كالعادة.

يقرأ: cutz.mp4 · caps.json · theme.json · simple.json · broll/ · logo
الطبقات: الفيديو (بزوم اللقطة) → كروت البي-رول + الأكسنت (ورا الشخص) → الشخص مقصوص فوقها
        → كروت قدّام (behind:false) → الهوك / الكابشن → الإوترو بعد نهاية الكلام"""
import json, sys, os, math, subprocess, urllib.request
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter, features

W_, H_, FPS = 1080, 1920, 30
WORK = os.path.abspath(sys.argv[1]); CMD = sys.argv[2] if len(sys.argv) > 2 else "render"; ARGS = sys.argv[3:]
SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get("VAE_CACHE", os.path.expanduser("~/.cache/video-ad-editor"))
SEG_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
           "selfie_segmenter/float16/latest/selfie_segmenter.tflite")
J = lambda n: os.path.join(WORK, n)
TH = json.load(open(J("theme.json"))) if os.path.exists(J("theme.json")) else {}
CAPS = json.load(open(J("caps.json")))

def hexrgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
def lum(c): return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]

# ═══ init: مسودة simple.json ═══════════════════════════════════════════════════
if CMD == "init":
    words = [w for c in CAPS["cards"] for w in c["w"]]
    # قسّم لكروت ≤٣ كلمات — علامة ترقيم أو سكتة > 0.25ث = حد إجباري
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i+1]["s"] - w["e"] if i + 1 < len(words) else 9
        if len(cur) == 3 or w["t"][-1] in "؟?.!،,:" or gap > 0.25:
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    # دمج كرت كلمة وحدة مع اللي قبله لو ما فيه حد جملة
    out = []
    for c in chunks:
        if out and len(c) == 1 and len(out[-1]) < 3 and out[-1][-1]["t"][-1] not in "؟?.!" \
                and c[0]["s"] - out[-1][-1]["e"] < 0.25:
            out[-1] = out[-1] + c
        else: out.append(c)
    chunks = out
    # الهوك = الكلمات لين أول ؟/. (≤٥ كلمات) وإلا أول كرت
    hook, n = [], 0
    for i, w in enumerate(words[:5]):
        if w["t"][-1] in "؟?.!": hook = words[:i+1]; break
    if not hook: hook = chunks[0]
    hook_end = round(hook[-1]["e"] + 0.15, 3)
    caps = [{"s": c[0]["s"], "e": c[-1]["e"], "text": " ".join(w["t"] for w in c)}
            for c in chunks if c[0]["s"] >= hook[-1]["s"] + 0.01]
    total = CAPS["total"]
    starts = [c["s"] for c in caps]
    shots, t0, close = [], 0.0, False
    for c in [hook_end] + [x for x in starts if x > hook_end + 0.5] + [total]:
        if c not in (total, hook_end) and (c - t0 < 2.8 or total - c < 1.5): continue
        if c - t0 < 0.3: continue
        shots.append({"s": round(t0, 3), "e": round(c, 3), "zoom": 1.25 if close else 1.0, "cy": 0.3})
        t0, close = c, not close
    bg = TH.get("bg", "#0B0B6B")
    plan = {
        "colors": {"arrow": bg if lum(hexrgb(bg)) < 110 else TH.get("acc", "#0B0B6B"),
                   "circle": TH.get("acc", "#E9B85A"), "outro_bg": bg,
                   "outro_name": TH.get("acc", "#E9B85A")},
        "hook": {"words": [{"w": w["t"], "s": w["s"]} for w in hook], "e": hook_end,
                 "side": "left", "kashida": True},
        "captions": caps, "shots": shots, "broll": [],
        "outro": {"dur": 3.2, "logo": TH.get("logo", "logo.png"), "name": ""},
    }
    json.dump(plan, open(J("simple.json"), "w"), ensure_ascii=False, indent=1)
    print(f"✅ simple.json — هوك: {' '.join(w['t'] for w in hook)} (لين {hook_end}s) · "
          f"{len(caps)} كابشن · {len(shots)} لقطة · broll فاضي (عبّه)")
    for c in caps: print(f"  {c['s']:6.2f}-{c['e']:6.2f}  {c['text']}")
    sys.exit(0)

# ═══ الإعداد للرسم ═══════════════════════════════════════════════════════════
P = json.load(open(J("simple.json")))
COL = P.get("colors", {})
INK = (255, 255, 255)                       # الكابشن فوق الفيديو أبيض دائماً
ARROW = hexrgb(COL.get("arrow", "#0B0B6B")); CIRC = hexrgb(COL.get("circle", "#E9B85A"))
TOTAL = float(CAPS["total"])
OUT = P.get("outro") or {}
_lp = J(OUT.get("logo") or "_")
OUT_DUR = float(OUT.get("dur", 0)) if (os.path.exists(_lp) or OUT.get("name")) else 0.0
RAQM = features.check("raqm")
if not RAQM:
    import arabic_reshaper
    from bidi.algorithm import get_display

def is_ar(s): return any("؀" <= c <= "ۿ" for c in s)
def shape(s):
    """بدون raqm: نشكّل بـarabic_reshaper. الأشكال «المعزولة» نرجعها للحرف الأصلي —
    بعض الخطوط ما فيها هالرموز وتطلع مربعات، والحرف الأصلي نفس الشكل"""
    if RAQM or not is_ar(s): return s
    import unicodedata
    out = get_display(arabic_reshaper.reshape(s))
    return "".join(chr(int(d.split()[1], 16)) if (d := unicodedata.decomposition(c)).startswith("<isolated>")
                   and len(d.split()) == 2 else c for c in out)

_fc = {}
def font(weight, size):
    """خط الوضع البسيط: IBM Plex Sans Arabic (نفس خط الريل المرجعي) — مو خط الثيم.
    يتغيّر بـ"font" بـsimple.json (اسم العائلة، والملف {fam}-{weight}.ttf بمجلد الشغل أو assets/fonts)"""
    key = (weight, size)
    if key in _fc: return _fc[key]
    fam = P.get("font", "IBMPlexSansArabic").replace(" ", "")
    lay = ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC
    f = None
    for d in (WORK, J("fonts"), os.path.join(SK, "assets", "fonts")):
        for fn in (f"{fam}-{weight}.ttf", f"{fam}.ttf", f"IBMPlexSansArabic-{weight}.ttf"):
            p = os.path.join(d, fn)
            if os.path.exists(p):
                f = ImageFont.truetype(p, size, layout_engine=lay)
                try: f.set_variation_by_name(weight)
                except Exception: pass
                break
        if f: break
    _fc[key] = f; return f

clamp = lambda x, a=0.0, b=1.0: max(a, min(b, x))
def ease_out(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_back(x, k=1.6): x = clamp(x); x -= 1; return 1 + (k + 1) * x**3 + k * x**2

def blend(dst, rgba, x, y, a=1.0):
    """RGBA (uint8) فوق dst (float32 RGB) عند x,y مع قصّ الحواف"""
    if a <= 0.003: return
    h, w = rgba.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(dst.shape[1], x + w), min(dst.shape[0], y + h)
    if x1 <= x0 or y1 <= y0: return
    src = rgba[y0-y:y1-y, x0-x:x1-x].astype(np.float32)
    al = src[..., 3:4] / 255.0 * a
    dst[y0:y1, x0:x1] = dst[y0:y1, x0:x1] * (1 - al) + src[..., :3] * al

def scaled(rgba, s):
    if abs(s - 1) < 1e-3: return rgba
    h, w = rgba.shape[:2]
    return cv2.resize(rgba, (max(1, int(w*s)), max(1, int(h*s))), interpolation=cv2.INTER_LINEAR)

def text_rgba(txt, fnt, color, shadow=True, pad=40):
    txt = shape(txt)
    l, t, r, b = fnt.getbbox(txt)
    w, h = r - l + pad*2, b - t + pad*2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - l, pad - t + 4), txt, font=fnt, fill=(0, 0, 0, 120))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(im).text((pad - l, pad - t), txt, font=fnt, fill=tuple(color) + (255,))
    return np.array(im)

# ── الكشيدة ──
NOJOIN = set("اأإآدذرزوؤةىءـ")
def kashida_spots(w):
    ar = lambda c: "ء" <= c <= "ي"
    return [i for i in range(len(w) - 1) if ar(w[i]) and w[i] not in NOJOIN and ar(w[i+1])]

def stretch(word, fnt, target):
    """يمد الكلمة بالتطويل (ـ) لين توصل عرض target — بنقطة أو نقطتين قرب الوسط"""
    spots = kashida_spots(word)
    if not spots: return word
    spots.sort(key=lambda i: abs(i - (len(word) - 1) / 2))
    pick = sorted(spots[:2] if len(word) >= 6 and len(spots) > 1 else spots[:1])
    best = word
    for n in range(1, 40):
        cnt = [n // len(pick) + (1 if j < n % len(pick) else 0) for j in range(len(pick))]
        s, last = "", 0
        for j, i in enumerate(pick): s += word[last:i+1] + "ـ" * cnt[j]; last = i + 1
        s += word[last:]
        if fnt.getlength(shape(s)) > target: break
        best = s
    return best

# ═══ الهوك ═══════════════════════════════════════════════════════════════════
HOOK = P.get("hook") or {}; HW = HOOK.get("words", []); hook_imgs = []
if HW:
    size = int(HOOK.get("size", 150 if len(HW) <= 4 else 128))
    hf = font(HOOK.get("weight", "Bold"), size)
    raw = [w["w"] for w in HW]
    colw = HOOK["width"] * W_ if HOOK.get("width") else \
        min(0.40 * W_, max(hf.getlength(shape(w)) for w in raw) * 1.15)
    for w in raw:
        hook_imgs.append(text_rgba(stretch(w, hf, colw) if HOOK.get("kashida", True) else w, hf, INK, pad=30))
    HOOK_LH = int(size * 1.22); HOOK_TOP = int(HOOK.get("top", 0.36) * H_)
    # يمين: العمود يوقف قبل منطقة أزرار انستقرام (180px)
    HOOK_CX = int(HOOK["cx"] * W_) if "cx" in HOOK else \
        (int(0.29 * W_) if HOOK.get("side", "left") == "left" else int(W_ - 190 - colw / 2))
HOOK_END = float(HOOK.get("e", 0)) if HW else 0.0

def draw_hook(fr, t):
    if not HW or t >= HOOK_END: return
    for i, (w, im) in enumerate(zip(HW, hook_imgs)):
        p = (t - w["s"]) / 0.18
        if p <= 0: continue
        cy = HOOK_TOP + i * HOOK_LH + int((1 - ease_out(p)) * 26)
        blend(fr, im, HOOK_CX + int(colw / 2) - im.shape[1] + 30, cy - im.shape[0] // 2, ease_out(p))

# ═══ الكابشن ═════════════════════════════════════════════════════════════════
CAPL = P.get("captions", [])
CF = font(P.get("caption_weight", "Bold"), int(P.get("caption_size", 62))); CAP_Y = float(P.get("caption_y", 0.585))
_cc = {}
def cap_img(txt):
    if txt not in _cc:
        ws = txt.split()
        if CF.getlength(shape(txt)) > 0.76 * W_ and len(ws) > 1:
            k = len(ws) // 2
            a, b = text_rgba(" ".join(ws[:k]), CF, INK), text_rgba(" ".join(ws[k:]), CF, INK)
            w = max(a.shape[1], b.shape[1]); gap = -40
            im = np.zeros((a.shape[0] + b.shape[0] + gap, w, 4), np.uint8)
            for src, yy in ((a, 0), (b, a.shape[0] + gap)):
                xx = (w - src.shape[1]) // 2; reg = im[yy:yy+src.shape[0], xx:xx+src.shape[1]]
                np.maximum(reg, src, out=reg)
            _cc[txt] = im
        else: _cc[txt] = text_rgba(txt, CF, INK)
    return _cc[txt]

def draw_caption(fr, t):
    if t < HOOK_END: return
    for i, c in enumerate(CAPL):
        nxt = CAPL[i+1]["s"] if i + 1 < len(CAPL) else 1e9
        if c["s"] - 0.02 <= t < min(c["e"] + c.get("hold", 0.15), nxt - 0.02):
            im = cap_img(c["text"]); p = (t - c["s"]) / 0.12
            im2 = scaled(im, 0.92 + 0.08 * ease_out(p))
            blend(fr, im2, (W_ - im2.shape[1]) // 2, int(CAP_Y * H_) - im2.shape[0] // 2, ease_out(p))
            return

# ═══ البي-رول ════════════════════════════════════════════════════════════════
POS = {"tl": (0.28, 0.235), "tr": (0.72, 0.235), "tc": (0.50, 0.225), "ml": (0.27, 0.42), "mr": (0.73, 0.42)}
VIDEXT = (".mp4", ".mov", ".m4v", ".webm")

class Card:
    def __init__(self, d):
        self.d = d; self.s, self.e = float(d["s"]), float(d["e"])
        self.src = J(d["src"]); self.vid = self.src.lower().endswith(VIDEXT)
        pos = d.get("pos", "tl")
        self.cx, self.cy = POS[pos] if isinstance(pos, str) else pos
        self.cw = int(d.get("w", 0.75 if pos == "tc" else 0.44) * W_); self.r = int(d.get("radius", 14))
        if self.vid:
            self.cap = cv2.VideoCapture(self.src); self.vfps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.nf = max(1, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))
            ok, f0 = self.cap.read(); self.last = (0, f0); self.size(f0.shape[1], f0.shape[0])
        else:
            im = Image.open(self.src).convert("RGB"); self.size(*im.size)
            self.static = self.frame_rgba(np.array(im)[..., ::-1])

    def size(self, w, h):
        self.ch = int(self.cw * h / w); mh = int(self.d.get("max_h", 0.36) * H_)
        if self.ch > mh: self.ch = mh; self.cw = int(mh * w / h)
        self.x = int(self.cx * W_ - self.cw / 2); self.y = int(self.cy * H_ - self.ch / 2)

    def frame_rgba(self, bgr):
        """صورة → كرت بزوايا دائرية + ظل خفيف (RGBA بهامش 40)"""
        m, r = 40, self.r
        img = cv2.resize(bgr, (self.cw, self.ch), interpolation=cv2.INTER_AREA)[..., ::-1]
        out = np.zeros((self.ch + 2*m, self.cw + 2*m, 4), np.uint8)
        mask = np.zeros((self.ch, self.cw), np.uint8)
        cv2.rectangle(mask, (r, 0), (self.cw - r, self.ch), 255, -1)
        cv2.rectangle(mask, (0, r), (self.cw, self.ch - r), 255, -1)
        for cx, cy in ((r, r), (self.cw-r-1, r), (r, self.ch-r-1), (self.cw-r-1, self.ch-r-1)):
            cv2.circle(mask, (cx, cy), r, 255, -1, cv2.LINE_AA)
        sh = np.zeros(out.shape[:2], np.uint8); sh[m+10:m+10+self.ch, m:m+self.cw] = mask
        out[..., 3] = (cv2.GaussianBlur(sh, (0, 0), 14) * 0.35).astype(np.uint8)
        reg = out[m:m+self.ch, m:m+self.cw]
        reg[..., :3] = (img * (mask[..., None] / 255.0)).astype(np.uint8)
        reg[..., 3] = np.maximum(reg[..., 3], mask)
        return out

    def get(self, t):
        if not self.vid: return self.static
        k = int((t - self.s) * self.vfps) % self.nf
        if k != self.last[0]:
            if k != self.last[0] + 1: self.cap.set(cv2.CAP_PROP_POS_FRAMES, k)
            ok, f = self.cap.read()
            if ok: self.last = (k, f)
        return self.frame_rgba(self.last[1])

    def draw(self, fr, t):
        pi, po = (t - self.s) / 0.28, (self.e - t) / 0.2
        a, s = (ease_out(pi), 0.86 + 0.14 * ease_back(pi)) if pi < 1 else \
               (ease_out(po), 0.96 + 0.04 * po) if po < 1 else (1.0, 1.0)
        im = scaled(self.get(t), s)
        blend(fr, im, int(self.cx * W_ - im.shape[1] / 2), int(self.cy * H_ - im.shape[0] / 2), a)
        if self.d.get("accent") in ACCENTS: ACCENTS[self.d["accent"]](fr, self, t, a)

def acc_arrow(fr, c, t, a):
    """سهم نمو ينرسم من تحت-يسار الكرت لفوق-يمينه (تقارير، أرقام، نمو)"""
    p = ease_out((t - c.s - 0.15) / 0.75)
    if p <= 0: return
    pts = np.array([(-0.08, 1.05), (0.30, 0.62), (0.48, 0.78), (1.08, -0.04)]) * (c.cw, c.ch) + (c.x, c.y)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1); L = seg.sum() * p
    path, acc = [pts[0]], 0.0
    for i, l in enumerate(seg):
        if acc + l >= L: path.append(pts[i] + (pts[i+1] - pts[i]) * (L - acc) / l); break
        path.append(pts[i+1]); acc += l
    path = np.array(path); th = int(c.cw * 0.055); ov = np.zeros((H_, W_, 4), np.uint8)
    cv2.polylines(ov, [path.astype(np.int32)], False, ARROW + (255,), th, cv2.LINE_AA)
    d = path[-1] - path[-2]; d = d / (np.linalg.norm(d) + 1e-6); nrm = np.array([-d[1], d[0]])
    tri = np.array([path[-1] + d*th*1.2, path[-1] - d*th*0.6 + nrm*th*1.5, path[-1] - d*th*0.6 - nrm*th*1.5])
    cv2.fillPoly(ov, [tri.astype(np.int32)], ARROW + (255,), cv2.LINE_AA)
    blend(fr, ov, 0, 0, a)

def acc_circle(fr, c, t, a):
    """دائرة تحديد حول تفصيلة بالكرت — focus: [x,y] نسبي · focus_r"""
    p = ease_out((t - c.s - 0.2) / 0.6)
    if p <= 0: return
    fx, fy = c.d.get("focus", [0.5, 0.5]); r = int(c.cw * c.d.get("focus_r", 0.22))
    ov = np.zeros((H_, W_, 4), np.uint8)
    cv2.ellipse(ov, (int(c.x + fx*c.cw), int(c.y + fy*c.ch)), (r, int(r*0.7)), -20, 0, 360*p, CIRC + (255,),
                max(6, r // 9), cv2.LINE_AA)
    blend(fr, ov, 0, 0, a)

ACCENTS = {"arrow": acc_arrow, "circle": acc_circle}
CARDS = [Card(d) for d in P.get("broll", [])]

# ═══ قصّ الشخص (mediapipe — ماك ولينكس وويندوز) ══════════════════════════════
_seg = None; _prev = None
def person_mask(rgb):
    global _seg, _prev
    if _seg is None:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
        mpath = os.path.join(CACHE, "selfie_segmenter.tflite")
        if not os.path.exists(mpath):
            os.makedirs(CACHE, exist_ok=True); urllib.request.urlretrieve(SEG_URL, mpath)
        _seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=mpath), output_confidence_masks=True))
        _seg._mp = mp
    mp = _seg._mp
    r = _seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    m = cv2.resize(r.confidence_masks[0].numpy_view().astype(np.float32), (W_, H_))
    m = cv2.GaussianBlur(np.clip((m - 0.35) / 0.35, 0, 1), (0, 0), 2.2)
    if _prev is not None: m = 0.65 * m + 0.35 * _prev       # تنعيم زمني — الحواف ما ترجف
    _prev = m
    return m[..., None]

# ═══ اللقطات (punch-in فوق زوم cutz) ═════════════════════════════════════════
SHOTS = P.get("shots", [])
def zoom(frame, t):
    s = next((x for x in SHOTS if x["s"] <= t < x["e"]), {"zoom": 1.0})
    z = float(s.get("zoom", 1.0)) * (1 + float(s.get("push", 0)) *
        clamp((t - s.get("s", 0)) / max(0.1, s.get("e", 1) - s.get("s", 0))))
    if z <= 1.001: return frame
    cw, ch = int(W_ / z), int(H_ / z)
    x, y = int((W_ - cw) * s.get("cx", 0.5)), int((H_ - ch) * s.get("cy", 0.3))
    return cv2.resize(frame[y:y+ch, x:x+cw], (W_, H_), interpolation=cv2.INTER_CUBIC)

# ═══ الإوترو ═════════════════════════════════════════════════════════════════
_logo = None
def outro_frame(t):
    """شعار يلف ويكبر بتوهّج أبيض → يصغر ويطلع الاسم بمسح → يطفي"""
    global _logo
    fr = np.zeros((H_, W_, 3), np.float32); fr[:] = hexrgb(COL.get("outro_bg", TH.get("bg", "#0B0B6B")))
    name = OUT.get("name", "")
    if _logo is None and os.path.exists(_lp):
        im = Image.open(_lp).convert("RGBA"); s = 0.42 * W_ / max(im.size)
        _logo = np.array(im.resize((int(im.width*s), int(im.height*s)), Image.LANCZOS))
    move = ease_out((t - 0.95) / 0.5) if name else 0.0
    if _logo is not None and t > 0.05:
        p = (t - 0.05) / 0.6
        sc = (0.25 + 0.75 * ease_back(p, 2.0)) * (1 - 0.45 * move); ang = (1 - ease_out(p)) * -140
        h, w = _logo.shape[:2]; big = int(max(w, h) * 1.5)
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, sc); M[0, 2] += (big - w) / 2; M[1, 2] += (big - h) / 2
        rot = cv2.warpAffine(_logo, M, (big, big), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        cx, cy = W_ // 2, int(H_ * (0.5 - 0.07 * move))
        glow = clamp(1 - (t - 0.35) / 0.9) * 0.9
        if glow > 0.01:
            g = rot.copy(); g[..., :3] = 255; g[..., 3] = cv2.GaussianBlur(g[..., 3], (0, 0), 28)
            blend(fr, g, cx - big // 2, cy - big // 2, glow)
        blend(fr, rot, cx - big // 2, cy - big // 2, ease_out(p * 2))
    if name:
        im = text_rgba(name, font("Bold", int(OUT.get("size", 120))), hexrgb(COL.get("outro_name", "#E9B85A")),
                       shadow=False, pad=10)
        p = ease_out((t - (1.05 if _logo is not None else 0.2)) / 0.6)
        if p > 0:
            w = im.shape[1]; vis = int(w * p); im = im.copy()
            if is_ar(name): im[:, :w - vis, 3] = 0
            else: im[:, vis:, 3] = 0
            y = int(H_ * (0.56 if _logo is not None else 0.5))
            blend(fr, im, (W_ - w) // 2, y - im.shape[0] // 2)
    return fr * clamp((OUT_DUR - t) / 0.35)

# ═══ تركيب فريم ══════════════════════════════════════════════════════════════
def compose(rgb, t):
    if t >= TOTAL: return outro_frame(t - TOTAL)
    base = zoom(rgb, t); fr = base.astype(np.float32)
    act = [c for c in CARDS if c.s <= t < c.e]
    behind = [c for c in act if c.d.get("behind", True)]
    if behind:
        for c in behind: c.draw(fr, t)
        m = person_mask(base); fr = base.astype(np.float32) * m + fr * (1 - m)
    for c in act:
        if not c.d.get("behind", True): c.draw(fr, t)
    draw_hook(fr, t); draw_caption(fr, t)
    return fr

SRC = J("cutz.mp4")
if CMD == "preview":
    ts = [float(x) for x in ARGS]; thumbs = []
    for t in ts:
        _prev = None
        if t < TOTAL:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", SRC, "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            rgb = np.frombuffer(raw[:W_*H_*3], np.uint8).reshape(H_, W_, 3)
        else: rgb = None
        im = np.clip(compose(rgb, t), 0, 255).astype(np.uint8)
        th = cv2.resize(im, (360, 640), interpolation=cv2.INTER_AREA)
        cv2.putText(th, f"{t:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2, cv2.LINE_AA)
        thumbs.append(th)
    cols = min(6, len(thumbs)); rows = -(-len(thumbs) // cols)
    thumbs += [np.zeros_like(thumbs[0])] * (rows * cols - len(thumbs))
    sheet = np.vstack([np.hstack(thumbs[r*cols:(r+1)*cols]) for r in range(rows)])
    cv2.imwrite(J("simple-sheet.jpg"), sheet[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"✅ simple-sheet.jpg — {len(ts)} لقطة"); sys.exit(0)

# ═══ رندر كامل / نافذة ═══════════════════════════════════════════════════════
t0, t1, dst = 0.0, TOTAL + OUT_DUR, J("ad-final.mp4")
if CMD == "range": t0, t1, dst = float(ARGS[0]), float(ARGS[1]), J("simple-range.mp4")
dur = t1 - t0
sfx = J("sfx.wav") if os.path.exists(J("sfx.wav")) else None
ain = ["-ss", f"{t0:.3f}", "-i", SRC] + (["-ss", f"{t0:.3f}", "-i", sfx] if sfx else [])
af = (f"[1:a]apad=whole_dur={dur:.3f}[a0];[2:a]apad=whole_dur={dur:.3f}[a1];"
      f"[a0][a1]amix=inputs=2:duration=first:normalize=0,atrim=0:{dur:.3f}[ao]") if sfx else \
     f"[1:a]apad=whole_dur={dur:.3f},atrim=0:{dur:.3f}[ao]"
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", SRC, "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W_}x{H_}",
                        "-r", str(FPS), "-i", "-"] + ain +
                       ["-filter_complex", af, "-map", "0:v", "-map", "[ao]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "8M", "-bufsize", "16M",
                        "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                        "-t", f"{dur:.3f}", "-movflags", "+faststart", "-y", dst], stdin=subprocess.PIPE)
N = int(round(dur * FPS)); last = np.zeros((H_, W_, 3), np.uint8)
for k in range(N):
    t = t0 + k / FPS
    if t < TOTAL:
        raw = dec.stdout.read(W_ * H_ * 3)
        if len(raw) == W_ * H_ * 3: last = np.frombuffer(raw, np.uint8).reshape(H_, W_, 3)
    enc.stdin.write(np.clip(compose(last, t), 0, 255).astype(np.uint8).tobytes())
    if k % 90 == 0: print(f"\r{t:6.1f}/{t1:.1f}s", end="", flush=True)
enc.stdin.close(); enc.wait(); dec.kill()
print(f"\n✅ {os.path.basename(dst)} — {dur:.2f}s ({N} فريم)")
