"""Stockage sécurisé des fichiers audio importés localement.

Règle de sécurité centrale de ce module : **aucune chaîne fournie par
l'utilisateur (nom de fichier, extension déclarée) ne participe jamais à la
construction d'un chemin sur le disque.** Chaque fichier importé reçoit un
identifiant interne (`uuid4`) généré côté serveur, qui devient le seul nom de
répertoire utilisé. Le nom de fichier d'origine est conservé uniquement comme
métadonnée d'affichage (tronqué, assaini), jamais comme composant de chemin.
Cela élimine par construction tout risque de traversée de répertoire
(`../../etc/passwd`, chemins absolus, etc.).
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from guitarriff.acquisition.formats import (
    SNIFF_SIZE,
    SUPPORTED_FORMATS,
    detect_format,
    extension_matches_format,
)
from guitarriff.config import Settings
from guitarriff.errors import (
    FileTooLargeError,
    InvalidFileIdError,
    NotFoundError,
    UnsupportedFileTypeError,
)

_META_FILENAME = "meta.json"
_STORED_FILENAME_PREFIX = "source"

# Un nom de fichier d'origine ne sert qu'à l'affichage : on le limite en
# longueur et on retire tout ce qui pourrait ressembler à un chemin ou à un
# caractère de contrôle avant de le stocker dans les métadonnées.
_DISPLAY_NAME_MAX_LENGTH = 200
_UNSAFE_DISPLAY_CHARS = re.compile(r"[\x00-\x1f/\\]")


@dataclass(frozen=True)
class StoredAudioFile:
    file_id: str
    original_filename: str
    format: str
    content_type: str
    size_bytes: int
    uploaded_at: str
    status: str = "stored"
    # Origine du fichier : "upload" (Étape 4) ou "youtube" (Étape 5).
    source: str = "upload"
    source_url: str | None = None
    title: str | None = None

    @property
    def stored_filename(self) -> str:
        return f"{_STORED_FILENAME_PREFIX}.{self.format}"


def _sanitize_display_name(filename: str) -> str:
    name = _UNSAFE_DISPLAY_CHARS.sub("_", filename).strip()
    if not name:
        return "fichier"
    return name[:_DISPLAY_NAME_MAX_LENGTH]


def _validate_file_id(file_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(file_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidFileIdError(
            "Identifiant de fichier invalide.", details={"file_id": file_id}
        ) from exc


class AudioFileStorage:
    """Gère l'écriture, la lecture des métadonnées et la suppression des
    fichiers audio importés, sous `settings.uploads_dir`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = settings.uploads_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def _dir_for(self, file_id: uuid.UUID) -> Path:
        # `file_id` est garanti être un UUID valide à ce stade (voir
        # `_validate_file_id`) : c'est ce qui rend ce chemin sûr même s'il
        # est dérivé d'une entrée utilisateur.
        return self._root / str(file_id)

    def save(
        self,
        *,
        filename: str,
        declared_content_type: str,
        content: bytes,
        source: str = "upload",
        source_url: str | None = None,
        title: str | None = None,
    ) -> StoredAudioFile:
        """Valide et stocke un fichier audio. Lève une `AppError` (voir
        `errors.py`) si le format n'est pas supporté ou si la taille dépasse
        la limite configurée."""

        max_size = self._settings.max_upload_size_bytes
        if len(content) > max_size:
            raise FileTooLargeError(
                "Le fichier dépasse la taille maximale autorisée.",
                details={
                    "max_size_bytes": max_size,
                    "received_size_bytes": len(content),
                },
            )

        header = content[:SNIFF_SIZE]
        detected = detect_format(header)
        if detected is None:
            raise UnsupportedFileTypeError(
                "Ce fichier n'est reconnu comme aucun format audio supporté.",
                details={"supported_formats": _supported_format_keys()},
            )

        declared_extension = Path(filename).suffix.lower()
        if declared_extension and not extension_matches_format(declared_extension, detected):
            raise UnsupportedFileTypeError(
                "L'extension du fichier ne correspond pas à son contenu réel.",
                details={
                    "declared_extension": declared_extension,
                    "detected_format": detected.key,
                },
            )

        file_id = uuid.uuid4()
        record = StoredAudioFile(
            file_id=str(file_id),
            original_filename=_sanitize_display_name(filename),
            format=detected.key,
            content_type=detected.content_type,
            size_bytes=len(content),
            uploaded_at=datetime.now(UTC).isoformat(),
            source=source,
            source_url=source_url,
            title=title,
        )

        target_dir = self._dir_for(file_id)
        target_dir.mkdir(parents=True, exist_ok=False)
        (target_dir / record.stored_filename).write_bytes(content)
        (target_dir / _META_FILENAME).write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return record

    def get(self, file_id: str) -> StoredAudioFile:
        validated_id = _validate_file_id(file_id)
        meta_path = self._dir_for(validated_id) / _META_FILENAME
        if not meta_path.is_file():
            raise NotFoundError(
                "Aucun fichier audio ne correspond à cet identifiant.",
                details={"file_id": file_id},
            )
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return StoredAudioFile(**data)

    def delete(self, file_id: str) -> None:
        validated_id = _validate_file_id(file_id)
        target_dir = self._dir_for(validated_id)
        if not target_dir.is_dir():
            raise NotFoundError(
                "Aucun fichier audio ne correspond à cet identifiant.",
                details={"file_id": file_id},
            )
        shutil.rmtree(target_dir)

    def purge_all(self) -> int:
        """Supprime tous les fichiers importés. Utilitaire de nettoyage —
        non exposé via l'API à ce stade, prévu pour un futur usage manuel ou
        planifié (voir docs/API.md, section fichiers audio)."""

        count = 0
        if self._root.is_dir():
            for entry in self._root.iterdir():
                if entry.is_dir():
                    shutil.rmtree(entry)
                    count += 1
        return count


def _supported_format_keys() -> list[str]:
    return [fmt.key for fmt in SUPPORTED_FORMATS]
