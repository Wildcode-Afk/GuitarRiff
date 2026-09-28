# GuitarRiff (FreeTabGen) — Project Status

Last updated: 2026-09-28 — after **Step 1**.

## Current state

- **Current step:** 1 — Audit and architecture — **DONE**
- **Next step:** 2 — Repository scaffold and tooling — **NOT STARTED** (waiting for the Prompt 02 text; Q1 does not block it)
- **Application code written:** none (by design)

## Common rules (apply to every step)

1. Only modify what the step requires.
2. Do not rewrite working code without a reason.
3. Do not move to the next step automatically.
4. Test before considering the step finished.
5. If a test fails, fix it before finishing.
6. Never hide an error.
7. Update this file.
8. End with a report: files modified + tests + results + known issues.
9. **STOP is mandatory** at the end of each step.

## Roadmap progress

| Step | Name | Status |
|---|---|---|
| 1 | Audit and architecture (docs only) | Done |
| 2 | Repository scaffold and tooling | Not started |
| 3 | Basic Pitch environment smoke test | Not started |
| 4 | NoteEvent / Transcription models | Not started |
| 5 | Upload ingest + FFmpeg normalization | Not started |
| 6 | YouTube link handling (no audio download, scope to confirm) | Not started |
| 7 | Audio preprocessing | Not started |
| 8 | Basic Pitch adapter (isolated) | Not started |
| 9 | Note post-processing | Not started |
| 10 | Instrument mapping | Not started |
| 11 | Tablature generation | Not started |
| 12 | Chord detection | Not started |
| 13 | MIDI and ASCII tab export | Not started |
| 14 | Job orchestration and REST API | Not started |
| 15 | Frontend scaffold | Not started |
| 16 | Tab viewer and chords | Not started |
| 17 | Synchronized playback | Not started |
| 18 | Corrections and MusicXML export | Not started |
| 19 | Robustness and security | Not started |
| 20 | E2E tests, docs, Docker, release | Not started |

Dependencies between steps are listed in `docs/ARCHITECTURE.md`, section 11.

## Step 1 report

### Files modified

| File | Action |
|---|---|
| `docs/ARCHITECTURE.md` | Created |
| `docs/PROJECT_STATUS.md` | Created |

No application code, configuration or dependency file was created or changed.

### Audit results

| Item | Result |
|---|---|
| Existing project | None (greenfield: 1 commit, `.gitattributes` only) |
| Python | 3.12.3 (3.11 not installed, available through `uv`) |
| Node / npm | v22.22.2 / 10.9.7 |
| FFmpeg | 6.1.1 |
| yt-dlp | Not installed |
| Frontend / backend files | None |
| Configuration | None |

### Tests and results

| Check | Method | Result |
|---|---|---|
| Roadmap has exactly 20 steps | Script parsing the roadmap table | OK |
| No circular dependency | Topological sort (Kahn) | OK, valid order found |
| Every dependency points to an earlier step | Script | OK |
| Every step reachable from Step 1 | Script | OK |
| Every module in the responsibility table exists in the directory tree | Script | OK |
| Basic Pitch installability | Read `basic-pitch 0.4.0` wheel metadata and tried to resolve its TensorFlow requirement | **Fails on Python 3.12** (see below) |

Internal consistency of the architecture was checked by reading: the pipeline stages, module table, directory tree, NoteEvent model and API all use the same names.

### Known problems / findings

1. **Blocking for Step 3 if ignored:** `basic-pitch 0.4.0` requires `tensorflow>=2.4.1,<2.15.1` on Linux with Python >= 3.11. No such TensorFlow release exists for Python 3.12. The project must run on **Python 3.11**.
2. The ONNX alternative for Basic Pitch on Python 3.11 has **not** been tested; it is only a fallback to evaluate in Step 3.
3. The audit machine has 1 CPU core and about 4 GB RAM, so real-model tests must stay small.
4. Downloading from YouTube may violate YouTube's Terms of Service. **Resolved:** the owner decided that nothing is downloaded (D4). The consequence for the audio source is open (Q1).
5. The `basic-pitch` install itself was not attempted in full (only metadata and dependency resolution), so its real runtime behaviour is unverified until Step 3.

## Decisions (owner)

| # | Decision | Status |
|---|---|---|
| D1 | Product name | **GuitarRiff** (confirmed). Package `guitarriff` |
| D2 | Python version | 3.11 pinned with `uv` — proposed, not yet answered |
| D3 | Frontend stack | Delegated to Claude: Vite + React + TypeScript |
| D4 | YouTube usage | **No audio download.** The link is only used to work with the song |
| D5 | Instruments | Defined by the following prompts |

## Open questions

| # | Question | Why it matters |
|---|---|---|
| Q1 | Without downloading YouTube audio, where does the audio for Basic Pitch come from? Options: (a) the user uploads an audio file they own, the YouTube link gives metadata (title, artist, duration) and an embedded player for listening; (b) another source chosen by the owner | Basic Pitch transcribes audio only. A link alone contains no audio, so no notes can be extracted from it. This decides Steps 5, 6 and 8 and the pipeline diagram |

## Decision log

| Date | Step | Decision |
|---|---|---|
| 2026-09-28 | 1 | Owner: app is GuitarRiff; no audio download from YouTube; frontend delegated; instruments follow later prompts |
| 2026-09-28 | 1 | Upload ingest (Step 5) is built before YouTube (Step 6) so the pipeline can be developed without a fragile source |
| 2026-09-28 | 1 | `basic_pitch` may be imported only by `transcription/basic_pitch_adapter.py` |
| 2026-09-28 | 1 | librosa is limited to preprocessing and analysis, never a substitute for Basic Pitch |

---

**STOP — Step 1 complete. Step 2 must not begin until explicitly requested.**
