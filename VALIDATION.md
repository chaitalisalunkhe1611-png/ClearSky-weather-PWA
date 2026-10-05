# Local Validation

Run these steps on **your own machine**. They cannot be completed inside a
sandbox that blocks the provider hosts (see
[What was verified in the sandbox](#what-was-verified-in-the-sandbox) at the
bottom for exactly what was and was not confirmed).

Budget about 15 minutes, most of it waiting on the image throttle.

---

## Step 0 - Prerequisites

```bash
python --version        # need 3.10 or newer
ffmpeg -version         # need any recent build
ffprobe -version        # should ship alongside ffmpeg
```

If `ffprobe` is missing, the project still works (it parses `ffmpeg -i` output
instead and warns once), but install it if you can.

<details>
<summary>Paste your output here</summary>

```
(drag your terminal output in here)

```

</details>

---

## Step 1 - Install and configure

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Now edit `.env`. At minimum you need a script provider:

* `GEMINI_API_KEY` + `GEMINI_MODEL` - **or** -
* `GROQ_API_KEY` + `GROQ_MODEL`

Model names are intentionally blank. Get them from the pages linked in the
`.env.example` comments. Image and voice stages need no keys.

Then confirm the wiring:

```bash
python main.py --check
```

Expect a table where `Script / Gemini` or `Script / Groq` shows `OK`, and the
last line reads `Ready. Next: python smoke_tests/test_ffmpeg.py`.

<details>
<summary>Paste your <code>--check</code> output here</summary>

```
(paste here)

```

</details>

---

## Step 2 - Smoke tests

Run these **in this order**. Each prints exactly one `PASS:` or `FAIL:` line and
exits 0 or 1. Do not move on to the pipeline until they pass.

### 2a. FFmpeg (no network, no keys)

```bash
python smoke_tests/test_ffmpeg.py
```

Expected: `PASS`, a ~3.0s clip, 90-91 frames, and a motion line reading roughly
`first vs last frame PSNR = 10-25 dB`.

This is the most important test. It fails if the clip is frozen, which is what a
naive `zoompan` expression produces. Anything above 45 dB means "not moving".

```
PASS: FFmpeg rendered a real 3.03s Ken Burns clip (91 frames, pattern 'zoom_in',
first/last frame PSNR 10.65 dB) at .../output/smoke/ffmpeg_test_clip.mp4
```

<details>
<summary>Paste your output here</summary>

```
(paste here)

```

</details>

### 2b. Edge TTS (no key, but needs a normal internet connection)

```bash
python smoke_tests/test_edge_tts.py
```

Expected: `PASS`, an MP3 path, a duration of about 2-3 seconds for the 12-word
test sentence, and a words-per-minute figure around 130-170.

If this fails with `403` or `NoAudioReceived`, you are almost certainly on a
datacenter IP or VPN - Microsoft blocks those. Try a normal home/office
connection before assuming the code is broken.

<details>
<summary>Paste your output here</summary>

```
(paste here)

```

</details>

### 2c. Gemini

```bash
python smoke_tests/test_gemini.py
```

Expected: a numbered list of model IDs your key can see (with your
`GEMINI_MODEL` marked), then one real reply, then `PASS`.

If your configured model is not in the list, the test fails and tells you to pick
one that is. That is the free tier having moved on - update `.env`.

<details>
<summary>Paste your output here</summary>

```
(paste here)

```

</details>

### 2d. Groq (fallback script provider)

```bash
python smoke_tests/test_groq.py
```

Expected: the same shape as Gemini. If you are not using Groq, this can fail
without blocking you - Gemini alone is enough.

<details>
<summary>Paste your output here</summary>

```
(paste here)

```

</details>

### 2e. Pollinations (keyless image endpoint)

```bash
python smoke_tests/test_pollinations.py
```

Expected: `PASS`, plus the HTTP status, the Content-Type, and a saved image at
`output/smoke/pollinations_test.png` (or `.jpg`).

**Open that image and look at it.** Check whether a watermark is visible. The
test verifies the bytes are a real image, not that the image is unwatermarked.

If you get `HTTP 429`, wait a minute and retry - the anonymous tier allows about
one request every 15 seconds.

<details>
<summary>Paste your output here</summary>

```
(paste here)

```

</details>

### 2f. Cloudflare (optional fallback)

```bash
python smoke_tests/test_cloudflare.py
```

Expected if you have not set the Cloudflare keys:
`PASS: skipped - none of CF_ACCOUNT_ID / CF_API_TOKEN / CF_IMAGE_MODEL is set...`

Expected if you have set all three: `PASS` plus a saved image.
If you set *one or two* of the three, this **fails** - partial configuration is
a real mistake worth catching.

<details>
<summary>Paste your output here</summary>

```
(paste here)

```

</details>

---

## Step 3 - Results summary

Fill this in from the runs above.

| Test | Result (PASS/FAIL) | Notes |
| --- | --- | --- |
| `test_ffmpeg.py` | | |
| `test_edge_tts.py` | | |
| `test_gemini.py` | | |
| `test_groq.py` | | |
| `test_pollinations.py` | | |
| `test_cloudflare.py` | | |

**If any test failed, stop here.** Send the failing output back - do not run the
pipeline on a broken stage, because you will just burn free-tier quota.

---

## Step 4 - Full pipeline

Only once every test above passes.

```bash
python main.py "a lighthouse keeper who teaches a seagull to read"
```

This takes a few minutes. The image stage deliberately pauses ~15 seconds
between requests to respect the anonymous rate limit, so 5 scenes means about
75 seconds of waiting on images alone. That is expected and logged.

A successful run ends with:

```
DONE
Video    : output/final_video.mp4
Metadata : output/metadata.txt
```

### Then check the actual output

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/final_video.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of default=noprint_wrappers=1 output/final_video.mp4
```

Confirm, and **watch the video** rather than trusting the numbers:

- [ ] Duration is between 30 and 45 seconds
- [ ] Resolution is 1280x720 and the codec is h264
- [ ] There is an audio stream and you can hear narration throughout
- [ ] The narration is not cut off mid-word at any scene boundary
- [ ] Every scene's image **moves** - if any clip looks frozen, `test_ffmpeg.py`
      lied and you should report it
- [ ] The images match the story
- [ ] No on-screen text, logos or watermarks in the images
- [ ] The character looks *roughly* the same across scenes

That last point is a judgement call, not a guarantee. **Character consistency is
unreliable** - see the README. Some drift between scenes is normal and expected.

<details>
<summary>Paste your pipeline output here</summary>

```
(paste here)

```

</details>

---

## Step 5 - Test the cache

This is the failure-recovery guarantee: a failed rerun must not re-spend quota.

```bash
python main.py "a lighthouse keeper who teaches a seagull to read"
```

The second run should complete in seconds, not minutes, and the logs should show
lines like:

```
Scene 1: reusing cached image ...
Scene 1: reusing cached narration ...
```

If it re-generates everything, the cache is broken - report it.

<details>
<summary>Paste your second-run output here</summary>

```
(paste here)

```

</details>

---

## Step 6 - Manual upload (optional)

Open `output/metadata.txt`, then in YouTube Studio:

1. Create a video, upload `final_video.mp4`.
2. Paste the **title**.
3. Paste the **description**.
4. Under *Show more*, paste the **tags**.

There is no uploader in this project, on purpose. See the "Why there is no
YouTube uploader" section of the README.

---

# What was verified in the sandbox

So you know which failures to take seriously and which are just this
environment. The sandbox this project was written in has an **egress allowlist**:
PyPI and GitHub are reachable, but `generativelanguage.googleapis.com`,
`api.groq.com`, `image.pollinations.ai`, `api.cloudflare.com` and
`speech.platform.bing.com` are all blocked at the proxy.

### Verified for real

| Item | How | Result |
| --- | --- | --- |
| FFmpeg Ken Burns rendering | Ran `test_ffmpeg.py` | **PASS** - 3.03s clip, 91 frames, first/last frame PSNR 10.65 dB (real motion) |
| The `zoompan` `d=1` bug | A/B measurement | The `zoom+` idiom scored 71 dB (frozen); the `on`-driven form scored 10-25 dB. The project uses the second. |
| Duration probing without ffprobe | Ran with ffprobe absent | Worked via `ffmpeg -i` parsing, warned once |
| Full local video pipeline | 5 synthetic images + 5 synthetic tones through the real `animation_engine` / `video_assembler` / metadata writer | **PASS** - 37.86s output, 1280x720, H.264 High yuv420p + AAC 44100 stereo, stream-copy join, audio decoded cleanly |
| Scene frame counts | Measured | Clip length tracked the measured audio duration, not the nominal one (MP3 pads 3.000s to 3.030s) |
| `main.py --check` | Ran it | **PASS** - correct readiness report |
| `metadata.txt` generation | Ran it | Correct title/description/tags and scene timestamps |

### NOT verified - you must do these

| Item | Why |
| --- | --- |
| Gemini script generation | Host blocked by the sandbox proxy |
| Groq script generation | Host blocked |
| Pollinations image generation | Host blocked |
| Cloudflare image generation | Host blocked |
| Edge TTS synthesis | Host blocked; also the classic datacenter-IP failure mode |

Those five smoke tests were run in the sandbox and all returned
`FAIL: network unreachable - the request never reached the provider`, which is
the correct and expected result there. **It is not evidence that these APIs are
broken or that the code is wrong.** Their request-building and error-handling
paths were exercised; their happy paths were not.

The synthetic-asset test in the table above used locally generated gradient
images and sine-wave tones. It does not fake any API response, and it says
nothing about whether the providers work.

### Things the sandbox could not check at all

- Whether your images are watermarked
- Whether the generated characters look consistent enough for your taste
- Whether Edge TTS is blocked on your connection
- Whether the final video is pleasant to watch - **watch it**
