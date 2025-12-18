# BiliStalkerMCP 返回字段说明（精简版）

本文档记录各工具返回的字段。已针对**视频内容分析**场景进行精简，移除了无分析价值的字段。

---

## 图例

| 标记 | 含义 |
|------|------|
| ⭐⭐⭐ | 核心字段，必须保留 |
| ⭐⭐ | 有用字段，建议保留 |
| ⭐ | 次要字段，可保留可移除 |
| ❌ | 低价值字段，建议移除 |

---

## 1. get_user_info（获取用户信息）

用途：获取B站用户的基本资料

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `mid` | 用户ID | 用户的唯一数字标识，用于调用其他API | ⭐⭐⭐ |
| `name` | 用户名 | 用户的昵称 | ⭐⭐⭐ |
| `face` | 头像地址 | 用户头像的图片URL | ❌ |
| `sign` | 个性签名 | 用户自己填写的简介 | ⭐ |
| `level` | 等级 | B站用户等级（0-6级） | ⭐ |
| `birthday` | 生日 | 用户填写的生日日期 | ❌ |
| `sex` | 性别 | 男/女/保密 | ❌ |
| `live_room` | 直播间信息 | 用户的直播间相关数据 | ❌ |
| `following` | 关注数 | 该用户关注了多少人 | ⭐ |
| `follower` | 粉丝数 | 有多少人关注该用户 | ⭐⭐ |

**精简建议**：仅保留 `mid`、`name`，可选保留 `follower`

---

## 2. get_user_video_updates（获取用户视频列表）

用途：获取用户发布的视频列表，**这是核心工具**

### 视频基础信息

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `bvid` | BV号 | 视频的唯一标识（新格式），如 BV1xx411c7XW | ⭐⭐⭐ |
| `aid` | AV号 | 视频的旧格式标识（数字），如 av170001 | ❌ |
| `title` | 视频标题 | 视频的标题文字 | ⭐⭐⭐ |
| `description` | 视频简介 | UP主填写的视频描述文字 | ⭐⭐ |
| `created` | 发布时间 | 视频发布的时间戳（秒） | ⭐⭐ |
| `length` | 视频时长 | 视频长度，格式如 "12:34" | ⭐ |
| `pic` | 封面图片 | 视频封面的图片URL | ❌ |
| `url` | 视频链接 | 视频的完整播放地址 | ❌ |

### 视频互动数据

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `play` | 播放量 | 视频被播放的次数 | ⭐⭐ |
| `like` | 点赞数 | 视频获得的点赞数量 | ⭐⭐ |
| `comment` | 评论数 | 视频下的评论数量 | ⭐ |
| `favorites` | 收藏数 | 视频被收藏的次数 | ⭐ |

### 字幕信息（subtitle 对象）

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `has_subtitle` | 是否有字幕 | true/false，表示视频是否有字幕 | ⭐⭐⭐ |
| `subtitle_count` | 字幕数量 | 有多少种语言的字幕 | ⭐ |
| `subtitle_summary` | 字幕概要 | 简洁描述，如"有2种字幕: 中文(AI生成), 英文" | ⭐⭐⭐ |
| `subtitle_list` | 字幕详情列表 | 每种字幕的详细信息数组 | ❌ |

#### subtitle_list 内部字段（如保留）

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `id` | 字幕ID | 字幕的内部ID | ❌ |
| `lan` | 语言代码 | 如 "zh-CN"、"en" | ⭐ |
| `lan_doc` | 语言名称 | 如 "中文（中国）"、"英语" | ⭐ |
| `author_mid` | 字幕作者ID | 上传字幕的用户ID | ❌ |
| `author_name` | 字幕作者名 | 上传字幕的用户昵称 | ❌ |
| `subtitle_url` | 字幕下载地址 | 字幕文件的URL | ⭐⭐ |
| `is_ai_generated` | 是否AI生成 | true/false，是否为AI自动生成 | ⭐ |

**精简建议**：
- 必须保留：`bvid`、`title`、`subtitle.has_subtitle`、`subtitle.subtitle_summary`
- 建议保留：`description`、`created`、`play`、`like`
- 建议移除：`aid`、`pic`、`url`、`subtitle_list`（或仅保留 `subtitle_url`）

---

## 3. get_user_dynamic_updates（获取用户动态）

用途：获取用户发布的动态（类似微博/朋友圈）

### 动态基础信息

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `dynamic_id` | 动态ID | 动态的唯一标识 | ⭐⭐ |
| `author_mid` | 作者ID | 发布者的用户ID（已知，冗余） | ❌ |
| `timestamp` | 发布时间 | 动态发布的时间戳（秒） | ⭐⭐ |
| `type` | 动态类型 | 如 VIDEO、IMAGE_TEXT、TEXT、ARTICLE 等 | ⭐⭐⭐ |
| `text_content` | 文字内容 | 动态的文字部分 | ⭐⭐⭐ |

