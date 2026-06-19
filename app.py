"""
CaptionShift Backend — v4
Changelog v4:
 - BUG FIX: stream_duration NameError in get_video_dimensions() when no video
   stream is found (variable now initialized to None before the loop).
 - NEW: Word-chunked caption mode (CapCut/Reels style)
   - Whisper now runs with word_timestamps=True
   - /transcribe returns both 'segments' (sentence-level) AND 'words' (word-level)
   - New helper: chunk_words_into_segments(words, chunk_size)
     Splits word-level timestamps into groups of N words (default 3) so each
     caption shows only 3-4 words at a time, perfectly synced to speech.
   - /generate accepts optional 'caption_mode' field:
       "sentence"  — original behaviour (full Whisper segments, auto-wrapped at 45 chars)
       "word"      — word-chunked mode; chunk size controlled by 'word_chunk_size' (1-5)
   - create_ass_file no longer word-wraps in sentence mode (wrapping still works
     but is now only a safety net); word mode produces pre-chunked, single-line segments.

Changelog v3:
 - NEW: Optional Title/POV text overlay, fully independent from captions
 - get_video_dimensions() returns duration (no extra ffprobe call)

Changelog v2:
 - Near-lossless video encoding (CRF 16, preset medium, audio stream copy)
 - 9 bundled custom fonts
 - Font size control: small / medium / large / xlarge
 - 7 elegant color themes
"""

import os
import uuid
import json
import subprocess
import shutil
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import whisper
import tempfile

app = Flask(__name__)
CORS(app, origins="*")

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'captionshift')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_SRC = os.path.join(APP_DIR, 'fonts')
FONTS_DST = os.path.join(UPLOAD_FOLDER, 'fonts')
if os.path.exists(FONTS_SRC):
    shutil.copytree(FONTS_SRC, FONTS_DST, dirs_exist_ok=True)
    print(f"Custom fonts ready: {FONTS_DST}")

print("Loading Whisper model... please wait...")
model = whisper.load_model("base")
print("Whisper model loaded! Ready.")


# ─── Helpers ────────────────────────────────────────────────────────────────

