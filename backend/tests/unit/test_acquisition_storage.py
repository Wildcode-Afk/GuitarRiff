"""Vérifie le stockage des fichiers audio : validation, identifiants internes,
absence de traversée de répertoire, suppression contrôlée."""

from __future__ import annotations

import pytest

from guitarriff.acquisition.storage import AudioFileStorage
from guitarriff.config import Settings
from guitarriff.errors import (
    FileTooLargeError,
    InvalidFileIdError,
    NotFoundError,
    UnsupportedFileTypeError,
)

VALID_WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16


@pytest.fixture
def storage(tmp_path) -> AudioFileStorage:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    return AudioFileStorage(settings)


def test_save_accepts_valid_wav_and_returns_uuid(storage: AudioFileStorage) -> None:
    record = storage.save(
        filename="ma_chanson.wav", declared_content_type="audio/wav", content=VALID_WAV
    )

    assert record.format == "wav"
    assert record.size_bytes == len(VALID_WAV)
    # L'identifiant doit être un UUID valide (36 caractères avec tirets).
    assert len(record.file_id) == 36


def test_saved_file_is_stored_under_its_own_uuid_directory(
    storage: AudioFileStorage, tmp_path
) -> None:
    record = storage.save(filename="test.wav", declared_content_type="audio/wav", content=VALID_WAV)

    stored_path = tmp_path / "uploads" / record.file_id / record.stored_filename
    assert stored_path.is_file()
    assert stored_path.read_bytes() == VALID_WAV


def test_original_filename_never_used_as_path_component(
    storage: AudioFileStorage, tmp_path
) -> None:
    malicious_name = "../../../etc/passwd.wav"
    record = storage.save(
        filename=malicious_name, declared_content_type="audio/wav", content=VALID_WAV
    )

    # Le fichier doit être stocké normalement, sous son UUID — le nom
    # d'origine malveillant ne doit avoir créé aucun chemin en dehors du
    # répertoire d'upload.
    stored_path = tmp_path / "uploads" / record.file_id / record.stored_filename
    assert stored_path.is_file()
    assert not (tmp_path / "etc").exists()
    # Le nom affiché est assaini (plus de séparateurs de chemin).
    assert "/" not in record.original_filename
    assert ".." not in record.original_filename.split("/")


def test_save_rejects_file_exceeding_size_limit(tmp_path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, max_upload_size_mb=1)
    storage = AudioFileStorage(settings)
    oversized_content = VALID_WAV + b"\x00" * (2 * 1024 * 1024)

    with pytest.raises(FileTooLargeError):
        storage.save(
            filename="big.wav", declared_content_type="audio/wav", content=oversized_content
        )


def test_save_rejects_unrecognized_content(storage: AudioFileStorage) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        storage.save(
            filename="fake.wav", declared_content_type="audio/wav", content=b"not audio at all"
        )


def test_save_rejects_mismatched_extension(storage: AudioFileStorage) -> None:
    # Contenu WAV valide, mais extension .mp3 déclarée : incohérence rejetée.
    with pytest.raises(UnsupportedFileTypeError):
        storage.save(filename="song.mp3", declared_content_type="audio/mpeg", content=VALID_WAV)


def test_get_returns_stored_metadata(storage: AudioFileStorage) -> None:
    saved = storage.save(filename="test.wav", declared_content_type="audio/wav", content=VALID_WAV)
    fetched = storage.get(saved.file_id)

    assert fetched == saved


def test_get_unknown_id_raises_not_found(storage: AudioFileStorage) -> None:
    import uuid

    with pytest.raises(NotFoundError):
        storage.get(str(uuid.uuid4()))


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../../../etc/passwd",
        "..",
        "/etc/passwd",
        "not-a-uuid",
        "",
        "..%2f..%2fetc%2fpasswd",
    ],
)
def test_get_rejects_non_uuid_ids_before_touching_filesystem(
    storage: AudioFileStorage, malicious_id: str
) -> None:
    with pytest.raises(InvalidFileIdError):
        storage.get(malicious_id)


@pytest.mark.parametrize("malicious_id", ["../../../etc/passwd", "..", "not-a-uuid", ""])
def test_delete_rejects_non_uuid_ids(storage: AudioFileStorage, malicious_id: str) -> None:
    with pytest.raises(InvalidFileIdError):
        storage.delete(malicious_id)


def test_delete_removes_the_file_and_its_metadata(storage: AudioFileStorage, tmp_path) -> None:
    saved = storage.save(filename="test.wav", declared_content_type="audio/wav", content=VALID_WAV)
    file_dir = tmp_path / "uploads" / saved.file_id

    assert file_dir.is_dir()
    storage.delete(saved.file_id)
    assert not file_dir.exists()


def test_delete_unknown_id_raises_not_found(storage: AudioFileStorage) -> None:
    import uuid

    with pytest.raises(NotFoundError):
        storage.delete(str(uuid.uuid4()))


def test_purge_all_removes_every_stored_file(storage: AudioFileStorage) -> None:
    storage.save(filename="a.wav", declared_content_type="audio/wav", content=VALID_WAV)
    storage.save(filename="b.wav", declared_content_type="audio/wav", content=VALID_WAV)

    removed = storage.purge_all()

    assert removed == 2
