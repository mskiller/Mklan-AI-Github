from sqlmodel import SQLModel, Field, Column, String
from pgvector.sqlalchemy import Vector
from typing import Optional

class MovieProject(SQLModel, table=True):
    __tablename__ = "movie_projects"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    name: str
    scenario_text: str
    genre: str
    tone: str
    target_duration_s: int
    output_width: int
    output_height: int
    output_fps: int
    aspect_ratio: str
    workflow_version: int
    style_anchor_text: str
    model_settings_override_json: Optional[str] = None
    opening_image_prompt_text: str
    opening_image_relative_path: Optional[str] = None
    opening_image_original_filename: Optional[str] = None
    opening_image_mime_type: Optional[str] = None
    opening_image_size_bytes: int
    opening_image_uploaded_at: Optional[str] = None
    beat_board_status: str
    archived_at: Optional[str] = None
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class MovieStoryScene(SQLModel, table=True):
    __tablename__ = "movie_story_scenes"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    order_index: int
    title: str
    target_duration_s: int
    narrative_text: str
    duration_locked: int
    first_image_prompt_text: str
    first_image_relative_path: Optional[str] = None
    first_image_original_filename: Optional[str] = None
    first_image_mime_type: Optional[str] = None
    first_image_size_bytes: int
    first_image_uploaded_at: Optional[str] = None
    first_image_source: Optional[str] = None
    image_generation_status: str
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class MovieStoryBeat(SQLModel, table=True):
    __tablename__ = "movie_story_beats"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    act_index: int
    order_index: int
    title: str
    summary_text: str
    purpose_text: str
    source: str
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class MovieScene(SQLModel, table=True):
    __tablename__ = "movie_scenes"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    story_scene_id: Optional[str] = None
    order_index: int
    absolute_order: Optional[int] = None
    title: str
    target_duration_s: int
    narrative_text: str
    duration_locked: int
    prompt_text: str
    camera_direction: str
    action_direction: str
    wan_prompt_text: str
    uploaded_sequence_relative_path: Optional[str] = None
    uploaded_sequence_original_filename: Optional[str] = None
    uploaded_sequence_mime_type: Optional[str] = None
    uploaded_sequence_size_bytes: int
    uploaded_sequence_uploaded_at: Optional[str] = None
    approved_video_relative_path: Optional[str] = None
    approved_video_original_filename: Optional[str] = None
    approved_video_mime_type: Optional[str] = None
    approved_video_size_bytes: int
    approved_video_created_at: Optional[str] = None
    approved_video_source: Optional[str] = None
    input_frame_relative_path: Optional[str] = None
    input_frame_original_filename: Optional[str] = None
    input_frame_mime_type: Optional[str] = None
    input_frame_size_bytes: int
    input_frame_created_at: Optional[str] = None
    last_frame_relative_path: Optional[str] = None
    last_frame_original_filename: Optional[str] = None
    last_frame_mime_type: Optional[str] = None
    last_frame_size_bytes: int
    last_frame_created_at: Optional[str] = None
    trim_in_ms: int
    trim_out_ms: int
    include_in_assembly: int
    render_status: str
    approved_clip_id: Optional[str] = None
    created_at: str
    updated_at: str
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384)))

class MovieSceneImageVariant(SQLModel, table=True):
    __tablename__ = "movie_scene_image_variants"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    scene_id: str
    provider: str
    model_name: str
    seed: Optional[int] = None
    prompt_text: str
    relative_path: str
    original_filename: str
    mime_type: Optional[str] = None
    size_bytes: int
    created_at: str

class MovieSequenceVideoVariant(SQLModel, table=True):
    __tablename__ = "movie_sequence_video_variants"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    scene_id: str
    sequence_id: str
    provider: str
    model_name: str
    seed: Optional[int] = None
    prompt_text: str
    relative_path: str
    original_filename: str
    mime_type: Optional[str] = None
    size_bytes: int
    native_duration_s: float
    output_duration_s: float
    input_frame_relative_path: Optional[str] = None
    input_frame_original_filename: Optional[str] = None
    input_frame_mime_type: Optional[str] = None
    input_frame_size_bytes: int
    input_frame_created_at: Optional[str] = None
    last_frame_relative_path: Optional[str] = None
    last_frame_original_filename: Optional[str] = None
    last_frame_mime_type: Optional[str] = None
    last_frame_size_bytes: int
    last_frame_created_at: Optional[str] = None
    created_at: str

class MovieClipAsset(SQLModel, table=True):
    __tablename__ = "movie_clip_assets"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    scene_id: str
    version: int
    renderer: str
    relative_path: str
    duration_s: float
    width: int
    height: int
    status: str
    metadata_json: str
    created_at: str

class MovieJob(SQLModel, table=True):
    __tablename__ = "movie_jobs"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    scene_id: Optional[str] = None
    job_type: str
    status: str
    progress: float
    payload_json: str
    result_json: str
    error_text: Optional[str] = None
    cancel_requested: int
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

class MovieContinuityReview(SQLModel, table=True):
    __tablename__ = "movie_continuity_reviews"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    scene_id: str
    source: str
    summary_text: str
    findings_json: str
    sequence_suggestions_json: str
    created_at: str
    updated_at: str

class MovieExportAsset(SQLModel, table=True):
    __tablename__ = "movie_export_assets"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    job_id: str
    relative_path: str
    duration_s: float
    created_at: str

class MovieProjectCharacter(SQLModel, table=True):
    __tablename__ = "movie_project_characters"
    workspace_id: str = Field(default="default", index=True)
    id: str = Field(primary_key=True)
    project_id: str
    name: str
    role_summary: str
    prompt_tags: str
    order_index: int
    portrait_image_url: Optional[str] = None
    cowboyshot_image_url: Optional[str] = None
    fullbody_image_url: Optional[str] = None
    created_at: str
    updated_at: str

class MovieAppSetting(SQLModel, table=True):
    __tablename__ = "movie_app_settings"
    workspace_id: str = Field(default="default", index=True)
    key: str = Field(primary_key=True)
    value_text: str
    updated_at: str
