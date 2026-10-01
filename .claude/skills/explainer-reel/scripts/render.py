# -*- coding: utf-8 -*-
"""الرندر: cut.mp4 + plan.json → reel.mp4 (أو ورقة لقطات للمعاينة).
  python3 render.py <work>                         → <work>/reel.mp4
  python3 render.py <work> --preview 0.8 3.4 9 ... → <work>/sheet.jpg (لقطات بدون رندر كامل)
  python3 render.py <work> --range 3 9             → <work>/range.mp4 (نافذة بس، للتجربة)

الطبقات من تحت لفوق:
  الفيديو (بزوم اللقطة) → كروت البي-رول + الأكسنتات (ورا الشخص) → الشخص مقصوص فوقها
  → كروت قدّام (behind:false) → الكابشن / الهوك → (بعد نهاية الكلام) الإوترو"""
import json, sys, os, math, subprocess
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W_, H_, FPS = 1080, 1920, 30
WORK = os.path.abspath(sys.argv[1]); ARGS = sys.argv[2:]
SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.environ.get("REEL_MODELS", os.path.expanduser("~/.cache/explainer-reel/models"))
P = json.load(open(os.path.join(WORK, "plan.json")))
TH = P.get("theme", {})
TOTAL = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              os.path.join(WORK, "cut.mp4")], capture_output=True, text=True).stdout)
OUT = P.get("outro") or {}
OUT_DUR = float(OUT.get("dur", 0)) if (OUT.get("logo") and os.path.exists(os.path.join(WORK, OUT["logo"]))) \
    or OUT.get("name") else 0.0

def hexrgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
BRAND, ACC, INK = hexrgb(TH.get("brand", "#0B0B6B")), hexrgb(TH.get("accent", "#E9B85A")), hexrgb(TH.get("ink", "#FFFFFF"))

def font(name, size):
    for d in (WORK, os.path.join(WORK, "fonts"), os.path.join(SK, "assets", "fonts")):
        p = os.path.join(d, name)
        if os.path.exists(p): return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.RAQM)
    raise SystemExit(f"الخط {name} مو موجود")

# ── أدوات ──────────────────────────────────────────────────────────────────────
clamp = lambda x, a=0.0, b=1.0: max(a, min(b, x))
def ease_out(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_back(x, k=1.6): x = clamp(x); x -= 1; return 1 + (k + 1) * x**3 + k * x**2

def blend(dst, rgba, x, y, a=1.0):
    """يركّب صورة RGBA (numpy uint8) على dst (float32 RGB) عند x,y مع قصّ الحواف"""
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
    """نص عربي مشكَّل (raqm) → RGBA numpy، مع ظل ناعم"""
    l, t, r, b = fnt.getbbox(txt, direction="rtl" if is_ar(txt) else "ltr")
    w, h = r - l + pad*2, b - t + pad*2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad - l, pad - t + 4), txt, font=fnt, fill=(0, 0, 0, 120))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(im).text((pad - l, pad - t), txt, font=fnt, fill=color + (255,))
    return np.array(im)

def is_ar(s): return any("؀" <= c <= "ۿ" for c in s)

# ── الكشيدة ────────────────────────────────────────────────────────────────────
NOJOIN = set("اأإآدذرزوؤةىءـ")          # حروف ما تتصل باللي بعدها
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
        if fnt.getlength(s) > target: break
        best = s
    return best

# ── الهوك ─────────────────────────────────────────────────────────────────────
HOOK = P.get("hook") or {}
HW = HOOK.get("words", [])
hook_imgs = []
if HW:
    n = len(HW); size = int(HOOK.get("size", 150 if n <= 4 else 128))
    hf = font(TH.get("hook_font", "Tajawal-Black.ttf"), size)
    raw = [w["w"] for w in HW]
    col = HOOK.get("width", 0.40) * W_
    colw = min(col, max(hf.getlength(w) for w in raw) * 1.15) if not HOOK.get("width") else col
    for w in raw:
        s = stretch(w, hf, colw) if HOOK.get("kashida", True) else w
        hook_imgs.append(text_rgba(s, hf, INK, shadow=True, pad=30))
    HOOK_LH = int(size * 1.22)
    HOOK_TOP = int(HOOK.get("top", 0.36) * H_)
    HOOK_CX = int((0.29 if HOOK.get("side", "left") == "left" else 0.71) * W_)
    if isinstance(HOOK.get("cx"), (int, float)): HOOK_CX = int(HOOK["cx"] * W_)