def format_time_ass(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


SIZE_FRACTIONS = {
    "small":  0.032,
    "medium": 0.045,
    "large":  0.060,
    "xlarge": 0.078,
}


def rgb_to_ass(hexcolor, alpha="00"):
    h = hexcolor.lstrip('#')
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()


STYLE_DEFS = {
    "clean_white":      dict(primary="#FFFFFF", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.09),
    "bold_yellow":      dict(primary="#FFD700", outline="#000000", border_style=1, bold=1, shadow=1, size_mult=1.05, outline_frac=0.10),
    "black_box":        dict(primary="#FFFFFF", outline="#000000", back="#000000", back_alpha="80", border_style=3, bold=1, shadow=0, size_mult=0.95, outline_frac=0.0, margin_lr=10),
    "neon_green":       dict(primary="#00FF66", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.09),
    "fire_red":         dict(primary="#FF2020", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.09),
    "sky_blue":         dict(primary="#38BDF8", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.09),
    "pink_pop":         dict(primary="#FF69B4", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.09),
    "outline_only":     dict(primary="#FFFFFF", outline="#FFFFFF", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.14),
    "gradient_gold":    dict(primary="#FFAA00", outline="#000000", border_style=1, bold=1, shadow=1, size_mult=1.05, outline_frac=0.10),
    "cyan_glow":        dict(primary="#00FFFF", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.12),
    "dark_subtitle":    dict(primary="#FFFFFF", outline="#000000", back="#000000", back_alpha="CC", border_style=3, bold=1, shadow=0, size_mult=0.92, outline_frac=0.0, margin_lr=20),
    "purple_haze":      dict(primary="#CC00FF", outline="#000000", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.12),
    "ivory_classic":    dict(primary="#FFFFF0", outline="#2B1D14", border_style=1, bold=0, shadow=0, size_mult=1.00, outline_frac=0.09),
    "rose_gold":        dict(primary="#F0C9C0", outline="#5A2E27", border_style=1, bold=0, shadow=0, size_mult=1.00, outline_frac=0.09),
    "ice_blue":         dict(primary="#CFEFFF", outline="#0E2A3D", border_style=1, bold=0, shadow=0, size_mult=1.00, outline_frac=0.09),
    "mint_glow":        dict(primary="#9CFFD0", outline="#003322", border_style=1, bold=0, shadow=1, size_mult=1.00, outline_frac=0.11),
    "sunset_coral":     dict(primary="#FF7E5F", outline="#3A0E04", border_style=1, bold=1, shadow=0, size_mult=1.00, outline_frac=0.10),
    "royal_purple_box": dict(primary="#FFFFFF", outline="#000000", back="#2D0A4E", back_alpha="90", border_style=3, bold=0, shadow=0, size_mult=0.95, outline_frac=0.0, margin_lr=14),
    "cinema_subtitle":  dict(primary="#F5F5F5", outline="#000000", back="#000000", back_alpha="90", border_style=3, bold=0, shadow=0, size_mult=0.90, outline_frac=0.0, margin_lr=24, spacing=2),
}


def get_ass_style(style, video_width, video_height, position, font="Arial", size_choice="medium", style_name="Default"):
    sdef = STYLE_DEFS.get(style, STYLE_DEFS["clean_white"])
    size_fraction = SIZE_FRACTIONS.get(size_choice, SIZE_FRACTIONS["medium"])
    font_size = max(12, round(video_height * size_fraction * sdef.get("size_mult", 1.0)))
    outline_w = round(font_size * sdef.get("outline_frac", 0.09))
    primary  = rgb_to_ass(sdef["primary"])
    outline_c = rgb_to_ass(sdef["outline"])
    back_c   = rgb_to_ass(sdef.get("back", "#000000"), sdef.get("back_alpha", "00"))
    bold         = sdef.get("bold", 1)
    shadow       = sdef.get("shadow", 0)
    border_style = sdef.get("border_style", 1)
    margin_lr    = sdef.get("margin_lr", 10)
    spacing      = sdef.get("spacing", 0)
    y_pct    = position.get('y', 85)
    margin_v = int((1 - y_pct / 100) * video_height)
    margin_v = max(0, min(margin_v, video_height))
    return (
        f"Style: {style_name},{font},{font_size},"
        f"{primary},{primary},{outline_c},{back_c},"
        f"{bold},0,0,0,100,100,{spacing},0,"
        f"{border_style},{outline_w},{shadow},2,{margin_lr},{margin_lr},{margin_v},0"
    )


def chunk_words_into_segments(words, chunk_size=3):
    """
    Convert a flat list of word-timestamp dicts into caption segments,
    each containing exactly `chunk_size` words (last chunk may be smaller).

    Each word dict must have: {'word': str, 'start': float, 'end': float}
    Returns list of {'start', 'end', 'text'} — same shape as Whisper segments.
    """
    segments = []
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        text  = ' '.join(w['word'].strip() for w in chunk)
        segments.append({
            'start': chunk[0]['start'],
            'end':   chunk[-1]['end'],
            'text':  text,
        })
    return segments


def create_ass_file(segments, style, position, video_width, video_height, output_path,
                    font="Arial", size_choice="medium",
                    title_text=None, title_style="clean_white", title_font="Arial",
                    title_size="medium", title_position=None, video_duration=None,
                    word_mode=False):
    style_line = get_ass_style(style, video_width, video_height, position, font, size_choice, style_name="Default")

    styles_block = [
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
    ]

    title_text = (title_text or "").strip()
    has_title  = bool(title_text)

    if has_title:
        title_pos       = title_position or {"x": 50, "y": 15}
        title_style_line = get_ass_style(
            title_style, video_width, video_height, title_pos,
            title_font, title_size, style_name="Title"
        )
        styles_block.append(title_style_line)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "ScaledBorderAndShadow: yes",
        "",
    ] + styles_block + [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if has_title:
        end_time   = format_time_ass(video_duration if video_duration else 9999)
        safe_title = title_text.replace("\n", "\\N")
        lines.append(f"Dialogue: 0,0:00:00.00,{end_time},Title,,0,0,0,,{safe_title}")

    for seg in segments:
        start = format_time_ass(seg['start'])
        end   = format_time_ass(seg['end'])
        text  = seg['text'].strip()

        # In sentence mode only: wrap long lines as a safety net
        if not word_mode and len(text) > 45:
            words = text.split()
            mid   = len(words) // 2
            text  = ' '.join(words[:mid]) + '\\N' + ' '.join(words[mid:])

        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def get_video_dimensions(video_path):
    """Returns (width, height, duration_seconds).
    BUG FIX v4: stream_duration initialised to None before the loop so it is
    always defined even when no video stream is present."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', video_path],
            capture_output=True, text=True
        )
        data   = json.loads(result.stdout)
        width, height = 1280, 720
        stream_duration = None                          # ← FIX: always initialised
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                width, height   = stream['width'], stream['height']
                stream_duration = stream.get('duration')
                break

        duration      = None
        fmt_duration  = data.get('format', {}).get('duration')
        if fmt_duration:
            duration = float(fmt_duration)
        elif stream_duration:
            duration = float(stream_duration)

        return width, height, duration
    except Exception as e:
        print(f"ffprobe error: {e}")
    return 1280, 720, None


def run_ffmpeg(video_path, safe_ass_name, safe_out_name, cwd):
    """Near-lossless FFmpeg encode. Tries audio copy first, falls back to AAC."""
    base_cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f"ass={safe_ass_name}:fontsdir=fonts",
        '-c:v', 'libx264',
        '-crf', '16',
        '-preset', 'medium',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
    ]

    cmd_copy = base_cmd + ['-c:a', 'copy', safe_out_name]
    print("Running FFmpeg (audio copy)...")
    result = subprocess.run(cmd_copy, capture_output=True, text=True, cwd=cwd)
    if result.returncode == 0:
        return result

    print("Audio copy failed, retrying with AAC re-encode...")
    print("FFmpeg stderr (copy attempt):", result.stderr[-500:])
    cmd_aac = base_cmd + ['-c:a', 'aac', '-b:a', '192k', safe_out_name]
    return subprocess.run(cmd_aac, capture_output=True, text=True, cwd=cwd)


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'version': 'v4'})


@app.route('/transcribe', methods=['POST'])
def transcribe():
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400

        video_file = request.files['video']
        job_id     = str(uuid.uuid4()).replace('-', '')[:12]
        video_ext  = os.path.splitext(video_file.filename)[1] or '.mp4'
        video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_in{video_ext}")
        video_file.save(video_path)

        width, height, duration = get_video_dimensions(video_path)

        print(f"Transcribing: {video_file.filename}")
        # word_timestamps=True gives us per-word start/end times
        result = model.transcribe(video_path, word_timestamps=True)

        # ── Sentence-level segments (for "sentence" caption mode) ──
        segments = []
        for seg in result['segments']:
            segments.append({
                'start': round(seg['start'], 2),
                'end':   round(seg['end'],   2),
                'text':  seg['text'].strip(),
            })

        # ── Word-level timestamps (for "word" caption mode) ──
        words = []
        for seg in result['segments']:
            for w in seg.get('words', []):
                words.append({
                    'word':  w['word'],
                    'start': round(w['start'], 3),
                    'end':   round(w['end'],   3),
                })

        try:
            os.remove(video_path)
        except Exception:
            pass

        return jsonify({
            'segments':       segments,
            'words':          words,          # NEW in v4
            'language':       result.get('language', 'en'),
            'video_width':    width,
            'video_height':   height,
            'video_duration': duration,
        })

    except Exception as e:
        print(f"Transcribe error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/generate', methods=['POST'])
def generate():
    video_path  = None
    ass_path    = None
    output_path = None

    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400

        video_file   = request.files['video']
        style        = request.form.get('style',        'clean_white')
        font         = request.form.get('font',         'Arial')
        size_choice  = request.form.get('font_size',    'medium')
        position     = json.loads(request.form.get('position',     '{"x":50,"y":85}'))

        # Caption mode — "sentence" (default, v1-v3 behaviour) or "word" (CapCut style)
        caption_mode    = request.form.get('caption_mode',    'sentence')
        word_chunk_size = int(request.form.get('word_chunk_size', 3))
        word_chunk_size = max(1, min(word_chunk_size, 5))   # clamp 1-5

        # Segments come from the frontend and reflect whatever the user has
        # edited in the caption editor — this is the source of truth and must
        # always win, regardless of caption_mode.
        segments = json.loads(request.form.get('segments', '[]'))

        # Fallback only: if no segments were supplied at all (e.g. an older
        # client), re-chunk from raw word timestamps. This path is never hit
        # when the frontend sends edited segments, so user edits are never
        # silently discarded.
        words_raw = request.form.get('words', '')
        if not segments and caption_mode == 'word' and words_raw:
            words    = json.loads(words_raw)
            segments = chunk_words_into_segments(words, chunk_size=word_chunk_size)

        # Title / POV overlay
        title_text     = request.form.get('title_text',     '').strip()
        title_style    = request.form.get('title_style',    'clean_white')
        title_font     = request.form.get('title_font',     'Arial')
        title_size     = request.form.get('title_size',     'medium')
        title_position = json.loads(request.form.get('title_position', '{"x":50,"y":15}'))

        job_id     = str(uuid.uuid4()).replace('-', '')[:12]
        video_ext  = os.path.splitext(video_file.filename)[1] or '.mp4'
        video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_in{video_ext}")
        video_file.save(video_path)

        width, height, duration = get_video_dimensions(video_path)

        ass_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.ass")
        create_ass_file(
            segments, style, position, width, height, ass_path, font, size_choice,
            title_text=title_text, title_style=title_style, title_font=title_font,
            title_size=title_size, title_position=title_position,
            video_duration=duration,
            word_mode=(caption_mode == 'word'),
        )

        output_path   = os.path.join(UPLOAD_FOLDER, f"{job_id}_out.mp4")
        safe_ass_name = f"{job_id}.ass"
        safe_out_name = f"{job_id}_out.mp4"

        mode_log  = f"word-chunk({word_chunk_size})" if caption_mode == 'word' else "sentence"
        title_log = f" | Title: '{title_text}' ({title_style}/{title_font}/{title_size})" if title_text else ""
        print(f"Mode: {mode_log} | Style: {style} | Font: {font} | Size: {size_choice} | Res: {width}x{height}{title_log}")

        result = run_ffmpeg(video_path, safe_ass_name, safe_out_name, UPLOAD_FOLDER)

        print(f"FFmpeg return code: {result.returncode}")
        if result.returncode != 0:
            print("FFmpeg stderr:", result.stderr[-2000:])
            return jsonify({'error': 'FFmpeg failed: ' + result.stderr[-500:]}), 500

        for f in [video_path, ass_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except Exception as ex:
                print(f"Cleanup warning: {ex}")

        try:
            out_size = os.path.getsize(output_path)
        except Exception:
            out_size = None
        print(f"Output ready: {output_path} ({out_size} bytes)")

        return jsonify({'job_id': job_id})

    except Exception as e:
        for f in [video_path, ass_path, output_path]:
            if f:
                try:
                    os.remove(f)
                except Exception:
                    pass
        print(f"Generate error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/download/<job_id>', methods=['GET'])
def download(job_id):
    if not job_id.isalnum():
        return jsonify({'error': 'Invalid job id'}), 400

    output_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_out.mp4")
    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found or already downloaded'}), 404

    def cleanup():
        try:
            os.remove(output_path)
            print(f"Cleaned up: {output_path}")
        except Exception as e:
            print(f"Cleanup error: {e}")

    response = send_file(
        output_path,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name='captioned_video.mp4'
    )

    @response.call_on_close
    def on_close():
        cleanup()

    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7860))
    app.run(host='0.0.0.0', port=port, debug=False)
