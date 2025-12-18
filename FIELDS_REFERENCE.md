# BiliStalkerMCP 字段参考手册

本文档记录各工具**当前返回的字段**和**可选添加的字段**。

---

## 图例

| 标记 | 含义 |
|------|------|
| ✅ | 当前已返回 |
| ➕ | 可选添加（API 支持但未返回） |
| ❌ | 不建议添加（低价值或冗余） |

---

## 1. get_user_info（获取用户信息）

用途：获取B站用户的基本资料

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `mid` | 用户ID | 用户的唯一数字标识 | ✅ |
| `name` | 用户名 | 用户的昵称 | ✅ |
| `sign` | 个性签名 | 用户自己填写的简介 | ✅ |
| `following` | 关注数 | 该用户关注了多少人 | ✅ |
| `follower` | 粉丝数 | 有多少人关注该用户 | ✅ |
| `face` | 头像地址 | 用户头像的图片URL | ➕ |
| `level` | 等级 | B站用户等级（0-6级） | ➕ |
| `birthday` | 生日 | 用户填写的生日日期 | ❌ |
| `sex` | 性别 | 男/女/保密 | ❌ |
| `live_room` | 直播间信息 | 用户的直播间相关数据 | ❌ |
| `official` | 认证信息 | 官方认证（UP主/机构等） | ➕ |
| `vip` | 大会员信息 | 会员类型和状态 | ➕ |

---

## 2. get_user_video_updates（获取用户视频列表）

用途：获取用户发布的视频列表（核心工具）

### 视频基础信息

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `bvid` | BV号 | 视频唯一标识，可拼接 `https://www.bilibili.com/video/{bvid}` | ✅ |
| `title` | 视频标题 | 视频的标题文字 | ✅ |
| `pic` | 封面图片 | 视频封面的图片URL，可用 `![](url)` 渲染 | ✅ |
| `description` | 视频简介 | UP主填写的视频描述文字 | ✅ |
| `created` | 发布时间戳 | 视频发布的Unix时间戳（秒） | ✅ |
| `created_time` | 发布时间(可读) | 格式化时间，如 "2024-12-18 20:00" | ✅ |
| `play` | 播放量 | 视频被播放的次数 | ✅ |
| `like` | 点赞数 | 视频获得的点赞数量 | ✅ |
| `subtitle` | 字幕信息 | 包含 `has_subtitle` 和 `subtitle_summary` | ✅ |
| `length` | 视频时长 | 视频长度，格式如 "12:34" | ➕ |
| `comment` | 评论数 | 视频下的评论数量 | ➕ |
| `favorites` | 收藏数 | 视频被收藏的次数 | ➕ |
| `coin` | 投币数 | 视频获得的硬币数 | ➕ |
| `share` | 分享数 | 视频被分享的次数 | ➕ |
| `danmaku` | 弹幕数 | 视频的弹幕数量 | ➕ |
| `aid` | AV号 | 视频的旧格式标识（数字） | ❌ |
| `url` | 视频链接 | 视频的完整播放地址（可拼接，冗余） | ❌ |

### 字幕信息（subtitle 对象）

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `has_subtitle` | 是否有字幕 | true/false | ✅ |
| `subtitle_summary` | 字幕概要 | 如"有2种字幕: 中文(AI生成), 英文" | ✅ |
| `subtitle_count` | 字幕数量 | 有多少种语言的字幕 | ➕ |
| `subtitle_list` | 字幕详情列表 | 每种字幕的详细信息数组 | ➕ |

---

## 3. get_user_dynamic_updates（获取用户动态）

用途：获取用户发布的动态（类似微博/朋友圈）

### 动态基础信息

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `dynamic_id` | 动态ID | 动态的唯一标识 | ✅ |
| `type` | 动态类型 | TEXT/IMAGE_TEXT/REPOST/VIDEO/ARTICLE 等 | ✅ |
| `text_content` | 文字内容 | 动态的文字部分 | ✅ |
| `timestamp` | 发布时间戳 | 动态发布的Unix时间戳（秒） | ✅ |
| `publish_time` | 发布时间(可读) | 格式化时间，如 "2024-12-18 20:00" | ✅ |
| `images` | 图片列表 | IMAGE_TEXT 类型的图片URL数组，可用 `![](url)` 渲染 | ✅ |
| `origin` | 转发原内容 | REPOST 类型的被转发内容详情 | ✅ |
| `video` | 视频信息 | VIDEO 类型的视频 bvid/title | ✅ |
| `article` | 文章信息 | ARTICLE 类型的文章 id/title | ✅ |
| `like_count` | 点赞数 | 动态获得的点赞 | ➕ |
| `comment_count` | 评论数 | 动态下的评论数 | ➕ |
| `forward_count` | 转发数 | 动态被转发的次数 | ➕ |

