# BiliStalkerMCP 数据能力清单 (Feature Options)

本文档详细列出了 `BiliStalkerMCP` 项目实际支持获取的、围绕特定B站用户的全方位数据能力。这是基于项目当前实现的完整数据结构参考文档。

> **更新时间**: 2025-09-16  
> **版本**: v1.1.0 (修复user_id参数和动态类型筛选后)  
> **状态**: ✅ 所有功能已验证可用

数据通过 `bilibili-api-python` 库和自定义API调用获取，分为以下几个维度：

---

### 1. 用户基础信息 (`get_user_info`)

**工具名**: `get_user_info`  
**支持参数**: `user_id` (int) 或 `username` (str)  
**实现状态**: ✅ 完全支持  

获取用户的基础个人信息和关系数据。

#### 核心字段 (必返回)
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `mid` | integer | **用户的唯一数字ID** |
| `name` | string | **用户的昵称** |
| `face` | string | **头像图片的URL** |
| `sign` | string | **用户的个性签名** |
| `level` | integer | **B站用户等级 (0-6)** |
| `following` | integer | **关注数** (通过额外API获取) |
| `follower` | integer | **粉丝数** (通过额外API获取) |

#### 可选字段 (可能为空)
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `birthday` | string | 生日 (格式如 `MM-DD`) |
| `sex` | string | 性别 (`男`, `女`, `保密`) |
| `top_photo` | string | 用户个人空间头图的URL |
| `live_room` | object | 直播间信息，包含 `roomid`, `url`, `title`, `liveStatus` 等 |

### 2. 用户视频投稿 (`get_user_video_updates`)

**工具名**: `get_user_video_updates`  
**支持参数**: `user_id` (int) 或 `username` (str), `page` (int), `limit` (int, 1-50)  
**实现状态**: ✅ 完全支持，包含增强字幕信息  

获取用户发布的视频列表，每个视频包含详细的字幕信息。

#### 核心字段 (必返回)
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `bvid` | string | **视频的唯一BV号** (自动从aid转换生成) |
| `aid` | integer | **视频的av号** |
| `mid` | integer | **作者的用户ID** |
| `title` | string | **视频标题** |
| `description` | string | **视频简介** |
| `created` | integer | **视频发布时间的Unix时间戳** |
| `length` | string | **视频时长** (格式 `MM:SS`) |
| `play` | integer | **播放量** |
| `comment` | integer | **评论数** |
| `favorites` | integer | **收藏数** |
| `like` | integer | **点赞数** |
| `pic` | string | **视频封面的URL** |
| `url` | string | **视频播放地址** (自动生成) |

#### 增强字幕信息 (subtitle对象)
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `has_subtitle` | boolean | **是否有字幕** |
| `subtitle_count` | integer | **字幕数量** |
| `subtitle_summary` | string | **字幕概要** (如"有2种字幕: 中文(简体), English") |
| `subtitle_list` | array | **详细字幕列表** |

#### 字幕列表项 (subtitle_list中的每项)
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `id` | string | 字幕ID |
| `lan` | string | 语言代码 |
| `lan_doc` | string | 语言名称 |
| `subtitle_url` | string | **字幕下载URL** |
| `is_ai_generated` | boolean | **是否为AI生成字幕** |
| `author_mid` | integer | 字幕作者ID (如果有) |
| `author_name` | string | 字幕作者名称 (如果有) |

### 3. 用户动态内容 (`get_user_dynamic_updates`)

**工具名**: `get_user_dynamic_updates`  
**支持参数**: `user_id` (int) 或 `username` (str), `offset` (int), `limit` (int, 1-50), `dynamic_type` (str)  
**实现状态**: ✅ 完全支持，包含类型筛选  

获取用户的动态列表，支持按类型筛选。已解析为统一的数据结构。

