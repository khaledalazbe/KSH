# -*- coding: utf-8 -*-
"""تفريغ كل مقطع كلام (من cut.json) عبر whisper بصيغة ONNX.
python3 asr.py <work> [models] [turbo|large-v3|small]   → a.raw.json (صحّح النص فيه، ثم align.py)"""
import json, sys, os, wave
import numpy as np, sherpa_onnx

W = os.path.abspath(sys.argv[1])
M = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else
                    os.environ.get("REEL_MODELS", os.path.expanduser("~/.cache/explainer-reel/models")))
NAME = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("REEL_WHISPER", "turbo")
MD = os.path.join(M, f"sherpa-onnx-whisper-{NAME}")
fs = os.listdir(MD)
pick = lambda key: sorted([f for f in fs if key in f and f.endswith(".onnx")], key=lambda f: "int8" not in f)[0]
tok = [f for f in fs if f.endswith("tokens.txt")][0]
print("whisper:", NAME, "|", pick("encoder"), "|", pick("decoder"))

rec = sherpa_onnx.OfflineRecognizer.from_whisper(
    encoder=os.path.join(MD, pick("encoder")), decoder=os.path.join(MD, pick("decoder")),
    tokens=os.path.join(MD, tok), language="ar", task="transcribe",
    num_threads=os.cpu_count() or 4, tail_paddings=1000)

with wave.open(os.path.join(W, "a.wav")) as f:
    sr = f.getframerate()
    pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

keep = json.load(open(os.path.join(W, "cut.json")))["keep"]
segments = []
for i, (a, b) in enumerate(keep):
    st = rec.create_stream(); st.accept_waveform(sr, pcm[int(a*sr):int(b*sr)]); rec.decode_stream(st)
    words = st.result.text.split()
    if not words:
        print(f"[{i}] (فاضي) {a:.2f}-{b:.2f}"); continue
    # توقيت مبدئي متساوٍ — align.py يعيد توزيعه على منحنى الطاقة
    step = (b - a) / len(words)
    ws = [{"word": w, "start": a + j*step, "end": a + (j+1)*step} for j, w in enumerate(words)]
    segments.append({"id": len(segments), "start": a, "end": b, "text": " ".join(words), "words": ws})
    print(f"[{len(segments)-1}] {a:6.2f}-{b:6.2f}  {' '.join(words)}")

json.dump({"text": " ".join(s["text"] for s in segments), "segments": segments, "language": "ar"},
          open(os.path.join(W, "a.raw.json"), "w"), ensure_ascii=False, indent=1)
print(f"\n✅ {len(segments)} جملة → a.raw.json")
