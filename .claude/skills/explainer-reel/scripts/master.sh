#!/usr/bin/env bash
# معايرة الصوت ‎-14 LUFS + (اختياري) ملف صوتي بالخلفية ينخفض تلقائياً وقت الكلام.
#   bash master.sh <work>        → <work>/reel-master.mp4
# حط <work>/bg-audio.mp3 (أو .m4a/.wav) لو تبي خلفية صوتية. BG_DB=-20 يضبط علوها.
set -euo pipefail
W="$(cd "$1" && pwd)"; IN="$W/reel.mp4"; OUT="$W/reel-master.mp4"
BG="$(ls "$W"/bg-audio.* 2>/dev/null | head -1 || true)"; BG_DB="${BG_DB:--20}"
if [ -n "$BG" ]; then
  ffmpeg -v error -i "$IN" -stream_loop -1 -i "$BG" -filter_complex \
   "[1:a]volume=${BG_DB}dB,afade=t=in:d=0.6[bg];[0:a]asplit[v][sc];\
    [bg][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck];\
    [v][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]" \
   -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart -y "$OUT"
else
  ffmpeg -v error -i "$IN" -af "loudnorm=I=-14:TP=-1.5:LRA=11" -map 0:v -map 0:a \
   -c:v copy -c:a aac -b:a 192k -movflags +faststart -y "$OUT"
fi
ffmpeg -v info -i "$OUT" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I:|Peak:)" | tail -2
echo "✅ $(basename "$OUT") — $(du -h "$OUT" | cut -f1)"