### origin 对象（转发动态的原始内容）

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `user_name` | 原作者昵称 | 被转发内容的作者名 | ✅ |
| `user_id` | 原作者ID | 被转发内容的作者UID | ✅ |
| `type` | 原内容类型 | VIDEO/IMAGE_TEXT/TEXT/ARTICLE/OTHER_xxx | ✅ |
| `text_content` | 原文字内容 | 原动态的文字部分 | ✅ |
| `video` | 原视频信息 | 如果是视频，包含 title/bvid/pic | ✅ |
| `images` | 原图片列表 | 如果是图文，包含图片URL数组 | ✅ |
| `article` | 原文章信息 | 如果是文章，包含 id/title | ✅ |

---

## 4. get_user_articles（获取用户专栏文章）

用途：获取用户发布的专栏文章

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `id` | 文章ID | 可拼接 `https://www.bilibili.com/read/cv{id}` | ✅ |
| `title` | 文章标题 | 文章的标题 | ✅ |
| `summary` | 文章摘要 | 文章内容的简短摘要 | ✅ |
| `publish_time` | 发布时间戳 | 文章发布的Unix时间戳（秒） | ✅ |
| `publish_time_str` | 发布时间(可读) | 格式化时间，如 "2024-12-18 20:00" | ✅ |
| `stats` | 统计数据 | 包含 view/like/reply/favorite/coin/share | ✅ |
| `banner_url` | 横幅图片 | 文章顶部的横幅图URL | ➕ |
| `words` | 字数 | 文章的总字数 | ➕ |
| `categories` | 分类标签 | 文章的分类信息 | ➕ |
| `mid` | 作者ID | 作者的用户ID（冗余） | ❌ |
| `url` | 文章链接 | 文章的完整阅读地址（可拼接，冗余） | ❌ |

---

## 5. get_user_followings（获取用户关注列表）

用途：获取用户关注的其他用户列表

| 字段 | 中文含义 | 说明 | 状态 |
|------|----------|------|------|
| `mid` | 用户ID | 被关注者的用户ID | ✅ |
| `uname` | 用户名 | 被关注者的昵称 | ✅ |
| `sign` | 个性签名 | 被关注者的简介 | ✅ |
| `face` | 头像地址 | 被关注者的头像URL | ➕ |
| `official_verify` | 认证信息 | 官方认证描述（如"知名UP主"） | ➕ |
| `vip` | 大会员信息 | 会员类型和状态 | ➕ |

---

## 快速参考：当前返回字段汇总

### get_user_info
```json
{
  "mid": 12345,
  "name": "用户昵称",
  "sign": "个性签名",
  "following": 100,
  "follower": 10000
}
```

### get_user_video_updates
```json
{
  "videos": [{
    "bvid": "BV1xxx",
    "title": "视频标题",
    "pic": "https://...",
    "description": "视频简介",
    "created": 1734537600,
    "created_time": "2024-12-19 00:00",
    "play": 10000,
    "like": 500,
    "subtitle": {
      "has_subtitle": true,
      "subtitle_summary": "有2种字幕: 中文(AI生成), 英文"
    }
  }],
  "total": 50
}
```

### get_user_dynamic_updates
```json
{
  "dynamics": [{
    "dynamic_id": "123456789",
    "type": "REPOST",
    "text_content": "转发评论",
    "timestamp": 1734537600,
    "publish_time": "2024-12-19 00:00",
    "origin": {
      "user_name": "原作者",
      "user_id": 12345,
      "type": "VIDEO",
      "text_content": "原视频简介",
      "video": {"title": "视频标题", "bvid": "BV1xxx", "pic": "..."}
    }
  }],
  "total_fetched": 10,
  "filter_type": "ALL"
}
```

### get_user_articles
```json
{
  "articles": [{
    "id": 12345678,
    "title": "文章标题",
    "summary": "文章摘要...",
    "publish_time": 1734537600,
    "publish_time_str": "2024-12-19 00:00",
    "stats": {"view": 1000, "like": 50, "reply": 10}
  }]
}
```

### get_user_followings
```json
{
  "followings": [{
    "mid": 12345,
    "uname": "用户昵称",
    "sign": "个性签名"
  }],
  "total": 100
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
| origin | 转发原内容 |