HOOK_END = float(HOOK.get("e", 0)) if HW else 0.0

def draw_hook(fr, t):
    if not HW or t >= HOOK_END: return
    for i, (w, im) in enumerate(zip(HW, hook_imgs)):
        p = (t - w["s"]) / 0.18
        if p <= 0: continue
        dy = int((1 - ease_out(p)) * 26)
        cy = HOOK_TOP + i * HOOK_LH + dy
        # محاذاة يمين (RTL) على عمود ثابت — الكشيدة تخلّي الأسطر بنفس العرض تقريباً
        x = HOOK_CX + int(colw / 2) - im.shape[1] + 30
        blend(fr, im, x, cy - im.shape[0] // 2, ease_out(p))

# ── الكابشن ───────────────────────────────────────────────────────────────────
CAPS = P.get("captions", [])
CF = font(TH.get("font", "Tajawal-Bold.ttf"), int(TH.get("caption_size", 66)))
CAP_Y = float(TH.get("caption_y", 0.555))
_cap_cache = {}
def cap_img(txt):
    if txt not in _cap_cache:
        ws = txt.split()
        if CF.getlength(txt) > 0.78 * W_ and len(ws) > 1:      # سطرين لو طويل
            k = len(ws) // 2
            a, b = text_rgba(" ".join(ws[:k]), CF, INK), text_rgba(" ".join(ws[k:]), CF, INK)
            w = max(a.shape[1], b.shape[1]); gap = -40
            im = np.zeros((a.shape[0] + b.shape[0] + gap, w, 4), np.uint8)
            for j, (src, yy) in enumerate(((a, 0), (b, a.shape[0] + gap))):
                xx = (w - src.shape[1]) // 2
                reg = im[yy:yy+src.shape[0], xx:xx+src.shape[1]]
                np.maximum(reg, src, out=reg)
            _cap_cache[txt] = im
        else:
            _cap_cache[txt] = text_rgba(txt, CF, INK)
    return _cap_cache[txt]

def draw_caption(fr, t):
    if t < HOOK_END: return
    for c in CAPS:
        if c["s"] - 0.02 <= t < c["e"] + c.get("hold", 0.12):
            nxt = [d["s"] for d in CAPS if d["s"] > c["s"]]
            if nxt and t >= nxt[0] - 0.02: continue
            im = cap_img(c["text"]); p = (t - c["s"]) / 0.12
            im2 = scaled(im, 0.92 + 0.08 * ease_out(p))
            blend(fr, im2, (W_ - im2.shape[1]) // 2, int(CAP_Y * H_) - im2.shape[0] // 2, ease_out(p))
            return

# ── البي-رول ──────────────────────────────────────────────────────────────────
POS = {"tl": (0.28, 0.235), "tr": (0.72, 0.235), "tc": (0.50, 0.225),
       "ml": (0.27, 0.42), "mr": (0.73, 0.42)}
VIDEXT = (".mp4", ".mov", ".m4v", ".webm")

class Card:
    def __init__(self, d):
        self.d = d; self.s, self.e = float(d["s"]), float(d["e"])
        self.src = os.path.join(WORK, d["src"]); self.vid = self.src.lower().endswith(VIDEXT)
        pos = d.get("pos", "tl")
        self.cx, self.cy = POS[pos] if isinstance(pos, str) else pos
        self.cw = int(d.get("w", 0.75 if pos == "tc" else 0.44) * W_)
        self.r = int(d.get("radius", 14)); self.cap = None
        if self.vid:
            self.cap = cv2.VideoCapture(self.src); self.vfps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            ok, f0 = self.cap.read(); self.last = (0, f0); self.size(f0.shape[1], f0.shape[0])
        else:
            im = Image.open(self.src).convert("RGB"); self.size(*im.size)
            self.static = self.frame_rgba(np.array(im)[..., ::-1])

    def size(self, w, h):
        self.ch = int(self.cw * h / w)
        mh = int(self.d.get("max_h", 0.36) * H_)
        if self.ch > mh: self.ch = mh; self.cw = int(mh * w / h)
        self.x = int(self.cx * W_ - self.cw / 2); self.y = int(self.cy * H_ - self.ch / 2)

    def frame_rgba(self, bgr):
        """صورة → كرت بزوايا دائرية + ظل (RGBA مع هامش 40)"""
        m = 40; img = cv2.resize(bgr, (self.cw, self.ch), interpolation=cv2.INTER_AREA)[..., ::-1]
        out = np.zeros((self.ch + 2*m, self.cw + 2*m, 4), np.uint8)
        mask = np.zeros((self.ch, self.cw), np.uint8)
        cv2.rectangle(mask, (self.r, 0), (self.cw - self.r, self.ch), 255, -1)
        cv2.rectangle(mask, (0, self.r), (self.cw, self.ch - self.r), 255, -1)
        for cx, cy in ((self.r, self.r), (self.cw-self.r-1, self.r), (self.r, self.ch-self.r-1), (self.cw-self.r-1, self.ch-self.r-1)):
            cv2.circle(mask, (cx, cy), self.r, 255, -1, cv2.LINE_AA)
        sh = np.zeros(out.shape[:2], np.uint8); sh[m+10:m+10+self.ch, m:m+self.cw] = mask
        out[..., 3] = (cv2.GaussianBlur(sh, (0, 0), 14) * 0.35).astype(np.uint8)
        reg = out[m:m+self.ch, m:m+self.cw]
        a = mask[..., None] / 255.0
        reg[..., :3] = (img * a).astype(np.uint8)
        reg[..., 3] = np.maximum(reg[..., 3], mask)
        return out

    def get(self, t):
        if not self.vid: return self.static
        k = int((t - self.s) * self.vfps) % max(1, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1)
        if k != self.last[0]:
            if k != self.last[0] + 1: self.cap.set(cv2.CAP_PROP_POS_FRAMES, k)
            ok, f = self.cap.read()
            if ok: self.last = (k, f)
        return self.frame_rgba(self.last[1])

    def alpha_scale(self, t):
        pi, po = (t - self.s) / 0.28, (self.e - t) / 0.2
        if pi < 1: return ease_out(pi), 0.86 + 0.14 * ease_back(pi)
        if po < 1: return ease_out(po), 0.96 + 0.04 * po
        return 1.0, 1.0

    def draw(self, fr, t):
        a, s = self.alpha_scale(t)
        im = scaled(self.get(t), s)
        blend(fr, im, int(self.cx * W_ - im.shape[1] / 2), int(self.cy * H_ - im.shape[0] / 2), a)
        if self.d.get("accent") in ACCENTS: ACCENTS[self.d["accent"]](fr, self, t, a)

def acc_arrow(fr, c, t, a):
    """سهم نمو يُرسم من تحت-يسار الكرت لفوق-يمينه (لتقارير/أرقام/نمو)"""
    p = ease_out((t - c.s - 0.15) / 0.75)
    if p <= 0: return
    bx, by, bw, bh = c.x, c.y, c.cw, c.ch
    pts = np.array([(-0.08, 1.05), (0.30, 0.62), (0.48, 0.78), (1.08, -0.04)]) * (bw, bh) + (bx, by)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1); L = seg.sum() * p
    path, acc = [pts[0]], 0.0
    for i, l in enumerate(seg):
        if acc + l >= L: path.append(pts[i] + (pts[i+1] - pts[i]) * (L - acc) / l); break
        path.append(pts[i+1]); acc += l
    path = np.array(path)
    th = int(bw * 0.055); ov = np.zeros((H_, W_, 4), np.uint8)
    cv2.polylines(ov, [path.astype(np.int32)], False, BRAND + (255,), th, cv2.LINE_AA)
    d = path[-1] - path[-2]; d = d / (np.linalg.norm(d) + 1e-6); nrm = np.array([-d[1], d[0]])
    tip = path[-1] + d * th * 1.2
    tri = np.array([tip, path[-1] - d * th * 0.6 + nrm * th * 1.5, path[-1] - d * th * 0.6 - nrm * th * 1.5])
    cv2.fillPoly(ov, [tri.astype(np.int32)], BRAND + (255,), cv2.LINE_AA)
    blend(fr, ov, 0, 0, a)

def acc_circle(fr, c, t, a):
    """دائرة تتلف حول نقطة بالكرت (focus: [x,y] نسبي) — لتأشير على تفصيلة"""
    p = ease_out((t - c.s - 0.2) / 0.6)
    if p <= 0: return
    fx, fy = c.d.get("focus", [0.5, 0.5]); r = int(c.cw * c.d.get("focus_r", 0.22))
    ov = np.zeros((H_, W_, 4), np.uint8)
    cv2.ellipse(ov, (int(c.x + fx*c.cw), int(c.y + fy*c.ch)), (r, int(r*0.7)), -20, 0, 360*p, ACC + (255,),
                max(6, r // 9), cv2.LINE_AA)
    blend(fr, ov, 0, 0, a)

ACCENTS = {"arrow": acc_arrow, "circle": acc_circle}
CARDS = [Card(d) for d in P.get("broll", [])]

# ── قصّ الشخص ─────────────────────────────────────────────────────────────────
_seg = None; _prev = None
def person_mask(rgb_u8):
    global _seg, _prev
    if _seg is None:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
        _seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=os.path.join(MODELS, "selfie_segmenter.tflite")),
            output_confidence_masks=True))
        _seg._mp = mp
    mp = _seg._mp
    r = _seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb_u8)))
    m = r.confidence_masks[0].numpy_view().astype(np.float32)
    m = cv2.resize(m, (W_, H_), interpolation=cv2.INTER_LINEAR)
    m = np.clip((m - 0.35) / 0.35, 0, 1)
    m = cv2.GaussianBlur(m, (0, 0), 2.2)
    if _prev is not None and _prev.shape == m.shape: m = 0.65 * m + 0.35 * _prev
    _prev = m
    return m[..., None]

