# -*- coding: utf-8 -*-
"""محاذاة الكلمات على الصوت: يوزّع كلمات كل مقطع على منحنى الطاقة ببرمجة ديناميكية.
python3 align.py <work>   → يقرأ a.raw.json (نص وِسبر بعد تصحيحك) ويكتب a.json بتوقيت لكل كلمة
مقسوماً لكروت كابشن ٢-٣ كلمات. آمن تعيد تشغيله بعد أي تصحيح للنص."""
import json, os, sys, wave
import numpy as np

W = os.path.abspath(sys.argv[1])
HOP = 0.020           # 20ms
WIN = 0.040
MAXCARD = 3           # أقصى عدد كلمات بكرت الكابشن (الستايل: كابشن قصير)
LAM, MU = 1.0, 0.55   # وزن مطابقة المدّة · وزن تفضيل الحدود الهادئة

with wave.open(os.path.join(W, "a.wav")) as f:
    sr = f.getframerate()
    pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)/32768.0

AR_LONG = set("اويأإآؤئى")
def weight(w):
    ltr = [c for c in w if c.isalpha()]
    n = max(2, len(ltr))
    n += sum(0.45 for c in ltr if c in AR_LONG)
    return n + 1.4                      # كلفة نطق ثابتة لكل كلمة

