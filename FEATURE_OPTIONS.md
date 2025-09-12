# BiliStalkerMCP 数据能力清单 (Feature Options)

本文档旨在详细列出 `BiliStalkerMCP` 项目理论上可以获取的、围绕一个特定B站用户的全方位数据。这可以作为我们评估和设计工具返回内容时的“最大数据集”参考。

数据主要通过 `bilibili-api-python` 库获取，分为以下几个维度：

---

### 1. 用户基础信息 (`user.get_user_info()`)

这是关于用户本身的静态画像数据。

| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `mid` | integer | **用户的唯一数字ID** |
| `name` | string | 用户的昵称 |
| `sex` | string | 性别 (`男`, `女`, `保密`) |
| `face` | string | 头像图片的URL |
| `sign` | string | 用户的个性签名 |
| `level` | integer | B站用户等级 (0-6) |
| `rank` | integer | 排名 (通常是 10000) |
| `birthday` | string | 生日 (格式如 `MM-DD`) |
| `coins` | integer | 持有的硬币数 |
| `is_followed` | boolean | 当前凭证是否已关注该用户 |
| `top_photo` | string | 用户个人空间头图的URL |
| `live_room` | object | 直播间信息，包含 `roomid`, `url`, `title`, `liveStatus` 等 |
| `vip` | object | 大会员信息，包含 `type`, `status`, `label` 等 |
| `official` | object | 认证信息，包含 `role`, `title`, `desc` 等 |
| `fans_medal` | object | 粉丝勋章信息 |
| `pendant` | object | 头像挂件信息 |
| `nameplate` | object | 认证铭牌信息 |
| `school` | object | 学校信息，包含 `name` |
| `profession` | object | 职业信息 |
| `series` | object | 系列信息，如是否是UP主工房成员 |
| `elec` | object | 充电信息 |

### 2. 用户关系数据 (`relation.stat`)

这是描述用户社交网络位置的数据。

| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `following` | integer | **关注数** |
| `follower` | integer | **粉丝数** |

### 3. 视频投稿 (`user.get_videos()`)

用户发布的视频列表，每个视频包含以下信息。

| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `bvid` | string | **视频的唯一BV号** |
| `aid` | integer | 视频的av号 |
| `mid` | integer | **作者的用户ID** |
| `author` | string | 作者的昵称 |
| `title` | string | 视频标题 |
| `description` | string | 视频简介 |
| `created` | integer | 视频发布时间的Unix时间戳 |
| `length` | string | 视频时长 (格式 `MM:SS`) |
| `play` | integer | 播放量 |
| `comment` | integer | 评论数 |
| `video_review` | integer | 弹幕数 |
| `favorites` | integer | 收藏数 |
| `like` | integer | 点赞数 |
| `pic` | string | 视频封面的URL |
| `copyright` | string | 是否原创 (1: 是) |
| `typeid` | integer | 视频分区ID |
| `is_union_video` | integer | 是否为联合投稿 (1: 是) |
| `is_pay` | integer | 是否为付费视频 (1: 是) |
| `attribute` | integer | 视频属性的位掩码 |
| `subtitle` | object | 字幕信息对象，包含 `subtitles` 列表 |

### 4. 用户动态 (`user.get_dynamics()`)

这是最复杂的数据结构，一条动态可以是多种类型的复合体。核心是 `card` 字段，其内容根据动态类型而变化。

**动态基础信息:**
- `dynamic_id`: 动态的唯一ID
- `type`: 动态的数字类型代码 (如 2: 图文, 8: 视频, 64: 文章, 1: 转发)
- `timestamp`: 发布时间的Unix时间戳
- `stat.like`, `stat.comment`, `stat.forward`: 转评赞统计

**根据类型，动态 `card` 内可能包含的核心内容:**
- **视频 (type=8)**: 包含一个完整的视频对象，结构类似上面的“视频投稿”。
- **图文 (type=2)**: 
    - `item.description`: **动态的文本内容**
    - `item.pictures`: 一个图片列表，每项包含 `img_src` (图片URL)。
- **文章 (type=64)**: 
    - `title`, `summary`, `banner_url`, `id` (cv号)
- **转发 (type=1)**: 
    - `item.content`: **转发时添加的评论文本**
    - `origin`: 一个字符串形式的JSON，包含了被转发的**原始动态**的全部信息，需要再次解析。

### 5. 专栏文章 (`user.get_articles()`)

用户发布的文章列表，每篇文章包含以下信息。

| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `id` | integer | **文章的唯一ID (cv号)** |
| `author.mid` | integer | **作者的用户ID** |
| `author.name` | string | 作者的昵称 |
| `title` | string | 文章标题 |
| `summary` | string | 文章摘要 |
| `banner_url` | string | 文章头图的URL |
| `publish_time` | integer | 发布时间的Unix时间戳 |
| `ctime` | integer | 创建时间的Unix时间戳 |
| `words` | integer | 文章字数 |
| `stats` | object | 统计信息，包含 `view`, `favorite`, `like`, `reply` 等 |
| `category` | object | 分区信息，包含 `id` 和 `name` |
| `reprint` | integer | 是否为转载 (0: 原创, 1: 转载) |
| `image_urls` | list | 正文中所有图片的URL列表 |

---

请您审阅这份清单。当您决定好需要保留哪些字段后，请随时告诉我，我将立即为您执行精简操作。