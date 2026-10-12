"""Tests de `tablature/service.py` — orchestration sur le Song persisté."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.audio.service import normalize_stored_audio
from guitarriff.config import Settings
from guitarriff.errors import InvalidInstrumentForFretboardMappingError, NotFoundError
from guitarriff.model import InstrumentKind
from guitarriff.tablature import service
from guitarriff.tablature.fretboard import STANDARD_GUITAR_TUNING
from guitarriff.transcription import service as transcription_service
from guitarriff.transcription.basic_pitch_adapter import RawNoteEvent


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path)


@pytest.fixture
def storage(settings: Settings) -> AudioFileStorage:
    return AudioFileStorage(settings)


def _transcribed_file(
    storage: AudioFileStorage, settings: Settings, tmp_path: Path, notes: list
) -> str:
    import subprocess

    source = tmp_path / "gen.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.0",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )
    normalize_stored_audio(record.file_id, settings, storage)

    with patch.object(transcription_service, "run_basic_pitch", return_value=notes):
        transcription_service.transcribe(
            record.file_id, InstrumentKind.GUITAR, "mixture", settings, storage
        )

    return record.file_id


def test_map_fretboard_updates_persisted_song(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    notes = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)]
    file_id = _transcribed_file(storage, settings, tmp_path, notes)

    outcome = service.map_fretboard(file_id, InstrumentKind.GUITAR, storage)

    assert outcome.placed_count == 1
    assert outcome.unplaced_count == 0
    track = outcome.song.tracks[0]
    assert track.tuning == STANDARD_GUITAR_TUNING
    assert track.notes[0].instrument_info is not None

    persisted = storage.read_song(file_id)
    assert persisted == outcome.song


def test_map_fretboard_rejects_unsupported_instrument(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    notes = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)]
    file_id = _transcribed_file(storage, settings, tmp_path, notes)

    with pytest.raises(InvalidInstrumentForFretboardMappingError):
        service.map_fretboard(file_id, InstrumentKind.DRUMS, storage)


def test_map_fretboard_without_song_raises_not_found(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    import subprocess

    source = tmp_path / "gen.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.0",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    record = storage.save(
        filename="chanson.wav", declared_content_type="audio/wav", content=source.read_bytes()
    )

    with pytest.raises(NotFoundError):
        service.map_fretboard(record.file_id, InstrumentKind.GUITAR, storage)


def test_map_fretboard_without_matching_track_raises_not_found(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    notes = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)]
    file_id = _transcribed_file(
        storage, settings, tmp_path, notes
    )  # transcrit en guitare seulement

    with pytest.raises(NotFoundError):
        service.map_fretboard(file_id, InstrumentKind.BASS, storage)


def test_map_fretboard_accepts_custom_tuning_capo_and_max_fret(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:
    notes = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=44, amplitude=0.8)]
    file_id = _transcribed_file(storage, settings, tmp_path, notes)

    outcome = service.map_fretboard(file_id, InstrumentKind.GUITAR, storage, capo_fret=2)

    info = outcome.song.tracks[0].notes[0].instrument_info
    assert info.fret == 2  # E2(40) + capo(2) + 2 = 44


def test_map_fretboard_preserves_other_tracks(
    settings: Settings, storage: AudioFileStorage, tmp_path: Path
) -> None:

    notes_guitar = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=69, amplitude=0.8)]
    file_id = _transcribed_file(storage, settings, tmp_path, notes_guitar)

    notes_bass = [RawNoteEvent(start_seconds=0.0, end_seconds=0.5, midi_pitch=40, amplitude=0.8)]
    with patch.object(transcription_service, "run_basic_pitch", return_value=notes_bass):
        transcription_service.transcribe(file_id, InstrumentKind.BASS, "mixture", settings, storage)

    outcome = service.map_fretboard(file_id, InstrumentKind.GUITAR, storage)

    instruments = {t.instrument for t in outcome.song.tracks}
    assert instruments == {InstrumentKind.GUITAR, InstrumentKind.BASS}
