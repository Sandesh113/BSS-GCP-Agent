"""Render one walkthrough scene with Gemini TTS on Vertex AI and save WAV files to listen to."""
import base64
import subprocess
import sys
import wave
from pathlib import Path

import requests

PROJECT = "bss-ai-agent-20261021-sandesh"
REGION = "europe-west1"
MODEL = "gemini-2.5-pro-tts"
GCLOUD = Path.home() / "AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
OUT = Path(__file__).parent

STYLE = ("Read this as a calm, confident British male presenter narrating a product walkthrough "
         "for telecom engineers. Measured pace, warm and clear, natural pauses, not dramatic:")
SCENE = ("That makes go-to-market simple. The product manager picks specifications, sets allowances and price, "
         "in the studio or by describing the plan to Gemini. The platform generates the product offering, "
         "the composite product specification and the inherited CFS realization. "
         "The product manager never touches service design.")


def main(voices):
    token = subprocess.run([str(GCLOUD), "auth", "print-access-token"], capture_output=True, text=True,
                           check=True).stdout.strip()
    url = (f"https://{REGION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT}/locations/{REGION}"
           f"/publishers/google/models/{MODEL}:generateContent")
    for voice in voices:
        body = {"contents": {"role": "user", "parts": {"text": f"{STYLE} {SCENE}"}},
                "generation_config": {"response_modalities": ["AUDIO"], "speech_config": {
                    "language_code": "en-GB", "voice_config": {"prebuilt_voice_config": {"voice_name": voice}}}}}
        reply = requests.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=120)
        if not reply.ok:
            print(voice, "HTTP", reply.status_code, reply.text[:600])
            continue
        part = reply.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(part["data"])
        path = OUT / f"sample-{voice.lower()}.wav"
        with wave.open(str(path), "wb") as wav:  # Vertex returns headerless 16-bit mono PCM at 24 kHz
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        print(voice, part.get("mimeType"), f"{len(pcm) / 48000:.1f}s", path)


if __name__ == "__main__":
    main(sys.argv[1:] or ["Charon", "Orus"])
