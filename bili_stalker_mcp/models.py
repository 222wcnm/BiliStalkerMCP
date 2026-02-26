from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserInfoResponse(BaseModel):
    mid: int
    name: str
    sign: str | None = None
    following: int | None = None
    follower: int | None = None


class VideoListItem(BaseModel):
    bvid: str | None = None
    aid: int | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    length: str | None = None
    created_time: str | None = None
    play: int | None = None
    review: int | None = None


class VideoListResponse(BaseModel):
    videos: list[VideoListItem] = Field(default_factory=list)
    total: int = 0


class VideoStatResponse(BaseModel):
    view: int | None = None
    danmaku: int | None = None
    reply: int | None = None
    favorite: int | None = None
    coin: int | None = None
    share: int | None = None
    like: int | None = None


class VideoDetailItem(BaseModel):
    bvid: str | None = None
    aid: int | None = None
    title: str | None = None
    desc: str | None = None
    publish_time: str | None = None
    stat: VideoStatResponse = Field(default_factory=VideoStatResponse)
    tags: list[str] = Field(default_factory=list)
    pages: list[dict[str, Any]] = Field(default_factory=list)


class SubtitleTrack(BaseModel):
    cid: int | None = None
    part: str | None = None
    lan: str | None = None
    lan_doc: str | None = None
    is_ai_generated: bool = False
    text: str = ""


class SubtitleResponse(BaseModel):
    enabled: bool = True
    mode: str = "full"
    requested_language: str = "auto"
    available_languages: list[str] = Field(default_factory=list)
    selected_language: str | None = None
    fallback_reason: str | None = None
    truncated: bool = False
    returned_chars: int = 0
    dropped_tracks: int = 0
    track_count: int = 0
    tracks: list[SubtitleTrack] = Field(default_factory=list)
    full_text: str = ""
    errors: list[str] = Field(default_factory=list)


class VideoDetailResponse(BaseModel):
    video: VideoDetailItem = Field(default_factory=VideoDetailItem)
    subtitles: SubtitleResponse = Field(default_factory=SubtitleResponse)


class DynamicStatsResponse(BaseModel):
    like: int = 0
    comment: int = 0
    forward: int = 0


class DynamicVideoRef(BaseModel):
    title: str | None = None
    bvid: str | None = None


class DynamicArticleRef(BaseModel):
    id: int | None = None
    title: str | None = None


class DynamicOriginResponse(BaseModel):
    type: str | None = None
    text_content: str | None = None
    image_count: int = 0
    user_name: str | None = None
    user_id: int | None = None
    video: DynamicVideoRef | None = None
    article: DynamicArticleRef | None = None


class DynamicItemResponse(BaseModel):
    dynamic_id: str | None = None
    publish_time: str | None = None
    type: str | None = None
    text_content: str | None = None
    image_count: int = 0
    stats: DynamicStatsResponse = Field(default_factory=DynamicStatsResponse)
    video: DynamicVideoRef | None = None
    article: DynamicArticleRef | None = None
    origin: DynamicOriginResponse | None = None


class DynamicListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dynamics: list[DynamicItemResponse] = Field(default_factory=list)
    total_fetched: int = 0
    filter_type: str
    next_cursor: str | None = None
    has_more: bool = False


class ArticleStatsResponse(BaseModel):
    view: int | None = None
    like: int | None = None
    reply: int | None = None
    coin: int | None = None
    share: int | None = None


class ArticleListItem(BaseModel):
    id: int | None = None
    title: str | None = None
    summary: str | None = None
    publish_time_str: str | None = None
    stats: ArticleStatsResponse = Field(default_factory=ArticleStatsResponse)


class ArticlesResponse(BaseModel):
    articles: list[ArticleListItem] = Field(default_factory=list)
    total: int = 0


class ArticleContentResponse(BaseModel):
    id: int
    title: str | None = None
    markdown_content: str = ""


class FollowingItemResponse(BaseModel):
    mid: int | None = None
    uname: str | None = None
    sign: str | None = None


class FollowingsResponse(BaseModel):
    followings: list[FollowingItemResponse] = Field(default_factory=list)
    total: int = 0
