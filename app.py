import os
import uuid
import json
import subprocess
import shutil
from flask import Flask, request, jsonify, send_file, send_from_directory, after_this_request
from flask_cors import CORS
import whisper

app = Flask(__name__)
CORS(app, origins="*")

import tempfile
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'captionshift')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

print("Loading Whisper model... please wait...")
model = whisper.load_model("base")
print("Whisper model loaded! Ready.")


def format_time_ass(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def get_ass_style(style, video_width, video_height, position, font="Arial"):
    y_pct = position.get('y', 85)
    margin_v = int((1 - y_pct / 100) * video_height)
    margin_v = max(0, min(margin_v, video_height))

    # ASS colour format: &HAABBGGRR  (AA=alpha, 00=opaque)
    styles = {
        # Original 4
        "clean_white": f"Style: Default,{font},22,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
        "bold_yellow": f"Style: Default,{font},24,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,1,2,10,10,{margin_v},0",
        "black_box":   f"Style: Default,{font},20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,3,1,0,2,10,10,{margin_v},0",
        "neon_green":  f"Style: Default,{font},22,&H0000FF00,&H0000FF00,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
        # New 8
        "fire_red":    f"Style: Default,{font},22,&H000000FF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
        "sky_blue":    f"Style: Default,{font},22,&H00FFD700,&H00FFD700,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
        "pink_pop":    f"Style: Default,{font},22,&H00FF69B4,&H00FF69B4,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
        "outline_only":f"Style: Default,{font},22,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00FFFFFF,1,0,0,0,100,100,0,0,1,3,0,2,10,10,{margin_v},0",
        "gradient_gold":f"Style: Default,{font},24,&H0000AAFF,&H0000AAFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,1,2,10,10,{margin_v},0",
        "cyan_glow":   f"Style: Default,{font},22,&H00FFFF00,&H00FFFF00,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
        "dark_subtitle":f"Style: Default,{font},20,&H00FFFFFF,&H00FFFFFF,&H00000000,&HCC000000,1,0,0,0,100,100,0,0,3,0,0,2,20,20,{margin_v},0",
        "purple_haze": f"Style: Default,{font},22,&H00FF00CC,&H00FF00CC,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,{margin_v},0",
    }
    return styles.get(style, styles["clean_white"])


def create_ass_file(segments, style, position, video_width, video_height, output_path, font="Arial"):
    style_line = get_ass_style(style, video_width, video_height, position, font)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for seg in segments:
        start = format_time_ass(seg['start'])
        end = format_time_ass(seg['end'])
        text = seg['text'].strip()
        if len(text) > 45:
            words = text.split()
            mid = len(words) // 2
            text = ' '.join(words[:mid]) + '\\N' + ' '.join(words[mid:])
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def get_video_dimensions(video_path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', video_path],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                return stream['width'], stream['height']
    except Exception as e:
        print(f"ffprobe error: {e}")
    return 1280, 720


# ——— Serve frontend ———
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/transcribe', methods=['POST'])
def transcribe():
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400

        video_file = request.files['video']
        job_id = str(uuid.uuid4()).replace('-', '')[:12]
        video_ext = os.path.splitext(video_file.filename)[1] or '.mp4'
        video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_in{video_ext}")
        video_file.save(video_path)

        width, height = get_video_dimensions(video_path)

        print(f"Transcribing: {video_file.filename}")
        result = model.transcribe(video_path, word_timestamps=False)

        segments = []
        for seg in result['segments']:
            segments.append({
                'start': round(seg['start'], 2),
                'end': round(seg['end'], 2),
                'text': seg['text'].strip()
            })

        try:
            os.remove(video_path)
        except:
            pass

        return jsonify({
            'segments': segments,
            'language': result.get('language', 'en'),
            'video_width': width,
            'video_height': height
        })

    except Exception as e:
        print(f"Transcribe error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/generate', methods=['POST'])
def generate():
    video_path = None
    ass_path = None
    output_path = None

    try:
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400

        video_file = request.files['video']
        segments = json.loads(request.form.get('segments', '[]'))
        style = request.form.get('style', 'clean_white')
        font = request.form.get('font', 'Arial')
        position = json.loads(request.form.get('position', '{"x":50,"y":85}'))

        job_id = str(uuid.uuid4()).replace('-', '')[:12]
        video_ext = os.path.splitext(video_file.filename)[1] or '.mp4'
        video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_in{video_ext}")
        video_file.save(video_path)

        width, height = get_video_dimensions(video_path)

        ass_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.ass")
        create_ass_file(segments, style, position, width, height, ass_path, font)

        output_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_out.mp4")

        # FFmpeg's filtergraph parser chokes on colons (Windows drive letters)
        # and quotes in paths. Safest cross-platform fix: use a short filename
        # with no special characters and run FFmpeg with cwd=UPLOAD_FOLDER.
        safe_ass_name = f"{job_id}.ass"   # already in UPLOAD_FOLDER, no path chars needed
        safe_out_name = f"{job_id}_out.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f"ass={safe_ass_name}",
            '-c:v', 'libx264',
            '-crf', '23',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '128k',
            safe_out_name
        ]

        print(f"ASS filename: {safe_ass_name}")
        print("Running FFmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=UPLOAD_FOLDER)

        print(f"FFmpeg return code: {result.returncode}")
        if result.returncode != 0:
            print("FFmpeg stderr:", result.stderr[-2000:])
            return jsonify({'error': 'FFmpeg failed: ' + result.stderr[-500:]}), 500
        print(f"FFmpeg succeeded, output exists: {os.path.exists(output_path)}")
        if os.path.exists(output_path):
            print(f"Output file size on disk: {os.path.getsize(output_path)} bytes")

        print(f"Output file ready, reading into memory...")
        # Read into memory first so we can clean up files safely
        with open(output_path, 'rb') as fh:
            video_data = fh.read()

        print(f"Output file size: {len(video_data)} bytes")

        # Cleanup all temp files now that we have data in memory
        for f in [video_path, ass_path, output_path]:
            try:
                if f and os.path.exists(f):
                    os.remove(f)
            except Exception as ex:
                print(f"Cleanup warning: {ex}")

        from flask import Response
        return Response(
            video_data,
            mimetype='video/mp4',
            headers={
                'Content-Disposition': 'attachment; filename="captioned_video.mp4"',
                'Content-Length': str(len(video_data)),
                'Cache-Control': 'no-cache',
            }
        )

    except Exception as e:
        # Cleanup on error
        for f in [video_path, ass_path, output_path]:
            if f:
                try:
                    os.remove(f)
                except:
                    pass
        print(f"Generate error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
