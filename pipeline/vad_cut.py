# -*- coding: utf-8 -*-
"""خطة قص بالـVAD (أدق من عتبة الديسيبل مع ضجيج السيارة).  python3 vad_cut.py <workdir> <models>"""
import json, sys, os, wave
import numpy as np, sherpa_onnx

W = os.path.abspath(sys.argv[1]); M = os.path.abspath(sys.argv[2])
PAD, MERGE, MIND = 0.14, 0.22, 0.32

wav = os.path.join(W, "a.wav")
with wave.open(wav) as f:
    sr = f.getframerate(); n = f.getnframes()
    pcm = np.frombuffer(f.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
dur = n / sr
print(f"صوت: {dur:.2f}s @ {sr}Hz")

cfg = sherpa_onnx.VadModelConfig()
cfg.silero_vad.model = os.path.join(M, "silero_vad.onnx")
cfg.silero_vad.threshold = 0.42
cfg.silero_vad.min_silence_duration = 0.25
cfg.silero_vad.min_speech_duration = 0.12
cfg.silero_vad.max_speech_duration = 18.0
cfg.sample_rate = sr
vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)

WIN = cfg.silero_vad.window_size
segs = []
for i in range(0, len(pcm), WIN):
    vad.accept_waveform(pcm[i:i+WIN])
    while not vad.empty():
        s = vad.front.start / sr
        segs.append([s, s + len(vad.front.samples) / sr]); vad.pop()
vad.flush()
while not vad.empty():
    s = vad.front.start / sr
    segs.append([s, s + len(vad.front.samples) / sr]); vad.pop()

print(f"VAD: {len(segs)} مقطع كلام خام")
# نحفظ مع كل مقطع بداية/نهاية الكلام الحقيقية (قبل الحشوة) — المحاذاة تتثبّت عليها
keep = [[max(0.0, a - PAD), min(dur, b + PAD), a, b] for a, b in segs]
m = []
for s in keep:
    if m and s[0] - m[-1][1] < MERGE: m[-1][1] = s[1]; m[-1][3] = s[3]
    else: m.append(s)
m = [x for x in m if x[1] - x[0] >= MIND]
tot = sum(x[1] - x[0] for x in m)
json.dump({"keep": [[x[0], x[1]] for x in m],
           "onsets": [round(x[2], 3) for x in m],
           "ends":   [round(x[3], 3) for x in m],
           "total": tot, "src_dur": dur},
          open(os.path.join(W, "cut.json"), "w"), indent=1)
print(f"مقاطع={len(m)}  الباقي={tot:.2f}s  انشال={dur-tot:.2f}s ({(dur-tot)/dur*100:.0f}%)")
for x in m: print(f"  {x[0]:7.2f} -> {x[1]:7.2f}  (كلام {x[2]:6.2f}-{x[3]:6.2f})")
