from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserInfoResponse(BaseModel):
    mid: int
    name: str
    sign: str | None = None
    following: int | None = None
    follower: int | None = None


class SubtitleSummary(BaseModel):
    has_subtitle: bool = False
    subtitle_summary: str = "No subtitles"


class VideoItemResponse(BaseModel):
    bvid: str | None = None
    title: str | None = None
    pic: str | None = None
    description: str | None = None
    created: int | None = None
    created_time: str | None = None
    play: int | None = None
    like: int | None = None
    subtitle: SubtitleSummary


class VideoUpdatesResponse(BaseModel):
    videos: list[VideoItemResponse] = Field(default_factory=list)
    total: int = 0


class DynamicUpdatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dynamics: list[dict[str, Any]] = Field(default_factory=list)
    total_fetched: int = 0
    filter_type: str
    next_cursor: str | None = None
    has_more: bool = False


class ArticleItemResponse(BaseModel):
    id: int | None = None
    title: str | None = None
    summary: str | None = None
    publish_time: int | None = None
    publish_time_str: str | None = None
    stats: dict[str, Any] | None = None


class ArticlesResponse(BaseModel):
    articles: list[ArticleItemResponse] = Field(default_factory=list)


class FollowingItemResponse(BaseModel):
    mid: int | None = None
    uname: str | None = None
    sign: str | None = None


class FollowingsResponse(BaseModel):
    followings: list[FollowingItemResponse] = Field(default_factory=list)
    total: int = 0
