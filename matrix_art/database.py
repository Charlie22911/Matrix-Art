from __future__ import annotations

from base64 import b64decode, b64encode
import hashlib
import mimetypes
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import RLock

from PIL import Image

from .artwork.processor import image_to_png_bytes
from .config import ImageConfig

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_folder_path(folder_path: str | None, *, default: str = "") -> str:
    """Return a safe, UI-facing folder path such as 'Uploads/Favorites'."""
    raw = (folder_path or default or "").replace("\\", "/").strip()
    if raw in {"", "/", "."}:
        return ""
    parts: list[str] = []
    for part in raw.split("/"):
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        # Keep names readable, but avoid path separators/control characters.
        part = "".join(ch for ch in part if ch not in "\x00\r\n\t")[:64].strip()
        if part:
            parts.append(part)
    return "/".join(parts[:6])


def normalize_source_path(rel_path: str | Path) -> str:
    """Return a safe, slash-separated source path for optional future imports."""
    rel = str(rel_path).replace("\\", "/").lstrip("/").strip()
    while rel.startswith("./"):
        rel = rel[2:]
    parts = [p.strip() for p in rel.split("/") if p.strip() and p not in {".", ".."}]
    clean_parts: list[str] = []
    for part in parts:
        clean = "".join(ch for ch in part if ch not in "\x00\r\n\t")[:128].strip()
        if clean:
            clean_parts.append(clean)
    return "/".join(clean_parts)


def folder_from_source_path(source_path: str | None, *, fallback: str = "") -> str:
    if not source_path:
        return normalize_folder_path(fallback)
    parts = normalize_source_path(source_path).split("/")
    if len(parts) <= 1:
        return normalize_folder_path(fallback)
    return normalize_folder_path("/".join(parts[:-1]), default=fallback)


@dataclass(slots=True)
class ArtworkRow:
    id: int
    title: str
    kind: str
    enabled: bool
    folder_path: str
    source_path: str | None
    source_mime: str | None
    checksum: str | None
    created_at: str
    updated_at: str
    frame_count: int = 1


@dataclass(slots=True)
class DemoRow:
    id: int
    slug: str
    title: str
    description: str
    code: str
    enabled: bool
    builtin: bool
    default_fps: int
    created_at: str
    updated_at: str


BACKUP_FORMAT = "matrix-art-database-backup"
BACKUP_VERSION = 1
BACKUP_TABLES = (
    "artwork",
    "artwork_settings",
    "frames",
    "folders",
    "settings",
    "demos",
    "demo_versions",
)
BACKUP_EXCLUDED_SETTINGS = {
    "settings_pin_hash",
    "settings_pin_salt",
    "settings_pin_iterations",
    "flask_secret_key",
}
BACKUP_BLOB_MARKER = "__matrix_art_blob_b64__"


def _backup_encode_value(value: object) -> object:
    if isinstance(value, bytes):
        return {BACKUP_BLOB_MARKER: b64encode(value).decode("ascii")}
    return value


