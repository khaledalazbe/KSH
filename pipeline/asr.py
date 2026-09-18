# -*- coding: utf-8 -*-
"""تفريغ بتوقيت الكلمة عبر whisper-large-v3 (ONNX) على مقاطع الـVAD.
python3 asr.py <workdir> <models>   → يكتب a.json بصيغة وِسبر الرسمية"""
import json, sys, os, wave
import numpy as np, sherpa_onnx

W = os.path.abspath(sys.argv[1]); M = os.path.abspath(sys.argv[2])
MD = os.path.join(M, "sherpa-onnx-whisper-large-v3")
enc = [f for f in os.listdir(MD) if "encoder" in f and f.endswith(".onnx")]
dec = [f for f in os.listdir(MD) if "decoder" in f and f.endswith(".onnx")]
enc.sort(key=lambda f: ("int8" not in f)); dec.sort(key=lambda f: ("int8" not in f))
print("encoder:", enc[0], "| decoder:", dec[0])

rec = sherpa_onnx.OfflineRecognizer.from_whisper(
    encoder=os.path.join(MD, enc[0]), decoder=os.path.join(MD, dec[0]),
    tokens=os.path.join(MD, "large-v3-tokens.txt"),
    language="ar", task="transcribe", num_threads=4,
    enable_token_timestamps=True, tail_paddings=1000)

with wave.open(os.path.join(W, "a.wav")) as f:
    sr = f.getframerate()
    pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)/32768.0

keep = json.load(open(os.path.join(W, "cut.json")))["keep"]
segments = []
for i, (a, b) in enumerate(keep):
    chunk = pcm[int(a*sr):int(b*sr)]
    st = rec.create_stream(); st.accept_waveform(sr, chunk); rec.decode_stream(st)
    r = st.result
    toks = list(r.tokens); ts = list(r.timestamps)
    if not toks:
        print(f"[{i}] (فاضي) {a:.2f}-{b:.2f}"); continue
    if len(ts) < len(toks): ts = ts + [ts[-1] if ts else 0.0]*(len(toks)-len(ts))
    # دمج التوكنز لكلمات: التوكن اللي يبدأ بمسافة = بداية كلمة جديدة
    words = []
    for tk, t in zip(toks, ts):
        new = tk.startswith(" ") or not words
        w = tk.strip()
        if not w:
            continue
        if new: words.append({"word": w, "start": a+t, "end": a+t})
        else:
            words[-1]["word"] += w; words[-1]["end"] = a+t
    # نهاية كل كلمة = بداية اللي بعدها (وآخر كلمة تمتد لنهاية المقطع)
    for j in range(len(words)-1):
        words[j]["end"] = max(words[j]["start"]+0.08, words[j+1]["start"]-0.01)
    if words:
        words[-1]["end"] = max(words[-1]["start"]+0.15, min(b, words[-1]["start"]+0.6))
    txt = " ".join(x["word"] for x in words)
    segments.append({"id": len(segments), "start": a, "end": b, "text": txt, "words": words})
    print(f"[{len(segments)-1}] {a:6.2f}-{b:6.2f}  {txt}")

json.dump({"text": " ".join(s["text"] for s in segments), "segments": segments, "language": "ar"},
          open(os.path.join(W, "a.json"), "w"), ensure_ascii=False, indent=1)
print(f"\n✅ {len(segments)} جملة، {sum(len(s['words']) for s in segments)} كلمة → a.json")
