# Narrated Slideshow Generator

Turns a one-line premise into a **30-45 second narrated slideshow**: 5-7 still
images, a slow pan/zoom over each one, a spoken voiceover, stitched into
`final_video.mp4` at 1280x720, plus a `metadata.txt` you paste into YouTube
Studio yourself.

Everything runs on free tiers. There is no local LLM, no paid API, and no
account required for the image or voice stages.

> **This is a slideshow, not animation.** The images are stills and the only
> motion is a Ken Burns pan/zoom applied by FFmpeg. No video-generation model is
> called anywhere in this project. If you were looking for moving characters,
> this is not that.

---

## What you need

| Requirement | Notes |
| --- | --- |
| Python 3.10+ | Uses `X \| Y` type syntax |
| FFmpeg + ffprobe | Must be on `PATH`. Not installable via pip. |
| Internet | For the script, image and voice APIs |
| A home/office connection | **Not** a VPS or VPN - see the Edge TTS caveat below |

Install FFmpeg:

```bash
# Windows
winget install Gyan.FFmpeg        # or: choco install ffmpeg

# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg

# Fedora
sudo dnf install ffmpeg
```

Verify with `ffmpeg -version` and `ffprobe -version`.

---

## Install

```bash
git clone <this-repo>
cd ai_cartoonmaker

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## Configure

```bash
cp .env.example .env
```

Then open `.env` and fill it in. **Model names are deliberately left blank and
have no defaults**, because free-tier model IDs rotate every few months and a
stale hardcoded name fails in confusing ways. Look up the current ones yourself:

| Key | Where to find the value |
| --- | --- |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | https://ai.google.dev/gemini-api/docs/pricing - copy an ID that shows as free |
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `GROQ_MODEL` | https://console.groq.com/docs/models |
| `POLLINATIONS_MODEL` | Optional. Leave blank to use the server default |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_IMAGE_MODEL` | Optional fallback - see below |

You need **Gemini or Groq** (Gemini is preferred; Groq is the fallback). The
image and voice stages need no keys at all.

Check your setup at any time:

```bash
python main.py --check
```

---

## Run the smoke tests first

Do not run the pipeline until these pass. Each prints exactly one `PASS:` or
`FAIL:` line and exits 0 or 1.

```bash
python smoke_tests/test_ffmpeg.py        # no network needed
python smoke_tests/test_edge_tts.py      # no key needed
python smoke_tests/test_gemini.py
python smoke_tests/test_groq.py
python smoke_tests/test_pollinations.py
python smoke_tests/test_cloudflare.py    # skipped if Cloudflare is not configured
```

