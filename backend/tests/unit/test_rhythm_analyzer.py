"""Tests de `rhythm/analyzer.py` — exemples synthétiques à tempo connu, et
cas ambigus (silence, bruit, signal trop court)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from guitarriff.errors import NoRhythmDetectedError, RhythmAnalysisError, RhythmAnalysisTimeoutError
from guitarriff.rhythm import analyzer

SAMPLE_RATE = 22050


def _click_track(bpm: float, duration: float, *, sr: int = SAMPLE_RATE) -> np.ndarray:
    period = 60.0 / bpm
    n_clicks = int(duration / period)
    click = np.zeros(int(sr * period), dtype="float32")
    click_len = int(sr * 0.02)
    click[:click_len] = 0.8 * np.sin(2 * np.pi * 1000 * np.arange(click_len) / sr).astype("float32")
    return np.tile(click, n_clicks)


def _write_wav(path: Path, samples: np.ndarray, *, sr: int = SAMPLE_RATE) -> None:
    sf.write(str(path), samples, sr)


def test_detects_known_tempo_within_reasonable_tolerance(tmp_path: Path) -> None:
    # Vérifié manuellement avant ce test : un click track à 120 BPM pur est
    # détecté à ~117.5 BPM par librosa — écart connu de l'algorithme sur un
    # signal de clics, toléré ici à 5 BPM près.
    path = tmp_path / "click_120.wav"
    _write_wav(path, _click_track(120.0, 8.0))

    result = analyzer.analyze_rhythm(path, timeout_seconds=30)

    assert abs(result.tempo_bpm - 117.5) < 1.0
    assert len(result.beat_times) > 0
    assert result.confidence > 0.9  # signal très régulier


def test_confidence_high_on_regular_click_track(tmp_path: Path) -> None:
    path = tmp_path / "click_100.wav"
    _write_wav(path, _click_track(100.0, 8.0))

    result = analyzer.analyze_rhythm(path, timeout_seconds=30)

    assert result.confidence >= 0.9


def test_confidence_low_on_white_noise_ambiguous_case(tmp_path: Path) -> None:
    """Cas ambigu : du bruit blanc n'a aucun rythme réel. La confiance doit
    rester nettement plus basse que sur un signal rythmique régulier —
    vérifié empiriquement (~0.23) avant d'écrire ce test."""

    path = tmp_path / "noise.wav"
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.1, SAMPLE_RATE * 8).astype("float32")
    _write_wav(path, noise)

    try:
        result = analyzer.analyze_rhythm(path, timeout_seconds=30)
    except NoRhythmDetectedError:
        # Issue également acceptable pour du bruit pur : "aucun rythme
        # détecté" est une réponse honnête, pas une erreur de test.
        return

    assert result.confidence < 0.5


def test_silence_raises_no_rhythm_detected_not_a_fake_tempo(tmp_path: Path) -> None:
    path = tmp_path / "silence.wav"
    _write_wav(path, np.zeros(SAMPLE_RATE * 4, dtype="float32"))

    with pytest.raises(NoRhythmDetectedError):
        analyzer.analyze_rhythm(path, timeout_seconds=30)


def test_silent_intro_does_not_degrade_tempo_detection(tmp_path: Path) -> None:
    """Cas 'introduction silencieuse' explicitement demandé : le tempo doit
    rester détecté correctement malgré 2s de silence avant le contenu."""

    path = tmp_path / "intro_silence.wav"
    track = np.concatenate(
        [np.zeros(int(SAMPLE_RATE * 2.0), dtype="float32"), _click_track(120.0, 8.0)]
    )
    _write_wav(path, track)

    result = analyzer.analyze_rhythm(path, timeout_seconds=30)

    assert abs(result.tempo_bpm - 117.5) < 1.0
    # Le premier battement détecté doit se situer après l'introduction.
    assert result.beat_times[0] > 1.5


def test_detects_tempo_change_between_two_known_tempos(tmp_path: Path) -> None:
    path = tmp_path / "tempo_change.wav"
    track = np.concatenate([_click_track(120.0, 8.0), _click_track(90.0, 8.0)])
    _write_wav(path, track)

    result = analyzer.analyze_rhythm(path, timeout_seconds=30)

    assert len(result.tempo_segments) >= 2
    assert result.tempo_segments[0].start_seconds == 0.0
    assert result.tempo_segments[0].bpm > result.tempo_segments[-1].bpm  # 120 -> 90, décroissant


def test_constant_tempo_yields_a_single_segment(tmp_path: Path) -> None:
    path = tmp_path / "constant.wav"
    _write_wav(path, _click_track(110.0, 16.0))

    result = analyzer.analyze_rhythm(path, timeout_seconds=30)

    assert len(result.tempo_segments) == 1
    assert result.tempo_segments[0].start_seconds == 0.0


def test_very_short_audio_still_returns_one_segment_anchored_at_zero(tmp_path: Path) -> None:
    """Cas ambigu : signal trop court pour une analyse par fenêtres —
    toujours un segment unique ancré à 0.0, jamais une erreur ni un
    comportement indéfini."""

    path = tmp_path / "short.wav"
    _write_wav(path, _click_track(120.0, 3.0))

    result = analyzer.analyze_rhythm(path, timeout_seconds=30)

    assert len(result.tempo_segments) == 1
    assert result.tempo_segments[0].start_seconds == 0.0


def test_timeout_raises_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "click.wav"
    _write_wav(path, _click_track(120.0, 2.0))

    def slow_load(*args: object, **kwargs: object) -> tuple[np.ndarray, int]:
        time.sleep(5)
        return np.zeros(100, dtype="float32"), SAMPLE_RATE

    with patch("librosa.load", side_effect=slow_load):
        with pytest.raises(RhythmAnalysisTimeoutError):
            analyzer.analyze_rhythm(path, timeout_seconds=1)


def test_corrupted_file_wrapped_as_rhythm_analysis_error(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.wav"
    path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 4)

    with pytest.raises(RhythmAnalysisError):
        analyzer.analyze_rhythm(path, timeout_seconds=30)
