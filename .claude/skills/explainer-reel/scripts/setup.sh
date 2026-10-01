#!/usr/bin/env bash
# يفحص الأدوات والموديلات. بلا وسيط = فحص فقط · --install = ينزّل الناقص.
#   bash setup.sh            → "كل شي جاهز" أو قائمة الناقص (رمز خروج 1)
#   bash setup.sh --install  → pip + الموديلات (~600 ميقا مرة وحدة)
set -u
M="${REEL_MODELS:-$HOME/.cache/explainer-reel/models}"
WH="${REEL_WHISPER:-turbo}"          # turbo (افتراضي، 560MB) · large-v3 (1GB) · small (640MB)
REL=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models
SEG=https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite
missing=()

command -v ffmpeg  >/dev/null || missing+=("ffmpeg")
command -v ffprobe >/dev/null || missing+=("ffprobe")
python3 - <<'EOF' 2>/dev/null || missing+=("python-libs")
import numpy, cv2, mediapipe, sherpa_onnx
from PIL import features
assert features.check("raqm"), "raqm"
EOF
[ -f "$M/silero_vad.onnx" ]            || missing+=("silero_vad")
[ -f "$M/selfie_segmenter.tflite" ]    || missing+=("selfie_segmenter")
[ -d "$M/sherpa-onnx-whisper-$WH" ]    || missing+=("whisper-$WH")

if [ ${#missing[@]} -eq 0 ]; then echo "✅ كل شي جاهز ($M)"; exit 0; fi
if [ "${1:-}" != "--install" ]; then echo "ناقص: ${missing[*]}"; exit 1; fi

mkdir -p "$M"
for x in "${missing[@]}"; do case "$x" in
  ffmpeg|ffprobe) (apt-get install -y ffmpeg >/dev/null 2>&1 || brew install ffmpeg) ;;
  python-libs) pip install -q pillow numpy opencv-python-headless mediapipe sherpa-onnx ;;
  silero_vad) curl -fsSL -o "$M/silero_vad.onnx" "$REL/silero_vad.onnx" ;;
  selfie_segmenter) curl -fsSL -o "$M/selfie_segmenter.tflite" "$SEG" ;;
  whisper-*) echo "⬇️  whisper-$WH ..."; curl -fsSL "$REL/sherpa-onnx-whisper-$WH.tar.bz2" | tar xj -C "$M" ;;
esac; done
exec bash "$0"