# ── اللقطات (زوم) ─────────────────────────────────────────────────────────────
SHOTS = P.get("shots", [])
def shot_at(t):
    for s in SHOTS:
        if s["s"] <= t < s["e"]: return s
    return {"zoom": 1.0, "cy": 0.3}

def zoom(frame, t):
    s = shot_at(t); z = float(s.get("zoom", 1.0))
    z *= 1 + float(s.get("push", 0)) * clamp((t - s.get("s", 0)) / max(0.1, s.get("e", 1) - s.get("s", 0)))
    if z <= 1.001: return frame
    cw, ch = int(W_ / z), int(H_ / z)
    x = int((W_ - cw) * s.get("cx", 0.5)); y = int((H_ - ch) * s.get("cy", 0.3))
    return cv2.resize(frame[y:y+ch, x:x+cw], (W_, H_), interpolation=cv2.INTER_CUBIC)

# ── الإوترو ───────────────────────────────────────────────────────────────────
_logo = None
def outro_frame(t):
    """t من 0 لين OUT_DUR. شعار يلف ويكبر بتوهّج، بعدين يصغر ويطلع الاسم بمسح"""
    global _logo
    bg = hexrgb(OUT["bg"]) if OUT.get("bg") else BRAND
    fr = np.zeros((H_, W_, 3), np.float32); fr[:] = bg
    lp = os.path.join(WORK, OUT.get("logo") or "_")
    name = OUT.get("name", "")
    if _logo is None and os.path.exists(lp):
        im = Image.open(lp).convert("RGBA"); s = 0.42 * W_ / max(im.size)
        _logo = np.array(im.resize((int(im.width*s), int(im.height*s)), Image.LANCZOS))
    has_name = bool(name)
    move = ease_out((t - 0.95) / 0.5) if has_name else 0.0
    if _logo is not None:
        p = (t - 0.05) / 0.6
        if p > 0:
            sc = (0.25 + 0.75 * ease_back(p, 2.0)) * (1 - 0.45 * move)
            ang = (1 - ease_out(p)) * -140
            h, w = _logo.shape[:2]
            M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, sc)
            big = int(max(w, h) * 1.5); M[0, 2] += (big - w) / 2; M[1, 2] += (big - h) / 2
            rot = cv2.warpAffine(_logo, M, (big, big), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
            cx, cy = W_ // 2, int(H_ * (0.5 - 0.07 * move))
            glow = clamp(1 - (t - 0.35) / 0.9) * 0.9
            if glow > 0.01:
                g = rot.copy(); g[..., :3] = 255
                g[..., 3] = cv2.GaussianBlur(g[..., 3], (0, 0), 28)
                blend(fr, g, cx - big // 2, cy - big // 2, glow)
            blend(fr, rot, cx - big // 2, cy - big // 2, ease_out(p * 2))
    if has_name:
        nf = font(OUT.get("font", TH.get("font", "Tajawal-Bold.ttf")), int(OUT.get("size", 120)))
        im = text_rgba(name, nf, ACC, shadow=False, pad=10)
        p = ease_out((t - (1.05 if _logo is not None else 0.2)) / 0.6)
        if p > 0:
            w = im.shape[1]; vis = int(w * p); im = im.copy()
            if is_ar(name): im[:, :w - vis, 3] = 0           # مسح من اليمين للعربي
            else: im[:, vis:, 3] = 0                         # ومن اليسار للإنجليزي
            y = int(H_ * (0.5 + (0.06 if _logo is not None else 0)))
            blend(fr, im, (W_ - w) // 2, y - im.shape[0] // 2, 1.0)
    f = clamp((OUT_DUR - t) / 0.35)
    return fr * f

# ── تركيب فريم ────────────────────────────────────────────────────────────────
def compose(frame_rgb, t):
    if t >= TOTAL: return outro_frame(t - TOTAL)
    base = zoom(frame_rgb, t)
    fr = base.astype(np.float32)
    act = [c for c in CARDS if c.s <= t < c.e]
    behind = [c for c in act if c.d.get("behind", True)]
    if behind:
        for c in behind: c.draw(fr, t)
        m = person_mask(base)
        fr = base.astype(np.float32) * m + fr * (1 - m)
    for c in act:
        if not c.d.get("behind", True): c.draw(fr, t)
    draw_hook(fr, t); draw_caption(fr, t)
    return fr

def frames_at(times):
    """فريمات محددة من cut.mp4 (للمعاينة)"""
    out = {}
    for t in times:
        if t >= TOTAL: out[t] = np.zeros((H_, W_, 3), np.uint8); continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", os.path.join(WORK, "cut.mp4"),
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        out[t] = np.frombuffer(raw[:W_*H_*3], np.uint8).reshape(H_, W_, 3)
    return out

if "--preview" in ARGS:
    ts = [float(x) for x in ARGS[ARGS.index("--preview") + 1:]]
    fs = frames_at(ts); thumbs = []
    for t in ts:
        _prev = None
        im = np.clip(compose(fs[t], t), 0, 255).astype(np.uint8)
        th = cv2.resize(im, (360, 640), interpolation=cv2.INTER_AREA)
        cv2.putText(th, f"{t:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2, cv2.LINE_AA)
        thumbs.append(th)
    cols = min(6, len(thumbs)); rows = -(-len(thumbs) // cols)
    while len(thumbs) < rows * cols: thumbs.append(np.zeros_like(thumbs[0]))
    sheet = np.vstack([np.hstack(thumbs[r*cols:(r+1)*cols]) for r in range(rows)])
    cv2.imwrite(os.path.join(WORK, "sheet.jpg"), sheet[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"✅ sheet.jpg — {len(ts)} لقطة"); sys.exit(0)

# ── رندر كامل / نافذة ─────────────────────────────────────────────────────────
t0, t1 = 0.0, TOTAL + OUT_DUR
name = "reel.mp4"
if "--range" in ARGS:
    i = ARGS.index("--range"); t0, t1 = float(ARGS[i+1]), float(ARGS[i+2]); name = "range.mp4"
dst = os.path.join(WORK, name)
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", os.path.join(WORK, "cut.mp4"),
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W_}x{H_}",
                        "-r", str(FPS), "-i", "-", "-ss", f"{t0:.3f}", "-i", os.path.join(WORK, "cut.mp4"),
                        "-map", "0:v", "-map", "1:a?", "-af", f"apad=whole_dur={t1-t0:.3f}",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                        "-c:a", "aac", "-b:a", "192k", "-t", f"{t1-t0:.3f}", "-movflags", "+faststart",
                        "-y", dst], stdin=subprocess.PIPE)
N = int(round((t1 - t0) * FPS)); blank = np.zeros((H_, W_, 3), np.uint8); last = blank
for k in range(N):
    t = t0 + k / FPS
    if t < TOTAL:
        raw = dec.stdout.read(W_ * H_ * 3)
        if len(raw) == W_ * H_ * 3: last = np.frombuffer(raw, np.uint8).reshape(H_, W_, 3)
    enc.stdin.write(np.clip(compose(last, t), 0, 255).astype(np.uint8).tobytes())
    if k % 60 == 0: print(f"\r{t:6.1f}/{t1:.1f}s", end="", flush=True)
enc.stdin.close(); enc.wait(); dec.kill()
print(f"\n✅ {name} — {t1-t0:.2f}s ({N} فريم)")