`test_ffmpeg.py` is the important one. It does not just check that a file
appeared - it compares the first and last frames of the rendered clip and fails
if the "motion" is actually frozen. See [Ken Burns gotcha](#the-ken-burns-gotcha).

See **VALIDATION.md** for the exact expected output of each test and a place to
record your results.

---

## Run

```bash
python main.py "a lighthouse keeper who teaches a seagull to read"
```

Options:

```bash
python main.py "..." --scenes 6          # override SCENE_COUNT
python main.py "..." --out ./myvideo     # override the output directory
python main.py "..." --no-cache          # regenerate everything (costs quota)
python main.py --premise-file idea.txt
python main.py --check                   # readiness report, no work done
```

The first run takes a few minutes. Most of that is deliberate waiting: the
keyless image endpoint is throttled to roughly one request every 15 seconds, and
the tool respects it rather than hammering the API.

### Output

```
output/
├── final_video.mp4     <- upload this
├── metadata.txt        <- paste title/description/tags from this
├── concat_list.txt
└── scenes/
    ├── scene_01.mp4
    └── ...
```

---

## How it works

```
premise
   │
   ├─ 1. script_generator.py   Gemini  ->  Groq fallback
   │        strict JSON: {"title", "scenes":[{"scene_number","dialogue","image_prompt"}]}
   │
   ├─ 2. image_generator.py    Pollinations (keyless)  ->  Cloudflare Workers AI fallback
   │        one still per scene, cached by prompt hash
   │
   ├─ 3. tts_generator.py      Edge TTS, one MP3 per scene, cached by text hash
   │
   ├─ 4. animation_engine.py   FFmpeg Ken Burns per scene
   │        clip length = measured TTS audio duration + tail pad
   │
   └─ 5. video_assembler.py    concat demuxer, stream copy, 1280x720 H.264 + AAC
```

Every external call has an explicit connect and read timeout. Every fallback
logs at `WARNING` with the reason it was used, so you always know which provider
actually served your video.

### Caching

Generated images and narration are content-addressed by hash in `.cache/`:

```
.cache/
├── images/<sha256>.png     + <sha256>.json  (records the prompt and provider)
└── tts/<sha256>.mp3
```

If a run fails halfway through, **re-run it**. Finished assets are reused and
you do not re-spend free-tier quota on them. Change a scene's prompt and only
that scene regenerates. Delete `.cache/` to start clean.

---

## FFmpeg notes

### The Ken Burns gotcha

The often-copied zoompan idiom

```
zoompan=z='min(zoom+0.0012,1.5)':d=1
```

**does not work.** With `d=1`, `zoom` is recomputed from scratch for every
output frame rather than fed back from the previous one, so that expression
produces a clip that is essentially frozen while looking superficially correct.

This was measured against FFmpeg 7.0.2 before the code was written: first frame
vs last frame came out at **71 dB PSNR** (visually identical) using `zoom+`, and
**10-25 dB** using the `on`-driven form below, which is what this project uses:

```
zoompan=z='1+0.14*min(on\,90)/90':...:d=1
```

If you edit the motion, keep driving it from `on` (the output frame index) and
keep the `test_ffmpeg.py` motion check.

### Other things the code does on purpose

* **2x upscale before `zoompan`.** Zooming the original pixels directly makes
  the motion shimmer.
* **`force_original_aspect_ratio=increase` then `crop`.** Image models return
  16:9, 1:1 or anything else depending on load; this guarantees the frame is
  filled without stretching or letterboxing.
* **A short tail pad** (`SCENE_TAIL_PAD_SECONDS`, default 0.35s) is added to
  each clip so the last word is never clipped mid-syllable. Clip length is
  otherwise driven by the measured TTS duration.
* **A stream-copy concat.** All scenes share encoder settings, so the join is
  lossless. If it ever fails, the code re-encodes and says so at `WARNING`.
* **ffprobe is preferred, but not required.** If it is missing, durations are
  parsed from `ffmpeg -i` output and a warning is logged once. Install ffprobe
  for the documented path.

---

## Limitations and honest caveats

### Character consistency is unreliable

Image models have no memory between calls. Scene 3's character will not
reliably be the same individual as scene 1's.

The mitigation used here is the only one that actually helps: every
`image_prompt` is required to repeat the same verbatim 25-45 word block
describing the recurring cast and art style. The pipeline measures how much of
that block really is shared and logs a `WARNING` when the overlap is too small.

**Do not use seeds expecting consistency.** Fixed seeds do not preserve
character identity. This project does not claim otherwise, and does not offer a
"consistent character" mode.

### Edge TTS is unofficial - read this

`edge-tts` talks to Microsoft Edge's "Read Aloud" endpoint. It is a free,
reverse-engineered client for an undocumented service that Microsoft has never
agreed to support.

Consequences you should expect:

* **It can break at any time**, with no notice and no changelog.
* **It often fails from datacenter IPs, VPSes and VPNs.** Microsoft applies
  IP-level anti-abuse filtering. Run this project from a normal home or office
  connection.
* It has historically returned `403 WSServerHandshakeError` when Microsoft
  rotates the short-lived anti-abuse token the Edge browser normally supplies.
* It sometimes fails intermittently and succeeds on retry.

**Run this locally, not on a server.** The code retries with exponential backoff
and pins a known-good version, and a failed synthesis tells you exactly which of
the above to check.

If it is blocked for you, alternate free options exist but are outside the scope
of this project (Azure Speech has a free monthly allowance but needs a key).

### The keyless image endpoint is throttled

Pollinations' keyless `image.pollinations.ai` endpoint is the simplest way to
get free images, and it is genuinely free. But as of the time of writing:

* Anonymous requests are throttled to roughly **one per 15 seconds**.
* Images **may carry a watermark**. `nologo=true` is a hint, not a guarantee;
  full watermark removal is tied to registering an account.
* A throttled or blocked request can still return **HTTP 200 with an HTML body**,
  which is why this project validates the image magic bytes instead of trusting
  the status code.

The adjustable `POLLINATIONS_MIN_INTERVAL_SECONDS` is set to 15 by default so
you stay under the limit instead of collecting 429s.

### Why there is no YouTube uploader

Deliberately omitted. Automating the upload would not work well anyway:

1. **An unaudited Google Cloud project can only upload videos as `private`.**
   Videos stay invisible to everyone else until the project passes Google's
   audit, so an "upload" would silently not go live.
2. **OAuth refresh tokens expire in about 7 days** while the app is in
   "Testing" status. An unattended uploader would need you to re-authenticate
   every week, which defeats the point.
3. **Bulk, repetitive, machine-generated uploads risk YouTube's monetization and
   spam policies.** Generating and publishing these at scale can get a channel's
   monetization limited.

So the pipeline stops at `metadata.txt`. Open YouTube Studio, create the video,
and copy the title, description and tags across. It takes about a minute and you
stay in control of what gets published.

### Copyright

Every character name in the generated script is original by instruction. The
prompt explicitly forbids using character names, mascots, catchphrases or
settings from any existing film, TV series, game, book, comic or brand, and
forbids imitating a named franchise's art style. Imitating a specific existing
show's characters or look invites copyright and trademark claims, so this
project never asks for it.

Generated scripts can still surprise you. Skim before publishing.

### Free tiers change

Free-tier model IDs, rate limits and quotas change every few months. That is
exactly why no model name is hardcoded anywhere in this project - every one is
read from `.env`. When something starts returning 404 or 400, check the
provider's pricing page and update `.env`. Do not edit the Python.
Cloudflare Workers AI gives 10,000 Neurons/day shared across all its models;
one 1024x1024 `flux-1-schnell` image costs a few Neurons, so the daily allowance
covers hundreds of images. Google's free tier limits apply per Google Cloud
project, not per API key, and reset at midnight Pacific.

---

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `FAIL: network unreachable` | Offline machine, firewall, proxy or sandbox egress allowlist. Not an API-key problem. |
| `FAIL: HTTP 401` / `403` from Gemini or Groq | Bad key, or the key belongs to a different project. Regenerate it. |
| Gemini `HTTP 404` | `GEMINI_MODEL` no longer exists or is not free any more. Re-check the pricing page. |
| Gemini `HTTP 429` | Free-tier rate limit. Wait; limits reset at midnight Pacific. |
| `FAIL: HTTP 403` / `NoAudioReceived` on Edge TTS | Datacenter IP or VPN, or the endpoint changed. See the Edge TTS section. |
| `ffmpeg was not found on PATH` | Install FFmpeg (see above) and reopen your terminal. |
| Images all look identical | You are seeing the provider's cache. The tool sends a random seed per request to avoid this. |
| Total duration is outside 30-45s | TTS pacing differs from the estimate. Adjust `MIN_TOTAL_SECONDS` / `MAX_TOTAL_SECONDS` or `SCENE_COUNT` in `.env` and re-run - cached assets are reused, so it costs almost nothing. |
| Characters drift between scenes | Expected. See [Character consistency](#character-consistency-is-unreliable). |

---

## Project layout

```
ai_cartoonmaker/
├── main.py                 entry point, orchestration, metadata.txt writer
├── config.py               .env loading; refuses to default any model name
├── utils.py                logging, error types, caching, bounded HTTP/subprocess
├── script_generator.py     Gemini primary, Groq fallback, strict JSON validation
├── image_generator.py      Pollinations primary, Cloudflare fallback, throttling
├── tts_generator.py        Edge TTS with backoff and a real error message
├── animation_engine.py     Ken Burns filters, duration probing, scene rendering
├── video_assembler.py      concat, stream-copy join, output verification
├── requirements.txt        pinned
├── .env.example            every key, no invented defaults
├── VALIDATION.md           step-by-step local validation + results log
├── README.md
└── smoke_tests/
    ├── _common.py
    ├── test_gemini.py
    ├── test_groq.py
    ├── test_pollinations.py
    ├── test_cloudflare.py
    ├── test_edge_tts.py
    └── test_ffmpeg.py
```

---

## Cost

Zero, on free tiers. There is no code path that can spend money: no billing
keys are read, no paid model is referenced, and the only optional credentialed
provider (Cloudflare Workers AI) is on its free daily allowance.
