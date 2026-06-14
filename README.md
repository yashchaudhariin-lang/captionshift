# CaptionShift — v2

## What's New in v2

### 1. Quality Fix (the big one)
Previous versions re-encoded everything with CRF 23, which visibly reduced
quality and shrank file size dramatically (100MB → 10MB).

v2 now:
- Encodes video at **CRF 16** (visually lossless) with `preset medium`
- **Copies the audio stream untouched** (`-c:a copy`) — zero audio quality loss
- Keeps `pix_fmt yuv420p` for compatibility and adds `+faststart` for instant playback
- Falls back to AAC 192k re-encode only if the original audio codec can't be
  copied into MP4 (rare)

Output file size and quality will now be very close to your original video —
no more "AI-generated" washed-out look.

### 2. 9 New Bundled Fonts
These are embedded in the app (in the `fonts/` folder) and burned directly
into the video — no installation needed:

| Font | Vibe |
|---|---|
| Montserrat (Bold) | Modern, clean, geometric |
| Oswald (Bold) | Tall, condensed, YouTube-style |
| Anton | Heavy display, dramatic |
| Bebas Neue | All-caps impact, Reels/Shorts |
| Righteous | Retro rounded |
| Pacifico | Handwriting script |
| Lobster | Playful script |
| Dancing Script (Bold) | Elegant cursive |
| Amatic SC (Bold) | Thin handwritten |

Plus the original 12 system fonts (Arial, Impact, Helvetica, Georgia, etc.)
are still available.

### 3. Font Size Control
New Small / Medium / Large / XL selector. Size is calculated as a percentage
of your video's height, so captions scale correctly no matter the resolution.

### 4. 7 New Elegant Color Themes
Added under a new "✨ Elegant" group in the style picker:

- Ivory Classic
- Rose Gold
- Ice Blue
- Mint Glow
- Sunset Coral
- Royal Purple (box)
- Cinema (letter-spaced subtitle box)

Total: 19 color themes now available.

### 5. Auto Backend Detection
`app.py` now serves `index.html` itself (Flask `/` route), and the frontend
auto-detects its backend URL via `window.location.origin`. This means:
- **Local testing**: run `python app.py`, open `http://localhost:7860` — works immediately
- **Hugging Face deploy**: works automatically, no URL editing needed

---

## How to Test Locally

1. Make sure this folder structure is intact:
```
captionshift/
├── app.py
├── index.html
├── fonts/
│   ├── Montserrat-Bold.ttf
│   ├── Oswald-Bold.ttf
│   ├── Pacifico-Regular.ttf
│   ├── BebasNeue-Regular.ttf
│   ├── DancingScript-Bold.ttf
│   ├── Anton-Regular.ttf
│   ├── Righteous-Regular.ttf
│   ├── Lobster-Regular.ttf
│   └── AmaticSC-Bold.ttf
├── Dockerfile
├── requirements.txt
└── README.md
```

2. Run:
```
python app.py
```

3. Open your browser to:
```
http://localhost:7860
```

(Flask now serves the page directly — no need to double-click index.html separately)

4. Upload a video, pick a font + size + color theme, drag the caption position,
   transcribe, then burn & download.

---

## Deploying to Hugging Face

1. Upload all files (including the `fonts/` folder) to your Hugging Face Space
2. The Dockerfile already copies `fonts/` into the container
3. No changes needed to `index.html` — `window.location.origin` handles it automatically

---

## Known Notes

- First run after deploy will be slightly slower because the `fonts/` folder
  is copied into the temp upload directory once at startup.
- If your input video's audio codec can't be copied into MP4 (very rare),
  the backend automatically falls back to AAC 192kbps — still high quality.
