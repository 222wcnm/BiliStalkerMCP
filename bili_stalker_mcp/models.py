from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserOfficialInfo(BaseModel):
    role: int | None = None
    title: str | None = None


class UserVipInfo(BaseModel):
    status: bool = False
    label: str | None = None


class UserLiveRoomInfo(BaseModel):
    is_live: bool = False
    title: str | None = None
    url: str | None = None
    watched: int | None = None


class UserInfoResponse(BaseModel):
    mid: int = Field(description="Bilibili user ID; the same identifier as uid.")
    name: str
    face: str | None = None
    sign: str | None = None
    level: int | None = None
    sex: str | None = None
    birthday: str | None = None
    school: str | None = None
    profession: str | None = None
    official: UserOfficialInfo | None = None
    vip: UserVipInfo | None = None
    is_banned: bool | None = None
    is_senior_member: bool | None = None
    live_room: UserLiveRoomInfo | None = None
    following: int | None = None
    follower: int | None = None
    total_video_views: int | None = None
    total_article_views: int | None = None
    total_likes: int | None = None


class UserSearchItem(BaseModel):
    uid: int
    name: str
    sign: str | None = None
    avatar: str | None = None
    follower: int | None = None
    videos: int | None = None
    level: int | None = None
    is_live: bool | None = None
    is_exact_match: bool = False


class UserSearchResponse(BaseModel):
    users: list[UserSearchItem] = Field(default_factory=list)
    count: int = 0
    exact_match_uid: int | None = None


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


class VideoOwnerItem(BaseModel):
    mid: int | None = Field(
        default=None, description="Uploader's Bilibili user ID (uid)."
    )
    name: str | None = None
    face: str | None = None


class VideoPageItem(BaseModel):
    cid: int | None = None
    page: int | None = None
    part: str | None = None
    duration: int | None = Field(default=None, description="Part duration in seconds.")


class VideoDetailItem(BaseModel):
    bvid: str | None = None
    aid: int | None = None
    title: str | None = None
    desc: str | None = None
    publish_time: str | None = None
    owner: VideoOwnerItem | None = None
    duration: int | None = Field(
        default=None, description="Total video duration in seconds, across all parts."
    )
    pic: str | None = Field(default=None, description="Cover image URL.")
    tname: str | None = Field(default=None, description="Upstream category name.")
    videos: int | None = Field(default=None, description="Number of video parts.")
    ctime: int | None = Field(
        default=None,
        description="Upstream creation time as a Unix timestamp in seconds.",
    )
    stat: VideoStatResponse = Field(default_factory=VideoStatResponse)
    tags: list[str] = Field(
        default_factory=list,
        description="Tags supplied by the detail source. Empty can mean unavailable, not no tags.",
    )
    pages: list[VideoPageItem] = Field(default_factory=list)


class SubtitleTrack(BaseModel):
    cid: int | None = None
    part: str | None = None
    lan: str | None = None
    lan_doc: str | None = None
    is_ai_generated: bool = False
    text: str = Field(
        default="",
        description="Compatibility field, always empty. Read subtitles.full_text for text.",
    )


class SubtitleScopeSummary(BaseModel):
    mode: Literal["single", "all"]
    target_page: int | None = Field(
        default=None,
        description="Selected page number in single scope; null in all scope.",
    )
    total_pages: int = 0
    returned_pages: list[int] = Field(
        default_factory=list,
        description="Pages with at least one subtitle text character returned. This does not guarantee complete text; inspect errors and truncated.",
    )
    summary: str = ""


class SubtitleResponse(BaseModel):
    enabled: bool = True
    mode: str = "full"
    scope: SubtitleScopeSummary | None = None
    requested_language: str = "auto"
    available_languages: list[str] = Field(default_factory=list)
    selected_language: str | None = Field(
        default=None,
        description="Selected track language in smart mode. Null in full/minimal/disabled modes; use tracks[].lan for full mode.",
    )
    fallback_reason: str | None = None
    truncated: bool = False
    returned_chars: int = 0
    dropped_tracks: int = 0
    track_count: int = 0
    tracks: list[SubtitleTrack] = Field(
        default_factory=list,
        description="Track metadata only. A track can be listed even if its text failed to download; inspect errors.",
    )
    full_text: str = Field(
        default="",
        description="Subtitle text, returned once within subtitle_max_chars; multiple full-mode tracks have language/part labels. No timecodes.",
    )
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


class DynamicReviewRef(BaseModel):
    rating: int | None = None
    text: str | None = None
    title: str | None = None
    cover_url: str | None = None
    jump_url: str | None = None
    score_description: str | None = None
    biz_type: str | None = None
    biz_id: str | None = None


class DynamicImageResponse(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None


class DynamicOriginResponse(BaseModel):
    type: str | None = None
    text_content: str | None = None
    image_count: int = 0
    images: list[DynamicImageResponse] = Field(default_factory=list)
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
    images: list[DynamicImageResponse] = Field(default_factory=list)
    stats: DynamicStatsResponse = Field(default_factory=DynamicStatsResponse)
    video: DynamicVideoRef | None = None
    article: DynamicArticleRef | None = None
    review: DynamicReviewRef | None = None
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
    id: str
    title: str | None = None
    markdown_content: str = ""


class FollowingItemResponse(BaseModel):
    mid: int | None = None
    uname: str | None = None
    sign: str | None = None


class FollowingsResponse(BaseModel):
    followings: list[FollowingItemResponse] = Field(default_factory=list)
    total: int = 0


class CommentMemberResponse(BaseModel):
    mid: int | None = None
    uname: str | None = None


class CommentPictureResponse(BaseModel):
    url: str
    width: float | None = None
    height: float | None = None
    size_kb: float | None = None


class CommentNoteResponse(BaseModel):
    cvid: str | None = None
    summary: str | None = None
    images: list[str] = Field(default_factory=list)
    url: str | None = None
    content_is_preview: bool = True


class CommentItemResponse(BaseModel):
    rpid: int | None = None
    root_rpid: int | None = None
    parent_rpid: int | None = None
    content: str | None = None
    member: CommentMemberResponse = Field(default_factory=CommentMemberResponse)
    like: int | None = None
    reply_count: int | None = None
    publish_time: str | None = None
    pictures: list[CommentPictureResponse] = Field(default_factory=list)
    note: CommentNoteResponse | None = None
    replies: list["CommentItemResponse"] = Field(default_factory=list)


CommentItemResponse.model_rebuild()


class CommentsResponse(BaseModel):
    comments: list[CommentItemResponse] = Field(default_factory=list)
    top: CommentItemResponse | None = None
    count: int = 0
    total: int = 0
    next_cursor: str | None = None
    has_more: bool = False


class CommentRepliesResponse(BaseModel):
    replies: list[CommentItemResponse] = Field(default_factory=list)
    count: int = 0
    total: int = 0
    page: int = 1
    has_more: bool = False


class UserSnapshotResponse(BaseModel):
    uid: int
    user: UserInfoResponse | None = None
    videos: VideoListResponse | None = None
    dynamics: DynamicListResponse | None = None
    articles: ArticlesResponse | None = None
    errors: dict[str, str] = Field(
        default_factory=dict,
        description="Section names mapped to JSON-encoded errors. Null sections without errors were skipped.",
    )