def _backup_decode_value(value: object) -> object:
    if isinstance(value, dict) and set(value.keys()) == {BACKUP_BLOB_MARKER}:
        raw = value.get(BACKUP_BLOB_MARKER)
        if not isinstance(raw, str):
            raise ValueError("invalid blob value in backup")
        return b64decode(raw.encode("ascii"), validate=True)
    return value


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        self.init_schema()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def init_schema(self) -> None:
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS artwork (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'image',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    folder_path TEXT NOT NULL DEFAULT '',
                    deleted INTEGER NOT NULL DEFAULT 0,
                    previous_folder_path TEXT,
                    previous_enabled INTEGER,
                    code_demo_id INTEGER,
                    source_path TEXT UNIQUE,
                    source_mime TEXT,
                    checksum TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artwork_settings (
                    artwork_id INTEGER PRIMARY KEY,
                    crop_x REAL,
                    crop_y REAL,
                    crop_w REAL,
                    crop_h REAL,
                    scale_mode TEXT,
                    resample_mode TEXT,
                    background_color TEXT,
                    FOREIGN KEY (artwork_id) REFERENCES artwork(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY,
                    artwork_id INTEGER NOT NULL,
                    frame_index INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    width INTEGER NOT NULL DEFAULT 64,
                    height INTEGER NOT NULL DEFAULT 64,
                    image_png BLOB NOT NULL,
                    FOREIGN KEY (artwork_id) REFERENCES artwork(id) ON DELETE CASCADE,
                    UNIQUE (artwork_id, frame_index)
                );

                CREATE TABLE IF NOT EXISTS folders (
                    path TEXT PRIMARY KEY,
                    protected INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS demos (
                    id INTEGER PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    code TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    builtin INTEGER NOT NULL DEFAULT 0,
                    default_fps INTEGER NOT NULL DEFAULT 24,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS demo_versions (
                    id INTEGER PRIMARY KEY,
                    demo_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (demo_id) REFERENCES demos(id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_column("artwork", "folder_path", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("artwork", "deleted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("artwork", "previous_folder_path", "TEXT")
            self._ensure_column("artwork", "previous_enabled", "INTEGER")
            self._ensure_column("artwork", "code_demo_id", "INTEGER")
            self._ensure_column("folders", "protected", "INTEGER NOT NULL DEFAULT 0")
            self.conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_artwork_enabled ON artwork(enabled) WHERE deleted=0;
                CREATE INDEX IF NOT EXISTS idx_artwork_folder ON artwork(folder_path) WHERE deleted=0;
                CREATE INDEX IF NOT EXISTS idx_artwork_deleted ON artwork(deleted);
                CREATE INDEX IF NOT EXISTS idx_artwork_sort ON artwork(LOWER(COALESCE(source_path, title))) WHERE deleted=0;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_artwork_code_demo_id ON artwork(code_demo_id) WHERE code_demo_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_frames_artwork ON frames(artwork_id, frame_index);
                CREATE INDEX IF NOT EXISTS idx_folders_sort ON folders(LOWER(path));
                CREATE INDEX IF NOT EXISTS idx_demos_enabled ON demos(enabled);
                CREATE INDEX IF NOT EXISTS idx_demos_sort ON demos(LOWER(title));
                """
            )
            self._backfill_folders_locked()
            self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column not in {str(row["name"]) for row in rows}:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_folder_locked(self, folder_path: str | None) -> str:
        folder = normalize_folder_path(folder_path)
        if not folder or folder.lower() == "trash":
            return folder
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO folders(path, protected, created_at, updated_at) VALUES (?, 0, ?, ?)
            ON CONFLICT(path) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (folder, now, now),
        )
        return folder

    def _backfill_folders_locked(self) -> None:
        rows = self.conn.execute(
            """
            SELECT DISTINCT folder_path FROM artwork
            WHERE COALESCE(folder_path, '')<>'' AND LOWER(folder_path)<>'trash'
            """
        ).fetchall()
        for row in rows:
            folder = normalize_folder_path(row["folder_path"])
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))

    def create_folder(self, folder_path: str) -> dict[str, object]:
        folder = normalize_folder_path(folder_path)
        if not folder:
            raise ValueError("folder name is empty")
        if folder.lower() in {"trash", "unfiled"}:
            raise ValueError(f"{folder} is reserved")
        with self.lock:
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))
            self.conn.commit()
        return {
            "path": folder,
            "name": folder.split("/")[-1],
            "depth": folder.count("/"),
            "direct_count": 0,
            "count": 0,
            "trash": False,
            "protected": False,
            "virtual": False,
        }

    def set_setting(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, utc_now()),
            )
            self.conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def export_backup_payload(self) -> dict[str, object]:
        """Return a portable JSON-safe backup of Matrix-Art runtime data.

        Settings PIN hashes/salts and the Flask session secret are intentionally
        omitted so restored backups do not copy the Settings PIN to another
        install or overwrite the current install's PIN.
        """
        payload: dict[str, object] = {
            "format": BACKUP_FORMAT,
            "format_version": BACKUP_VERSION,
            "created_at": utc_now(),
            "excluded_settings": sorted(BACKUP_EXCLUDED_SETTINGS),
            "tables": {},
        }
        tables: dict[str, object] = {}
        with self.lock:
            for table in BACKUP_TABLES:
                table_info = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
                columns = [str(row["name"]) for row in table_info]
                if not columns:
                    continue
                rows_out: list[dict[str, object]] = []
                for row in self.conn.execute(f"SELECT * FROM {table}").fetchall():
                    if table == "settings" and str(row["key"]) in BACKUP_EXCLUDED_SETTINGS:
                        continue
                    rows_out.append({column: _backup_encode_value(row[column]) for column in columns})
                tables[table] = {"columns": columns, "rows": rows_out}
        payload["tables"] = tables
        return payload

    def import_backup_payload(self, payload: dict[str, object]) -> dict[str, object]:
        """Replace database contents from a Matrix-Art backup payload.

        The current Settings PIN and Flask session secret are preserved even if
        the uploaded backup contains those setting keys.
        """
        if not isinstance(payload, dict):
            raise ValueError("backup is not a JSON object")
        if payload.get("format") != BACKUP_FORMAT:
            raise ValueError("backup format is not recognized")
        try:
            version = int(payload.get("format_version", 0))
        except Exception as exc:
            raise ValueError("backup version is invalid") from exc
        if version != BACKUP_VERSION:
            raise ValueError(f"backup version {version} is not supported")
        tables = payload.get("tables")
        if not isinstance(tables, dict):
            raise ValueError("backup does not contain table data")

        restored_rows = 0
        preserved_settings: dict[str, str] = {}
        with self.lock:
            for key in BACKUP_EXCLUDED_SETTINGS:
                row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                if row is not None:
                    preserved_settings[key] = str(row["value"])

            try:
                self.conn.execute("PRAGMA foreign_keys=OFF")
                self.conn.execute("BEGIN IMMEDIATE")

                for table in reversed(BACKUP_TABLES):
                    self.conn.execute(f"DELETE FROM {table}")

                for table in BACKUP_TABLES:
                    table_payload = tables.get(table, {})
                    if not isinstance(table_payload, dict):
                        continue
                    backup_columns = table_payload.get("columns")
                    backup_rows = table_payload.get("rows")
                    if not isinstance(backup_columns, list) or not isinstance(backup_rows, list):
                        continue

                    existing_columns = {
                        str(row["name"])
                        for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
                    }
                    columns = [str(column) for column in backup_columns if str(column) in existing_columns]
                    if not columns:
                        continue

                    placeholders = ", ".join("?" for _ in columns)
                    quoted_columns = ", ".join(f'"{column}"' for column in columns)
                    sql = f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'

                    for row in backup_rows:
                        if not isinstance(row, dict):
                            continue
                        if table == "settings" and str(row.get("key", "")) in BACKUP_EXCLUDED_SETTINGS:
                            continue
                        values = [_backup_decode_value(row.get(column)) for column in columns]
                        self.conn.execute(sql, values)
                        restored_rows += 1

                now = utc_now()
                for key, value in preserved_settings.items():
                    self.conn.execute(
                        """
                        INSERT INTO settings(key, value, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                        """,
                        (key, value, now),
                    )

                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self.conn.execute("PRAGMA foreign_keys=ON")

            self.init_schema()

        return {"format_version": version, "restored_rows": restored_rows, "preserved_settings": sorted(preserved_settings)}

    def count_artwork(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT COUNT(*) AS c FROM artwork WHERE deleted=0").fetchone()["c"])

    def count_enabled(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT COUNT(*) AS c FROM artwork WHERE enabled=1 AND deleted=0").fetchone()["c"])

    def add_panel_frame(
        self,
        panel_png_bytes: bytes,
        title: str,
        image_config: ImageConfig,
        *,
        kind: str = "upload",
        enabled: bool = True,
        folder_path: str = "Uploads",
        settings_label: str = "browser-preview",
    ) -> ArtworkRow:
        """Store a browser-rendered, panel-ready 64x64 PNG frame as artwork."""
        title = title.strip() or ("Drawing" if kind == "drawing" else "Uploaded image")
        kind = (kind or "upload").strip().lower()
        if kind not in {"upload", "drawing", "image", "generated", "gif", "code"}:
            kind = "upload"
        folder = normalize_folder_path(folder_path, default="Drawings" if kind == "drawing" else "Uploads")

        with Image.open(BytesIO(panel_png_bytes)) as img:
            img.load()
            if img.size != (image_config.target_width, image_config.target_height):
                raise ValueError(f"panel frame must be {image_config.target_width}x{image_config.target_height}")
            frame = img.convert("RGB")
        png_bytes = image_to_png_bytes(frame)
        checksum = self._sha256_bytes(png_bytes)
        now = utc_now()

        with self.lock:
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))
            cur = self.conn.execute(
                """
                INSERT INTO artwork(
                    title, kind, enabled, folder_path, deleted,
                    source_path, source_mime, checksum, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, NULL, 'image/png', ?, ?, ?)
                """,
                (title, kind, 1 if enabled else 0, folder, checksum, now, now),
            )
            artwork_id = int(cur.lastrowid)
            self.conn.execute(
                """
                INSERT INTO frames(artwork_id, frame_index, duration_ms, width, height, image_png)
                VALUES (?, 0, 0, ?, ?, ?)
                """,
                (artwork_id, image_config.target_width, image_config.target_height, png_bytes),
            )
            self.conn.execute(
                """
                INSERT INTO artwork_settings(
                    artwork_id, crop_x, crop_y, crop_w, crop_h, scale_mode, resample_mode, background_color
                ) VALUES (?, NULL, NULL, NULL, NULL, ?, ?, NULL)
                """,
                (artwork_id, settings_label, settings_label),
            )
            self.conn.commit()
        row = self.get_artwork(artwork_id)
        if row is None:
            raise RuntimeError("artwork was saved but could not be read back")
        return row

    def add_uploaded_frame(
        self,
        panel_png_bytes: bytes,
        title: str,
        image_config: ImageConfig,
        enabled: bool = True,
        folder_path: str = "Uploads",
    ) -> ArtworkRow:
        return self.add_panel_frame(
            panel_png_bytes,
            title,
            image_config,
            kind="upload",
            enabled=enabled,
            folder_path=folder_path,
            settings_label="browser-preview",
        )

    def add_drawing_frame(
        self,
        panel_png_bytes: bytes,
        title: str,
        image_config: ImageConfig,
        enabled: bool = True,
        folder_path: str = "Drawings",
    ) -> ArtworkRow:
        return self.add_panel_frame(
            panel_png_bytes,
            title,
            image_config,
            kind="drawing",
            enabled=enabled,
            folder_path=folder_path,
            settings_label="browser-drawing",
        )

    def add_animation_frames(
        self,
        frames: list[tuple[bytes, int]],
        title: str,
        image_config: ImageConfig,
        *,
        kind: str = "gif",
        enabled: bool = True,
        folder_path: str = "Animations",
        source_path: str | None = None,
        source_mime: str = "image/gif",
        checksum: str | None = None,
        settings_label: str = "animated-gif",
    ) -> ArtworkRow:
        """Store one animated artwork as multiple panel-ready 64x64 PNG frames."""
        if not frames:
            raise ValueError("animation had no frames")
        title = title.strip() or "Animated GIF"
        folder = normalize_folder_path(folder_path, default="Animations")
        now = utc_now()
        normalized: list[tuple[bytes, int]] = []
        for raw_png, duration_ms in frames:
            with Image.open(BytesIO(raw_png)) as img:
                img.load()
                if img.size != (image_config.target_width, image_config.target_height):
                    raise ValueError(f"animation frame must be {image_config.target_width}x{image_config.target_height}")
                normalized.append((image_to_png_bytes(img.convert("RGB")), max(20, min(5000, int(duration_ms or 100)))))
        if checksum is None:
            h = hashlib.sha256()
            for png, duration in normalized:
                h.update(duration.to_bytes(4, "big", signed=False))
                h.update(png)
            checksum = h.hexdigest()

        with self.lock:
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))

            artwork_id: int
            existing = None
            if source_path:
                existing = self.conn.execute("SELECT id, deleted FROM artwork WHERE source_path=?", (source_path,)).fetchone()
            if existing and int(existing["deleted"]):
                raise ValueError("animation was previously deleted from imported source")
            if existing:
                artwork_id = int(existing["id"])
                self.conn.execute(
                    """
                    UPDATE artwork
                    SET title=?, kind=?, enabled=?, folder_path=?, deleted=0, source_mime=?,
                        checksum=?, updated_at=?
                    WHERE id=?
                    """,
                    (title, kind, 1 if enabled else 0, folder, source_mime, checksum, now, artwork_id),
                )
                self.conn.execute("DELETE FROM frames WHERE artwork_id=?", (artwork_id,))
            else:
                cur = self.conn.execute(
                    """
                    INSERT INTO artwork(
                        title, kind, enabled, folder_path, deleted,
                        source_path, source_mime, checksum, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (title, kind, 1 if enabled else 0, folder, source_path, source_mime, checksum, now, now),
                )
                artwork_id = int(cur.lastrowid)

            for index, (png, duration_ms) in enumerate(normalized):
                self.conn.execute(
                    """
                    INSERT INTO frames(artwork_id, frame_index, duration_ms, width, height, image_png)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (artwork_id, index, duration_ms, image_config.target_width, image_config.target_height, png),
                )
            self.conn.execute(
                """
                INSERT INTO artwork_settings(artwork_id, scale_mode, resample_mode, background_color)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(artwork_id) DO UPDATE SET
                    scale_mode=excluded.scale_mode,
                    resample_mode=excluded.resample_mode,
                    background_color=excluded.background_color
                """,
                (artwork_id, settings_label, settings_label, image_config.background_color),
            )
            self.conn.commit()
        row = self.get_artwork(artwork_id)
        if row is None:
            raise RuntimeError("animation was saved but could not be read back")
        return row

    def list_artwork(
        self,
        q: str = "",
        enabled: str = "all",
        folder: str = "all",
        limit: int = 500,
        offset: int = 0,
    ) -> list[ArtworkRow]:
        folder_norm = normalize_folder_path(folder)
        viewing_trash = folder_norm.lower() == "trash"
        where = ["deleted=1"] if viewing_trash else ["deleted=0"]
        params: list[object] = []
        if q:
            where.append("(title LIKE ? OR source_path LIKE ? OR folder_path LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if enabled == "yes":
            where.append("enabled=1")
        elif enabled == "no":
            where.append("enabled=0")
        if not viewing_trash:
            if folder == "unfiled":
                where.append("COALESCE(folder_path, '')=''")
            elif folder_norm and folder != "all":
                where.append("(folder_path=? OR folder_path LIKE ?)")
                params.extend([folder_norm, f"{folder_norm}/%"])
        sql_where = " WHERE " + " AND ".join(where)
        with self.lock:
            rows = self.conn.execute(
                f"""
                SELECT a.*,
                       (SELECT COUNT(*) FROM frames f WHERE f.artwork_id=a.id) AS frame_count
                FROM artwork a
                {sql_where}
                ORDER BY LOWER(COALESCE(NULLIF(folder_path, ''), 'zzzz')), LOWER(title)
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_artwork(row) for row in rows]

    def list_enabled_artwork(self, limit: int = 5000) -> list[ArtworkRow]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT a.*,
                       (SELECT COUNT(*) FROM frames f WHERE f.artwork_id=a.id) AS frame_count
                FROM artwork a
                WHERE enabled=1 AND deleted=0
                ORDER BY LOWER(COALESCE(NULLIF(folder_path, ''), 'zzzz')), LOWER(title)
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_artwork(row) for row in rows]

    def list_folders(self) -> list[dict[str, object]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT folder_path, COUNT(*) AS direct_count
                FROM artwork
                WHERE deleted=0 AND COALESCE(folder_path, '')<>''
                GROUP BY folder_path
                ORDER BY LOWER(folder_path)
                """
            ).fetchall()
            folder_rows = self.conn.execute("SELECT path, protected FROM folders ORDER BY LOWER(path)").fetchall()
            trash_count = int(self.conn.execute("SELECT COUNT(*) AS c FROM artwork WHERE deleted=1").fetchone()["c"])
        direct_counts = {str(row["folder_path"]): int(row["direct_count"]) for row in rows}
        protected_map: dict[str, bool] = {
            normalize_folder_path(row["path"]): bool(row["protected"])
            for row in folder_rows
            if normalize_folder_path(row["path"])
        }
        all_paths: set[str] = set(protected_map)
        for folder in direct_counts:
            if folder.lower() == "trash":
                continue
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                path = "/".join(parts[:i])
                if path.lower() != "trash":
                    all_paths.add(path)
        result: list[dict[str, object]] = []
        for path in sorted(all_paths, key=str.lower):
            recursive = sum(
                count
                for folder, count in direct_counts.items()
                if folder.lower() != "trash" and (folder == path or folder.startswith(path + "/"))
            )
            result.append({
                "path": path,
                "name": path.split("/")[-1],
                "depth": path.count("/"),
                "direct_count": direct_counts.get(path, 0),
                "count": recursive,
                "trash": False,
                "protected": bool(protected_map.get(path, False)),
                "virtual": False,
            })
        # Always expose Trash as a selectable folder so the user can recover or destroy items.
        result.append({
            "path": "Trash",
            "name": "Trash",
            "depth": 0,
            "direct_count": trash_count,
            "count": trash_count,
            "trash": True,
            "protected": True,
            "virtual": True,
        })
        return result

    def list_folders_for_settings(self) -> list[dict[str, object]]:
        with self.lock:
            unfiled_count = int(
                self.conn.execute(
                    "SELECT COUNT(*) AS c FROM artwork WHERE deleted=0 AND COALESCE(folder_path, '')=''"
                ).fetchone()["c"]
            )
        folders = self.list_folders()
        return [
            {
                "path": "Unfiled",
                "name": "Unfiled",
                "depth": 0,
                "direct_count": unfiled_count,
                "count": unfiled_count,
                "trash": False,
                "protected": True,
                "virtual": True,
            },
            *folders,
        ]

    def _folder_delete_blockers_locked(self, folder: str) -> list[str]:
        rows = self.conn.execute("SELECT path FROM folders WHERE protected=1 ORDER BY LOWER(path)").fetchall()
        blockers: list[str] = []
        for row in rows:
            protected = normalize_folder_path(row["path"])
            if not protected:
                continue
            if protected == folder or protected.startswith(folder + "/") or folder.startswith(protected + "/"):
                blockers.append(protected)
        return blockers

    def delete_folder(self, folder_path: str) -> dict[str, object]:
        folder = normalize_folder_path(folder_path)
        if not folder or folder.lower() in {"trash", "unfiled", "all"}:
            raise ValueError("That folder is protected and cannot be deleted.")
        with self.lock:
            blockers = self._folder_delete_blockers_locked(folder)
            if blockers:
                raise ValueError("Folder is protected: " + ", ".join(blockers[:4]))
            now = utc_now()
            moved = self.conn.execute(
                """
                UPDATE artwork
                SET folder_path='', updated_at=?
                WHERE deleted=0 AND (folder_path=? OR folder_path LIKE ?)
                """,
                (now, folder, folder + "/%"),
            ).rowcount
            self.conn.execute(
                """
                UPDATE artwork
                SET previous_folder_path='', updated_at=?
                WHERE deleted=1 AND (previous_folder_path=? OR previous_folder_path LIKE ?)
                """,
                (now, folder, folder + "/%"),
            )
            deleted_rows = self.conn.execute(
                "DELETE FROM folders WHERE path=? OR path LIKE ?",
                (folder, folder + "/%"),
            ).rowcount
            self.conn.commit()
        return {"path": folder, "moved_count": int(moved or 0), "deleted_folder_count": int(deleted_rows or 0)}

    def set_folder_protected(self, folder_path: str, protected: bool) -> dict[str, object]:
        folder = normalize_folder_path(folder_path)
        if not folder or folder.lower() in {"trash", "unfiled", "all"}:
            return {"path": "Unfiled" if not folder or folder.lower() == "unfiled" else "Trash", "protected": True, "virtual": True}
        with self.lock:
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))
            self.conn.execute(
                "UPDATE folders SET protected=?, updated_at=? WHERE path=?",
                (1 if protected else 0, utc_now(), folder),
            )
            self.conn.commit()
        return {"path": folder, "protected": bool(protected), "virtual": False}

    def get_artwork(self, artwork_id: int, *, include_deleted: bool = False) -> ArtworkRow | None:
        deleted_clause = "" if include_deleted else "AND a.deleted=0"
        with self.lock:
            row = self.conn.execute(
                f"""
                SELECT a.*,
                       (SELECT COUNT(*) FROM frames f WHERE f.artwork_id=a.id) AS frame_count
                FROM artwork a WHERE a.id=? {deleted_clause}
                """,
                (artwork_id,),
            ).fetchone()
        return self._row_to_artwork(row) if row else None

    def get_first_enabled(self) -> ArtworkRow | None:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT a.*,
                       (SELECT COUNT(*) FROM frames f WHERE f.artwork_id=a.id) AS frame_count
                FROM artwork a
                WHERE enabled=1 AND deleted=0
                ORDER BY LOWER(COALESCE(NULLIF(folder_path, ''), 'zzzz')), LOWER(title)
                LIMIT 1
                """
            ).fetchone()
        return self._row_to_artwork(row) if row else None

    def set_enabled(self, artwork_id: int, enabled: bool) -> None:
        with self.lock:
            now = utc_now()
            self.conn.execute(
                "UPDATE artwork SET enabled=?, updated_at=? WHERE id=? AND deleted=0",
                (1 if enabled else 0, now, artwork_id),
            )
            self.conn.execute(
                "UPDATE demos SET enabled=?, updated_at=? WHERE id=(SELECT code_demo_id FROM artwork WHERE id=? AND kind='code')",
                (1 if enabled else 0, now, artwork_id),
            )
            self.conn.commit()

    def rename_artwork(self, artwork_id: int, title: str) -> ArtworkRow | None:
        title = (title or "").strip()
        if not title:
            raise ValueError("title cannot be empty")
        title = title[:120]
        with self.lock:
            row = self.conn.execute(
                "SELECT id, kind, code_demo_id, deleted FROM artwork WHERE id=?",
                (int(artwork_id),),
            ).fetchone()
            if not row:
                return None
            now = utc_now()
            self.conn.execute(
                "UPDATE artwork SET title=?, updated_at=? WHERE id=?",
                (title, now, int(artwork_id)),
            )
            if str(row["kind"] or "") == "code" and row["code_demo_id"] is not None:
                self.conn.execute(
                    "UPDATE demos SET title=?, updated_at=? WHERE id=?",
                    (title, now, int(row["code_demo_id"])),
                )
                demo_row = self.conn.execute("SELECT slug, builtin FROM demos WHERE id=?", (int(row["code_demo_id"]),)).fetchone()
                if demo_row and int(demo_row["builtin"] or 0):
                    self.conn.execute(
                        """
                        INSERT INTO settings(key, value, updated_at)
                        VALUES (?, '1', ?)
                        ON CONFLICT(key) DO UPDATE SET value='1', updated_at=excluded.updated_at
                        """,
                        (f"customized_builtin_demo:{demo_row['slug']}", now),
                    )
            self.conn.commit()
        return self.get_artwork(int(artwork_id), include_deleted=True)

    def set_folder(self, artwork_id: int, folder_path: str) -> ArtworkRow | None:
        folder = normalize_folder_path(folder_path)
        if folder.lower() in {"trash", "unfiled"}:
            folder = ""
        with self.lock:
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))
            self.conn.execute(
                "UPDATE artwork SET folder_path=?, updated_at=? WHERE id=? AND deleted=0",
                (folder, utc_now(), artwork_id),
            )
            self.conn.commit()
        return self.get_artwork(artwork_id)

    def move_artworks(self, artwork_ids: list[int], folder_path: str) -> list[ArtworkRow]:
        ids = sorted({int(x) for x in artwork_ids if int(x) > 0})
        if not ids:
            return []
        folder = normalize_folder_path(folder_path)
        if folder.lower() in {"trash", "unfiled"}:
            folder = ""
        moved: list[ArtworkRow] = []
        with self.lock:
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))
            now = utc_now()
            for artwork_id in ids:
                row = self.get_artwork(artwork_id)
                if row is None:
                    continue
                self.conn.execute(
                    "UPDATE artwork SET folder_path=?, updated_at=? WHERE id=? AND deleted=0",
                    (folder, now, artwork_id),
                )
                moved.append(row)
            self.conn.commit()
        return [self.get_artwork(row.id) or row for row in moved]

    def _folder_filter_sql(self, folder: str) -> tuple[str, list[object]]:
        folder_norm = normalize_folder_path(folder)
        if folder_norm.lower() == "trash":
            raise ValueError("Trash items must be recovered before they can be changed.")
        if str(folder or "").strip().lower() == "unfiled":
            return "deleted=0 AND COALESCE(folder_path, '')=''", []
        if folder_norm and str(folder or "").strip().lower() != "all":
            return "deleted=0 AND (folder_path=? OR folder_path LIKE ?)", [folder_norm, f"{folder_norm}/%"]
        return "deleted=0", []

    def folder_enabled_summary(self, folder: str = "all") -> dict[str, int]:
        where, params = self._folder_filter_sql(folder)
        with self.lock:
            row = self.conn.execute(
                f"SELECT COUNT(*) AS total, SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) AS enabled FROM artwork WHERE {where}",
                params,
            ).fetchone()
        total = int(row["total"] or 0) if row else 0
        enabled = int(row["enabled"] or 0) if row else 0
        return {"total": total, "enabled": enabled, "disabled": max(0, total - enabled)}

    def set_folder_enabled(self, folder: str, enabled: bool) -> dict[str, object]:
        where, params = self._folder_filter_sql(folder)
        with self.lock:
            now = utc_now()
            rows = self.conn.execute(f"SELECT id, code_demo_id FROM artwork WHERE {where}", params).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                self.conn.execute(
                    f"UPDATE artwork SET enabled=?, updated_at=? WHERE id IN ({placeholders})",
                    (1 if enabled else 0, now, *ids),
                )
                demo_ids = [int(row["code_demo_id"]) for row in rows if row["code_demo_id"] is not None]
                if demo_ids:
                    demo_placeholders = ",".join("?" for _ in demo_ids)
                    self.conn.execute(
                        f"UPDATE demos SET enabled=?, updated_at=? WHERE id IN ({demo_placeholders})",
                        (1 if enabled else 0, now, *demo_ids),
                    )
            self.conn.commit()
        summary = self.folder_enabled_summary(folder)
        return {"folder": normalize_folder_path(folder) or "all", "target_enabled": bool(enabled), "count": len(ids), **summary}

    def trash_artworks(self, artwork_ids: list[int]) -> list[ArtworkRow]:
        ids = sorted({int(x) for x in artwork_ids if int(x) > 0})
        if not ids:
            return []
        rows: list[ArtworkRow] = []
        with self.lock:
            for artwork_id in ids:
                row = self.get_artwork(artwork_id)
                if row is None:
                    continue
                now = utc_now()
                self.conn.execute(
                    """
                    UPDATE artwork
                    SET previous_folder_path=folder_path, previous_enabled=enabled,
                        folder_path='Trash', deleted=1, enabled=0, updated_at=?
                    WHERE id=? AND deleted=0
                    """,
                    (now, artwork_id),
                )
                if row.kind == "code":
                    self.conn.execute(
                        "UPDATE demos SET enabled=0, updated_at=? WHERE id=(SELECT code_demo_id FROM artwork WHERE id=?)",
                        (now, artwork_id),
                    )
                rows.append(row)
            self.conn.commit()
        return rows

    def recover_artworks(self, artwork_ids: list[int]) -> list[ArtworkRow]:
        ids = sorted({int(x) for x in artwork_ids if int(x) > 0})
        if not ids:
            return []
        recovered: list[ArtworkRow] = []
        with self.lock:
            for artwork_id in ids:
                row = self.get_artwork(artwork_id, include_deleted=True)
                if row is None:
                    continue
                now = utc_now()
                self.conn.execute(
                    """
                    UPDATE artwork
                    SET folder_path=COALESCE(NULLIF(previous_folder_path, ''), ''),
                        enabled=COALESCE(previous_enabled, 1),
                        deleted=0, previous_folder_path=NULL, previous_enabled=NULL, updated_at=?
                    WHERE id=? AND deleted=1
                    """,
                    (now, artwork_id),
                )
                if row.kind == "code":
                    self.conn.execute(
                        "UPDATE demos SET enabled=(SELECT enabled FROM artwork WHERE id=?), updated_at=? WHERE id=(SELECT code_demo_id FROM artwork WHERE id=?)",
                        (artwork_id, now, artwork_id),
                    )
                recovered_row = self.get_artwork(artwork_id)
                if recovered_row is not None:
                    recovered.append(recovered_row)
            self.conn.commit()
        return recovered

    def destroy_artworks(self, artwork_ids: list[int]) -> list[ArtworkRow]:
        ids = sorted({int(x) for x in artwork_ids if int(x) > 0})
        if not ids:
            return []
        destroyed: list[ArtworkRow] = []
        with self.lock:
            for artwork_id in ids:
                row = self.get_artwork(artwork_id, include_deleted=True)
                if row is None:
                    continue
                if row.kind == "code":
                    demo_row = self.conn.execute("SELECT * FROM demos WHERE id=(SELECT code_demo_id FROM artwork WHERE id=?)", (artwork_id,)).fetchone()
                    if demo_row and int(demo_row["builtin"]):
                        self.set_setting(f"deleted_builtin_demo:{demo_row['slug']}", "1")
                    if demo_row:
                        self.conn.execute("DELETE FROM demos WHERE id=?", (int(demo_row["id"]),))
                self.conn.execute("DELETE FROM frames WHERE artwork_id=?", (artwork_id,))
                self.conn.execute("DELETE FROM artwork_settings WHERE artwork_id=?", (artwork_id,))
                self.conn.execute("DELETE FROM artwork WHERE id=?", (artwork_id,))
                destroyed.append(row)
            self.conn.commit()
        return destroyed

    def delete_artwork(self, artwork_id: int) -> ArtworkRow | None:
        rows = self.trash_artworks([artwork_id])
        return rows[0] if rows else None


    def get_code_artwork_for_demo(self, demo_id: int, *, include_deleted: bool = False) -> ArtworkRow | None:
        deleted_clause = "" if include_deleted else "AND a.deleted=0"
        with self.lock:
            row = self.conn.execute(
                f"""
                SELECT a.*,
                       (SELECT COUNT(*) FROM frames f WHERE f.artwork_id=a.id) AS frame_count
                FROM artwork a
                WHERE a.kind='code' AND a.code_demo_id=? {deleted_clause}
                LIMIT 1
                """,
                (int(demo_id),),
            ).fetchone()
        return self._row_to_artwork(row) if row else None

    def get_demo_for_artwork(self, artwork_id: int):
        with self.lock:
            row = self.conn.execute(
                """
                SELECT d.*
                FROM demos d
                JOIN artwork a ON a.code_demo_id=d.id
                WHERE a.id=? AND a.kind='code' AND a.deleted=0
                LIMIT 1
                """,
                (int(artwork_id),),
            ).fetchone()
        return self._row_to_demo(row) if row else None

    def upsert_code_artwork(self, demo: DemoRow, thumbnail_png_bytes: bytes, image_config: ImageConfig, *, folder_path: str = "Code") -> ArtworkRow | None:
        """Mirror a saved Python code effect into the normal artwork library.

        Returns None when the code artwork exists in Trash, so startup refreshes
        do not resurrect code the user deliberately deleted.
        """
        existing_deleted = self.get_code_artwork_for_demo(demo.id, include_deleted=True)
        if existing_deleted is not None and existing_deleted.folder_path.lower() == "trash":
            return None
        folder = normalize_folder_path(folder_path, default="Code")
        with Image.open(BytesIO(thumbnail_png_bytes)) as img:
            img.load()
            if img.size != (image_config.target_width, image_config.target_height):
                raise ValueError(f"code thumbnail must be {image_config.target_width}x{image_config.target_height}")
            png_bytes = image_to_png_bytes(img.convert("RGB"))
        checksum = self._sha256_bytes((demo.code + "\n").encode("utf-8", errors="ignore") + png_bytes)
        now = utc_now()
        with self.lock:
            parts = folder.split("/") if folder else []
            for i in range(1, len(parts) + 1):
                self._ensure_folder_locked("/".join(parts[:i]))
            existing = self.conn.execute("SELECT id, deleted, folder_path FROM artwork WHERE code_demo_id=?", (demo.id,)).fetchone()
            if existing and int(existing["deleted"]):
                return None
            if existing:
                folder = normalize_folder_path(str(existing["folder_path"] or folder), default=folder)
                artwork_id = int(existing["id"])
                self.conn.execute(
                    """
                    UPDATE artwork
                    SET title=?, kind='code', enabled=?, folder_path=?, source_path=?, source_mime='text/x-python',
                        checksum=?, updated_at=?
                    WHERE id=?
                    """,
                    (demo.title, 1 if demo.enabled else 0, folder, f"code:{demo.slug}", checksum, now, artwork_id),
                )
                self.conn.execute("DELETE FROM frames WHERE artwork_id=?", (artwork_id,))
            else:
                cur = self.conn.execute(
                    """
                    INSERT INTO artwork(
                        title, kind, enabled, folder_path, deleted, code_demo_id,
                        source_path, source_mime, checksum, created_at, updated_at
                    ) VALUES (?, 'code', ?, ?, 0, ?, ?, 'text/x-python', ?, ?, ?)
                    """,
                    (demo.title, 1 if demo.enabled else 0, folder, demo.id, f"code:{demo.slug}", checksum, now, now),
                )
                artwork_id = int(cur.lastrowid)
            self.conn.execute(
                """
                INSERT INTO frames(artwork_id, frame_index, duration_ms, width, height, image_png)
                VALUES (?, 0, 0, ?, ?, ?)
                """,
                (artwork_id, image_config.target_width, image_config.target_height, png_bytes),
            )
            self.conn.commit()
        return self.get_code_artwork_for_demo(demo.id)

    def is_builtin_demo_deleted(self, slug: str) -> bool:
        return self.get_setting(f"deleted_builtin_demo:{slug}", "0").strip() == "1"

    def is_builtin_demo_customized(self, slug: str) -> bool:
        return self.get_setting(f"customized_builtin_demo:{slug}", "0").strip().lower() in {"1", "true", "yes", "on"}

    def get_frame_png(self, artwork_id: int, frame_index: int = 0, *, include_deleted: bool = True) -> bytes | None:
        deleted_clause = "" if include_deleted else "AND a.deleted=0"
        with self.lock:
            row = self.conn.execute(
                f"""
                SELECT f.image_png
                FROM frames f
                JOIN artwork a ON a.id=f.artwork_id
                WHERE f.artwork_id=? AND f.frame_index=? {deleted_clause}
                """,
                (artwork_id, frame_index),
            ).fetchone()
            return bytes(row["image_png"]) if row else None

    def get_frame_rows(self, artwork_id: int) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(
                """
                SELECT f.* FROM frames f
                JOIN artwork a ON a.id=f.artwork_id
                WHERE f.artwork_id=? AND a.deleted=0
                ORDER BY f.frame_index
                """,
                (artwork_id,),
            ).fetchall()

    def get_frame_sequence(self, artwork_id: int, *, include_deleted: bool = False) -> list[tuple[bytes, int]]:
        deleted_clause = "" if include_deleted else "AND a.deleted=0"
        with self.lock:
            rows = self.conn.execute(
                f"""
                SELECT f.image_png, f.duration_ms
                FROM frames f
                JOIN artwork a ON a.id=f.artwork_id
                WHERE f.artwork_id=? {deleted_clause}
                ORDER BY f.frame_index
                """,
                (artwork_id,),
            ).fetchall()
        return [(bytes(row["image_png"]), max(20, int(row["duration_ms"] or 100))) for row in rows]


    def upsert_demo(
        self,
        *,
        slug: str,
        title: str,
        description: str,
        code: str,
        default_fps: int = 24,
        builtin: bool = False,
    ) -> str:
        slug = (slug or "").strip().lower()
        if not slug:
            raise ValueError("demo slug is empty")
        title = title.strip() or slug
        description = description.strip()
        code = code.rstrip() + "\n"
        default_fps = max(1, min(1000, int(default_fps or 24)))
        now = utc_now()
        with self.lock:
            existing = self.conn.execute("SELECT id, code FROM demos WHERE slug=?", (slug,)).fetchone()
            if existing:
                old_code = str(existing["code"])
                self.conn.execute(
                    """
                    UPDATE demos
                    SET title=?, description=?, code=?, builtin=?, default_fps=?, updated_at=?
                    WHERE slug=?
                    """,
                    (title, description, code, 1 if builtin else 0, default_fps, now, slug),
                )
                if old_code != code:
                    self.conn.execute(
                        "INSERT INTO demo_versions(demo_id, code, note, created_at) VALUES (?, ?, ?, ?)",
                        (int(existing["id"]), old_code, "before builtin refresh" if builtin else "before update", now),
                    )
                self.conn.commit()
                return "updated"
            self.conn.execute(
                """
                INSERT INTO demos(slug, title, description, code, enabled, builtin, default_fps, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (slug, title, description, code, 1 if builtin else 0, default_fps, now, now),
            )
            self.conn.commit()
            return "inserted"

    def list_demos(self, *, enabled: str = "all", include_trashed: bool = False) -> list[DemoRow]:
        where: list[str] = []
        if enabled == "yes":
            where.append("d.enabled=1")
        elif enabled == "no":
            where.append("d.enabled=0")
        if not include_trashed:
            where.append("COALESCE(a.deleted, 0)=0")
        sql_where = " WHERE " + " AND ".join(where) if where else ""
        with self.lock:
            rows = self.conn.execute(
                f"""
                SELECT d.*
                FROM demos d
                LEFT JOIN artwork a ON a.code_demo_id=d.id AND a.kind='code'
                {sql_where}
                ORDER BY d.builtin DESC, LOWER(d.title)
                """
            ).fetchall()
            return [self._row_to_demo(row) for row in rows]

    def get_demo(self, demo_id: int) -> DemoRow | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM demos WHERE id=?", (int(demo_id),)).fetchone()
            return self._row_to_demo(row) if row else None

    def set_demo_enabled(self, demo_id: int, enabled: bool) -> None:
        with self.lock:
            now = utc_now()
            self.conn.execute(
                "UPDATE demos SET enabled=?, updated_at=? WHERE id=?",
                (1 if enabled else 0, now, int(demo_id)),
            )
            self.conn.execute(
                "UPDATE artwork SET enabled=?, updated_at=? WHERE kind='code' AND code_demo_id=? AND deleted=0",
                (1 if enabled else 0, now, int(demo_id)),
            )
            self.conn.commit()

    def _slug_base(self, title: str) -> str:
        raw = (title or "demo").strip().lower()
        chars: list[str] = []
        last_dash = False
        for ch in raw:
            if ch.isalnum():
                chars.append(ch)
                last_dash = False
            elif ch in {" ", "-", "_", ".", "/"}:
                if not last_dash:
                    chars.append("-")
                    last_dash = True
        slug = "".join(chars).strip("-")[:48]
        return slug or "demo"

    def _unique_demo_slug_locked(self, title: str, *, exclude_id: int | None = None) -> str:
        base = self._slug_base(title)
        slug = base
        suffix = 2
        while True:
            if exclude_id is None:
                row = self.conn.execute("SELECT id FROM demos WHERE slug=?", (slug,)).fetchone()
            else:
                row = self.conn.execute("SELECT id FROM demos WHERE slug=? AND id<>?", (slug, int(exclude_id))).fetchone()
            if not row:
                return slug
            suffix_text = f"-{suffix}"
            slug = f"{base[:48-len(suffix_text)]}{suffix_text}"
            suffix += 1

    def create_demo(
        self,
        *,
        title: str,
        description: str,
        code: str,
        default_fps: int = 24,
        enabled: bool = True,
    ) -> DemoRow:
        title = (title or "New Demo").strip() or "New Demo"
        description = (description or "").strip()
        code = (code or "").rstrip() + "\n"
        default_fps = max(1, min(1000, int(default_fps or 24)))
        now = utc_now()
        with self.lock:
            slug = self._unique_demo_slug_locked(title)
            cur = self.conn.execute(
                """
                INSERT INTO demos(slug, title, description, code, enabled, builtin, default_fps, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (slug, title, description, code, 1 if enabled else 0, default_fps, now, now),
            )
            demo_id = int(cur.lastrowid)
            self.conn.execute(
                "INSERT INTO demo_versions(demo_id, code, note, created_at) VALUES (?, ?, ?, ?)",
                (demo_id, code, "initial save", now),
            )
            self.conn.commit()
        demo = self.get_demo(demo_id)
        if demo is None:
            raise RuntimeError("demo create failed")
        return demo

    def update_demo(
        self,
        demo_id: int,
        *,
        title: str,
        description: str,
        code: str,
        default_fps: int = 24,
        enabled: bool = True,
    ) -> DemoRow:
        title = (title or "Demo").strip() or "Demo"
        description = (description or "").strip()
        code = (code or "").rstrip() + "\n"
        default_fps = max(1, min(1000, int(default_fps or 24)))
        now = utc_now()
        with self.lock:
            existing = self.conn.execute("SELECT * FROM demos WHERE id=?", (int(demo_id),)).fetchone()
            if not existing:
                raise ValueError("demo not found")

            old_code = str(existing["code"] or "")
            old_title = str(existing["title"] or "")
            old_description = str(existing["description"] or "")
            old_fps = int(existing["default_fps"] or 24)
            is_builtin = bool(existing["builtin"])

            # Built-in Code entries are editable now. Keep their original slug so
            # startup migration can identify them, then mark them customized so
            # future bundled refreshes do not overwrite the user's edits.
            if is_builtin:
                slug = str(existing["slug"] or self._slug_base(title))
            else:
                slug = self._unique_demo_slug_locked(title, exclude_id=int(demo_id))

            self.conn.execute(
                """
                UPDATE demos
                SET slug=?, title=?, description=?, code=?, enabled=?, default_fps=?, updated_at=?
                WHERE id=?
                """,
                (slug, title, description, code, 1 if enabled else 0, default_fps, now, int(demo_id)),
            )
            if old_code != code:
                self.conn.execute(
                    "INSERT INTO demo_versions(demo_id, code, note, created_at) VALUES (?, ?, ?, ?)",
                    (int(demo_id), old_code, "before editor save", now),
                )
            if is_builtin and (old_code != code or old_title != title or old_description != description or old_fps != default_fps):
                self.conn.execute(
                    """
                    INSERT INTO settings(key, value, updated_at)
                    VALUES (?, '1', ?)
                    ON CONFLICT(key) DO UPDATE SET value='1', updated_at=excluded.updated_at
                    """,
                    (f"customized_builtin_demo:{slug}", now),
                )
            self.conn.commit()
        demo = self.get_demo(int(demo_id))
        if demo is None:
            raise RuntimeError("demo update failed")
        return demo

    def duplicate_demo(
        self,
        demo_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        code: str | None = None,
        default_fps: int | None = None,
        enabled: bool = True,
    ) -> DemoRow:
        with self.lock:
            source = self.conn.execute("SELECT * FROM demos WHERE id=?", (int(demo_id),)).fetchone()
            if not source:
                raise ValueError("demo not found")
            copy_title = (title or f"{source['title']} copy").strip() or "Demo copy"
            copy_description = source["description"] if description is None else description
            copy_code = source["code"] if code is None else code
            copy_fps = int(source["default_fps"] or 24) if default_fps is None else int(default_fps)
        return self.create_demo(
            title=copy_title,
            description=str(copy_description or ""),
            code=str(copy_code or ""),
            default_fps=copy_fps,
            enabled=enabled,
        )

    def delete_demo(self, demo_id: int) -> DemoRow:
        with self.lock:
            row = self.conn.execute("SELECT * FROM demos WHERE id=?", (int(demo_id),)).fetchone()
            if not row:
                raise ValueError("demo not found")
            demo = self._row_to_demo(row)
            if demo.builtin:
                raise ValueError("built-in demos cannot be deleted")
            self.conn.execute("DELETE FROM demos WHERE id=?", (int(demo_id),))
            self.conn.commit()
            return demo

    def list_demo_versions(self, demo_id: int, *, limit: int = 12) -> list[dict[str, object]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT id, note, created_at, LENGTH(code) AS bytes
                FROM demo_versions
                WHERE demo_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(demo_id), max(1, int(limit))),
            ).fetchall()
            return [dict(row) for row in rows]

    def _row_to_demo(self, row: sqlite3.Row) -> DemoRow:
        return DemoRow(
            id=int(row["id"]),
            slug=str(row["slug"]),
            title=str(row["title"]),
            description=str(row["description"] or ""),
            code=str(row["code"] or ""),
            enabled=bool(row["enabled"]),
            builtin=bool(row["builtin"]),
            default_fps=int(row["default_fps"] or 24),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _row_to_artwork(self, row: sqlite3.Row) -> ArtworkRow:
        return ArtworkRow(
            id=int(row["id"]),
            title=str(row["title"]),
            kind=str(row["kind"]),
            enabled=bool(row["enabled"]),
            folder_path=str(row["folder_path"] or ""),
            source_path=row["source_path"],
            source_mime=row["source_mime"],
            checksum=row["checksum"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            frame_count=int(row["frame_count"] or 0),
        )

    def _sha256_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