#### 支持的动态类型筛选
| 类型参数 | API类型ID | 说明 |
| :--- | :--- | :--- |
| `ALL` | all | **所有类型** (默认) |
| `VIDEO` | 8 | **视频动态** |
| `DRAW` | 2 | **图文动态** |
| `ARTICLE` | 64 | **专栏动态** |
| `ANIME` | 512 | **番剧动态** |

#### 核心字段 (所有动态类型通用)
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `dynamic_id` | string | **动态的唯一ID** |
| `type` | string | **解析后的动态类型** (VIDEO, IMAGE_TEXT, ARTICLE等) |
| `type_id` | integer | **原始类型ID** |
| `author_mid` | integer | **作者的用户ID** |
| `timestamp` | integer | **发布的Unix时间戳** |
| `text_content` | string | **动态文本内容** |
| `stats` | object | **互动统计** (包含like, comment, forward) |

#### 特定类型附加字段
**视频动态 (type="VIDEO")**:
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `video.title` | string | 视频标题 |
| `video.bvid` | string | 视频BVID |
| `video.aid` | integer | 视频AID |
| `video.desc` | string | 视频描述 |
| `video.pic` | string | 视频封面 |

**图文动态 (type="IMAGE_TEXT")**:
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `images` | array | 图片URL列表 |

**专栏动态 (type="ARTICLE")**:
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `article.id` | integer | 专栏文章ID |
| `article.title` | string | 文章标题 |
| `article.covers` | array | 文章封面图片列表 |


### 4. 专栏文章 (`get_user_articles`)

**工具名**: `get_user_articles`  
**支持参数**: `user_id` (int) 或 `username` (str), `page` (int), `limit` (int, 1-50)  
**实现状态**: ✅ 完全支持  

获取用户发布的专栏文章列表。

#### 核心字段
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `id` | integer | **文章的唯一ID (cv号)** |
| `mid` | integer | **作者的用户ID** |
| `title` | string | **文章标题** |
| `summary` | string | **文章摘要** |
| `banner_url` | string | **文章头图的URL** |
| `publish_time` | integer | **发布时间的Unix时间戳** |
| `words` | integer | **文章字数** |
| `stats` | object | **统计信息** (包含view, favorite, like, reply等) |
| `url` | string | **文章链接** (自动生成) |

### 5. 用户关注列表 (`get_user_followings`)

**工具名**: `get_user_followings`  
**支持参数**: `user_id` (int) 或 `username` (str), `page` (int), `limit` (int, 1-50)  
**实现状态**: ✅ 完全支持，支持隐私检测  

获取用户的关注列表。如果用户设置了隐私，会返回相应错误信息。

#### 核心字段
| 字段名 | 数据类型 | 解释 |
| :--- | :--- | :--- |
| `mid` | integer | **被关注用户的ID** |
| `uname` | string | **被关注用户的昵称** |
| `face` | string | **被关注用户的头像** |
| `sign` | string | **被关注用户的签名** |
| `official_verify` | string | **认证信息** |
| `vip_type` | integer | **大会员类型** |

---

## 错误处理能力

所有工具都支持详细的错误处理，包括：

- **参数验证错误**: 友好的中文错误提示
- **用户不存在**: 区分用户ID和用户名错误
- **API限流**: 检测并提示速率限制
- **隐私设置**: 检测用户隐私设置限制
- **网络错误**: 网络连接和超时错误处理

## 技术实现特性

- ✅ **参数类型验证**: 使用Pydantic Field注解进行严格验证
- ✅ **自动ID转换**: username自动解析为user_id
- ✅ **缓存机制**: 用户名解析和用户信息使用LRU缓存
- ✅ **字幕增强**: 自动检测AI生成字幕和多语言支持
- ✅ **动态类型筛选**: 真正的服务端类型过滤
- ✅ **错误恢复**: bvid缺失时自动从aid转换生成

---

> **最后更新**: 2025-09-16  
> **验证状态**: 所有功能已通过测试验证 ✅  
> **兼容性**: 保持向后兼容