def envelope(a, b):
    """منحنى طاقة مقطع [a,b] بديسيبل مُطبَّع 0..1 (1 = عالي)"""
    s0, s1 = int(a*sr), int(b*sr)
    seg = pcm[s0:s1]
    hop, win = int(HOP*sr), int(WIN*sr)
    n = max(1, (len(seg)-win)//hop + 1)
    e = np.empty(n)
    for i in range(n):
        fr = seg[i*hop:i*hop+win]
        e[i] = np.sqrt(np.mean(fr*fr)) if len(fr) else 1e-6
    db = 20*np.log10(np.maximum(e, 1e-6))
    lo, hi = np.percentile(db, 5), np.percentile(db, 97)
    if hi-lo < 1e-3: return np.ones(n)*0.5, n
    return np.clip((db-lo)/(hi-lo), 0, 1), n

def align(a, b, words, onset, end):
    """يرجّع [(s,e)] لكل كلمة بالثواني المطلقة.
    حدود الكلام الخارجية من الـVAD نفسه (لا من الطاقة) — فأول كلمة تبدأ وقت
    ما يبدأ الصوت بالضبط، وحشوة الأمان ما تُنسب لها."""
    env, n = envelope(a, b)
    f0 = int(round((onset - a)/HOP)); f1 = int(round((end - a)/HOP))
    f0 = max(0, min(f0, n-2)); f1 = max(f0+1, min(f1, n))
    span = f1-f0
    k = len(words)
    if k == 1: return [(a+f0*HOP, a+f1*HOP)]
    wts = np.array([weight(w) for w in words]); wts = wts/wts.sum()
    exp = wts*span                                   # المدّة المتوقعة بالفريمات
    MIN, MAX = 4, int(2.6/HOP)                       # 80ms .. 2.6s لكل كلمة
    INF = 1e18
    dp   = np.full((k+1, span+1), INF)
    back = np.zeros((k+1, span+1), dtype=np.int32)
    dp[0, 0] = 0.0
    benv = env[f0:f1+1] if f1+1 <= n else np.append(env[f0:f1], env[f1-1])
    if len(benv) < span+1: benv = np.append(benv, [benv[-1]]*(span+1-len(benv)))
    for i in range(k):
        e_i = max(2.0, exp[i])
        lo_d, hi_d = MIN, min(MAX, span)
        for g in range(1, span+1):
            f_lo, f_hi = max(0, g-hi_d), g-lo_d
            if f_hi < f_lo: continue
            prev = dp[i, f_lo:f_hi+1]
            if not np.isfinite(prev).any(): continue
            d = g - np.arange(f_lo, f_hi+1)
            cost = prev + LAM*((d-e_i)/e_i)**2
            if i < k-1: cost = cost + MU*benv[g]      # آخر كلمة تنتهي بنهاية المقطع
            j = int(np.argmin(cost))
            if cost[j] < dp[i+1, g]: dp[i+1, g] = cost[j]; back[i+1, g] = f_lo+j
    # المسار
    bnd = [span]; cur = span
    for i in range(k, 0, -1):
        cur = int(back[i, cur]); bnd.append(cur)
    bnd.reverse()
    return [(a+(f0+bnd[i])*HOP, a+(f0+bnd[i+1])*HOP) for i in range(k)]

CUT = json.load(open(os.path.join(W, "cut.json")))
KEEP, ONSET, END = CUT["keep"], CUT["onsets"], CUT["ends"]
tr = json.load(open(os.path.join(W, "a.raw.json")))
out = []
for seg in tr["segments"]:
    ws = [w["word"] for w in seg["words"]]
    # دمج حروف العطف المفردة مع الكلمة اللي بعدها (و / ف)
    merged = []
    for w in ws:
        if merged and len(merged[-1]) == 1 and merged[-1] in "وف": merged[-1] += w
        else: merged.append(w)
    ws = merged
    si = min(range(len(KEEP)), key=lambda i: abs(KEEP[i][0]-seg["start"]))
    sp = align(seg["start"], seg["end"], ws, ONSET[si], END[si])
    wl = [{"word": w, "start": round(s, 3), "end": round(e, 3)} for w, (s, e) in zip(ws, sp)]
    # قصّ الكروت الطويلة عند أكبر سكتة داخلية
    def split(lst):
        """يقسم لكروت متوازنة (٢-٤ كلمات) عند أكبر السكتات — بلا كروت كلمة وحدة"""
        n = len(lst)
        if n <= MAXCARD: return [lst]
        p = -(-n // MAXCARD)                       # عدد الكروت
        while n / p < 2 and p > 1: p -= 1          # لا كرت أقل من كلمتين
        gaps = [lst[i+1]["start"]-lst[i]["end"] for i in range(n-1)]
        cuts = []
        for j in range(1, p):
            ideal = round(j*n/p)
            win = [i for i in range(max(1, ideal-2), min(n-1, ideal+2)+1)
                   if all(abs(i-c) >= 2 for c in cuts)]
            if not win: continue
            cuts.append(max(win, key=lambda i: (gaps[i-1], -abs(i-ideal))))
        cuts = sorted(set(cuts))
        parts, prev = [], 0
        for c in cuts + [n]:
            if c-prev >= 1: parts.append(lst[prev:c]); prev = c
        # أي كرت كلمة وحدة يندمج مع جاره
        i = 0
        while i < len(parts):
            if len(parts[i]) < 2 and len(parts) > 1:
                if i == 0: parts[1] = parts[0]+parts[1]; parts.pop(0)
                else: parts[i-1] = parts[i-1]+parts[i]; parts.pop(i)
            else: i += 1
        return parts
    # علامات الترقيم (؟ . ! ،) = حد كرت إجباري — الكرت ما يعبر نهاية جملة
    groups, cur = [], []
    for x in wl:
        cur.append(x)
        if x["word"][-1] in "؟?.!،,:": groups.append(cur); cur = []
    if cur: groups.append(cur)
    for part in [p for g in groups for p in split(g)]:
        out.append({"id": len(out), "start": part[0]["start"], "end": part[-1]["end"],
                    "text": " ".join(x["word"] for x in part), "words": part})

json.dump({"text": " ".join(s["text"] for s in out), "segments": out, "language": "ar"},
          open(os.path.join(W, "a.json"), "w"), ensure_ascii=False, indent=1)
print(f"✅ {len(out)} كرت، {sum(len(s['words']) for s in out)} كلمة")
for s in out:
    print(f"[{s['id']:2}] {s['start']:6.2f}-{s['end']:6.2f}  " +
          "  ".join(f"{w['word']}({w['start']:.2f})" for w in s["words"]))
