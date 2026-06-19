# VoiceHarvester

A small drag-and-drop desktop app that pulls a clean, isolated **voice** out of
your video and audio files and saves it as a WAV that's ready to feed into AI
voice-cloning tools (ElevenLabs, Play.ht, RVC, XTTS, and similar).

Drop in as many files as you like — it processes them in a batch and can even
stitch them into one combined sample for better cloning results.

---

## What it does

For each file it:

1. Extracts the audio track.
2. Isolates the spoken voice — using **Demucs** (deep-learning separation) if you
   install it, otherwise an **ffmpeg** denoise/clean-up chain that always works.
3. Cleans and normalizes the result to a **mono 44.1 kHz 16-bit WAV**, the format
   cloning services prefer.

Output files are named `<original>_voice.wav`. With the merge option on, you also
get `combined_voice_sample.wav`.

---

## Requirements

**ffmpeg** must be installed (the app uses it under the hood):

- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg`
- Linux: `sudo apt install ffmpeg`

**Python 3.9+**, then optionally install the extras:

```bash
pip install -r requirements.txt
```

- `tkinterdnd2` enables drag-and-drop. Without it, the app still works via the
  **Add files...** button.
- `demucs` (commented out in requirements) gives the best voice isolation but is
  a large download. Enable it by uncommenting the line and re-running pip.

---

## Run it

```bash
python app.py
```

Then drag files onto the window (or click **Add files...**), pick an output
folder, and click **Extract Voice**.

### Command-line version

For folders or automation, skip the GUI:

```bash
python cli.py /path/to/videos -o out/ --merge
```

---

## Tips for good cloning results

- Aim for **1–2+ minutes** of clear speech total. More clean audio = better clone.
- Prefer clips with little background music or noise.
- Use the **merge** option to combine several short clips into one sample.

---

## A note on consent

Cloning a real person's voice should be done with their consent, or — for a
memorial — in line with what your family is comfortable with. Reputable cloning
services require you to confirm you have the right to use the voice.
