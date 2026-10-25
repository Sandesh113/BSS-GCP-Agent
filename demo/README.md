# 🎧 Narrated walkthrough

**From product specification to a network-ready service order**: an 11-scene, about 4½-minute walkthrough of this BSS proof of concept for telecom and BSS teams. It is narrated with Google Gemini 2.5 Pro text-to-speech (voice **Charon**, calm British male presenter).

Online copy: [GitHub Pages walkthrough](https://sandesh113.github.io/BSS-GCP-Agent/)

## Open it

Double-click [`catalogue-to-network.html`](catalogue-to-network.html) and press **▶ Play**. The page reads its narration from `audio/`, so keep the folder together. Fonts load from Google Fonts when online; everything else is in the page.

GitHub's file viewer shows the HTML source; use the GitHub Pages link above to play it online. For offline use, clone the repository or download the `demo/` folder with its `audio/` files.

If your browser blocks local audio, serve the folder instead and open <http://127.0.0.1:8000/catalogue-to-network.html>:

```powershell
.venv\Scripts\python.exe -m http.server 8000 --directory demo
```

**Controls:** Play/Pause, Back, Next, Start over, chapter markers, Mute (silent timed captions), and the keyboard (Space, ← →). To make a video, press Play and screen-record the panel.

## What's here

| Path | Contents |
| --- | --- |
| `catalogue-to-network.html` | The player, scenes, captions and the copyable narration script |
| `audio/scene-01.wav` … `scene-11.wav` | One recorded clip per scene (24 kHz mono, about 13 MB in total) |
| `tools/scenes.json` | The 11 narration texts, extracted from the page |
| `tools/extract_scenes.py` | Pulls each scene's `say:"…"` text out of the page |
| `tools/make_sample.py` | Voice settings (model, region, style instruction) and a two-voice sample run |
| `tools/make_scenes.py` | Renders every scene with Charon; spells out acronyms such as TMF622 for the audio only |

## Re-record after changing the narration

Edit a scene's `say` text in the page, then run from the project root (needs `gcloud` signed in to the project and Vertex AI access):

```powershell
.venv\Scripts\python.exe demo\tools\extract_scenes.py demo\catalogue-to-network.html demo\tools\scenes.json
.venv\Scripts\python.exe demo\tools\make_scenes.py demo\tools\scenes.json demo\audio 6
```

The trailing number re-records only that scene (omit it to re-record all 11). Each run calls `gemini-2.5-pro-tts` in `europe-west1` on project `bss-ai-agent-20261021-sandesh`; the whole script is about 3,100 characters, so a full re-record costs a few pence.

If a clip cannot play, the page falls back to the browser's built-in voice and says so.
