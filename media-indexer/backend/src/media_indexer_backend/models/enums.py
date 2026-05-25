from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    MOUNTED_FS = "mounted_fs"
    SMB = "smb"
    NFS = "nfs"
    AGENT = "agent"


class SourceStatus(StrEnum):
    READY = "ready"
    SCANNING = "scanning"
    ERROR = "error"
    DISABLED = "disabled"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    UNKNOWN = "unknown"


class MatchType(StrEnum):
    DUPLICATE = "duplicate"
    SEMANTIC = "semantic"
    TAG = "tag"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAVORITE = "favorite"


class UserRole(StrEnum):
    ADMIN = "admin"
    CURATOR = "curator"
    GUEST = "guest"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"
    BANNED = "banned"
