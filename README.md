# CaptionShift — Setup Instructions

## LOCAL TESTING (do this first!)

### Step 1 — Install dependencies
Open terminal in this folder and run:
```
python -m pip install flask flask-cors openai-whisper torch numpy
```
This takes 5-10 minutes (downloads Whisper + PyTorch).

### Step 2 — Start the backend
```
python app.py
```
Wait until you see: "Whisper model loaded! Ready."

### Step 3 — Open the frontend
Open Chrome/Brave and go to: http://localhost:5001
(The app now serves itself — no need to open index.html separately)

### Step 4 — Test it
1. Upload a video
2. Drag the caption label to position it
3. Choose a style
4. Click "Transcribe Speech" — wait 1-2 mins
5. Edit captions if needed
6. Click "Burn Captions & Download"
7. Video downloads directly in your browser ✅
   (Works on Chrome, Brave, Safari — including iPad!)

---

## DEPLOY TO RENDER.COM

### Step 1 — Push to GitHub
Create a new GitHub repo and push all these files:
- app.py
- index.html
- requirements.txt
- Dockerfile

### Step 2 — Create Render Web Service
1. Go to render.com → New → Web Service
2. Connect your GitHub repo
3. Select "Docker" as environment
4. Set name e.g. "captionshift"
5. Click Deploy

### Step 3 — Update the frontend URL
Once deployed, Render gives you a URL like:
  https://captionshift.onrender.com

Open index.html, find this line (around line 800):
  const BACKEND = "http://localhost:5001";

Change it to:
  const BACKEND = "https://captionshift.onrender.com";

Then push to GitHub — Render auto-redeploys.

### Step 4 — Access from iPad
Open Safari/Chrome on iPad and go to:
  https://captionshift.onrender.com
Done! ✅

---

## NOTES
- Render free tier sleeps after 15 min inactivity (first request takes ~30s to wake)
- The video processes on the server and downloads directly to your browser
- Works on Safari, Chrome, and Brave on all devices
