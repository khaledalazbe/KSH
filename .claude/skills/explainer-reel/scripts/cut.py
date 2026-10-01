# -*- coding: utf-8 -*-
"""قص السكتات حسب cut.json → cut.mp4 عمودي 1080×1920 @30 (بلا زوم — الزوم بالرندر).
python3 cut.py <work>"""
import json, subprocess, sys, os
W = os.path.abspath(sys.argv[1]); SRC = os.path.join(W, "src.mp4")
if not os.path.exists(SRC):
    SRC = next(os.path.join(W, f) for f in os.listdir(W) if f.startswith("src."))
keep = json.load(open(os.path.join(W, "cut.json")))["keep"]
fc, v, a = [], [], []
for i, (s, e) in enumerate(keep):
    # cover: يملأ 9:16 ويقص الزايد من الوسط (فيديو أفقي ينقص من الجنبين)
    fc.append(f"[0:v]trim=start={s:.4f}:end={e:.4f},setpts=PTS-STARTPTS,"
              f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop=1080:1920,setsar=1[v{i}]")
    fc.append(f"[0:a]atrim=start={s:.4f}:end={e:.4f},asetpts=PTS-STARTPTS,"
              f"afade=t=in:d=0.02,areverse,afade=t=in:d=0.03,areverse[a{i}]")
    v.append(f"[v{i}]"); a.append(f"[a{i}]")
fc.append("".join(v) + f"concat=n={len(keep)}:v=1:a=0,fps=30,"
          "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,format=yuv420p[vo]")
fc.append("".join(a) + f"concat=n={len(keep)}:v=0:a=1,dynaudnorm=f=200:g=5:p=0.9[ao]")
r = subprocess.call(["ffmpeg", "-v", "error", "-i", SRC, "-filter_complex", ";".join(fc),
                     "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "fast", "-crf", "14",
                     "-c:a", "aac", "-b:a", "192k", "-y", os.path.join(W, "cut.mp4")])
if r == 0:
    print(f"✅ cut.mp4 — {sum(e-s for s, e in keep):.2f}s من {len(keep)} مقطع")
sys.exit(r)