### 互动统计（stats 对象）

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `like` | 点赞数 | 动态获得的点赞 | ⭐ |
| `comment` | 评论数 | 动态下的评论数 | ⭐ |
| `forward` | 转发数 | 动态被转发的次数 | ⭐ |

### 类型特定字段

| 字段 | 中文含义 | 出现条件 | 价值 |
|------|----------|----------|------|
| `images` | 图片列表 | IMAGE_TEXT 类型 | ❌ |
| `video` | 视频信息 | VIDEO 类型 | ⭐⭐ |
| `article` | 文章信息 | ARTICLE 类型 | ⭐⭐ |
| `origin_user` | 原作者 | REPOST 转发类型 | ⭐ |
| `origin_content` | 原内容 | REPOST 转发类型 | ⭐ |

**精简建议**：
- 必须保留：`dynamic_id`、`type`、`text_content`、`timestamp`
- 建议保留：`video`（仅 bvid、title）
- 建议移除：`author_mid`、`images`、`stats`、`origin_*`

---

## 4. get_user_articles（获取用户专栏文章）

用途：获取用户发布的专栏文章

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `id` | 文章ID | 文章的唯一标识（cv号的数字部分） | ⭐⭐⭐ |
| `mid` | 作者ID | 作者的用户ID（已知，冗余） | ❌ |
| `title` | 文章标题 | 文章的标题 | ⭐⭐⭐ |
| `summary` | 文章摘要 | 文章内容的简短摘要 | ⭐⭐ |
| `banner_url` | 横幅图片 | 文章顶部的横幅图URL | ❌ |
| `publish_time` | 发布时间 | 文章发布的时间戳（秒） | ⭐⭐ |
| `words` | 字数 | 文章的总字数 | ⭐ |
| `url` | 文章链接 | 文章的完整阅读地址 | ❌ |

### 统计数据（stats 对象）

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `view` | 阅读量 | 文章被阅读的次数 | ⭐⭐ |
| `like` | 点赞数 | 文章获得的点赞 | ⭐ |
| `reply` | 评论数 | 文章下的评论数 | ⭐ |
| `favorite` | 收藏数 | 文章被收藏的次数 | ⭐ |
| `coin` | 投币数 | 文章获得的硬币数 | ⭐ |
| `share` | 分享数 | 文章被分享的次数 | ⭐ |

**精简建议**：
- 必须保留：`id`、`title`、`summary`、`publish_time`
- 建议保留：`stats.view`
- 建议移除：`mid`、`banner_url`、`words`、`url`

---

## 5. get_user_followings（获取用户关注列表）

用途：获取用户关注的其他用户列表

| 字段 | 中文含义 | 说明 | 价值 |
|------|----------|------|------|
| `mid` | 用户ID | 被关注者的用户ID | ⭐⭐⭐ |
| `uname` | 用户名 | 被关注者的昵称 | ⭐⭐⭐ |
| `face` | 头像地址 | 被关注者的头像URL | ❌ |
| `sign` | 个性签名 | 被关注者的简介 | ❌ |
| `official_verify` | 认证信息 | 官方认证描述（如"知名UP主"） | ⭐ |

**精简建议**：仅保留 `mid`、`uname`

---

## 总结：推荐精简方案

### 应移除的字段（无分析价值）

1. **所有图片URL**：`face`、`pic`、`banner_url`、`images`
2. **可拼接的链接**：`url`（可由 bvid/id 拼接生成）
3. **冗余ID**：`aid`（有 bvid 即可）、`author_mid`、文章的 `mid`
4. **隐私信息**：`birthday`、`sex`
5. **低价值信息**：`live_room`、`level`、`sign`

### 应简化的结构

`subtitle` 对象：移除 `subtitle_list`，仅保留：
```json
{
  "has_subtitle": true,
  "subtitle_summary": "有2种字幕: 中文(AI生成), 英文"
}
```

---

## 附录：字段命名对照表

| 英文 | 中文 |
|------|------|
| mid | 用户ID |
| name/uname | 用户名 |
| face | 头像 |
| sign | 签名 |
| level | 等级 |
| follower | 粉丝数 |
| following | 关注数 |
| bvid | BV号 |
| aid | AV号 |
| title | 标题 |
| description/desc | 描述/简介 |
| created/publish_time | 发布时间 |
| length | 时长 |
| play/view | 播放量/阅读量 |
| like | 点赞数 |
| comment/reply | 评论数 |
| favorites/favorite | 收藏数 |
| coin | 投币数 |
| share | 分享数 |
| forward/repost | 转发数 |
| pic | 封面图 |
| subtitle | 字幕 |
| dynamic | 动态 |
| article | 专栏文章 |
| timestamp | 时间戳 |
