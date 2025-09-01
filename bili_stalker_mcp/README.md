# BiliStalkerMCP

## 🎯 项目功能

BiliStalkerMCP 是一个基于 MCP (Model Context Protocol) 的服务，允许AI模型通过标准化协议获取指定Bilibili用户的最新视频和动态更新。

### 🛠️ 工具功能

#### get_user_video_updates
获取用户视频更新信息

**参数**:
- `user_id` (int, 可选): 用户ID
- `username` (str, 可选): 用户名
- `limit` (int, 可选): 返回数量，默认10，最大50

#### get_user_dynamic_updates
获取用户动态更新信息

**参数**:
- `user_id` (int, 可选): 用户ID  
- `username` (str, 可选): 用户名
- `limit` (int, 可选): 返回数量，默认10，最大50
- `dynamic_type` (str, 可选): 动态类型过滤

### 📁 资源支持

#### 用户信息资源
- URI: `bili://user/{user_id}/info`
- 获取用户基本信息

#### 用户视频资源
- URI: `bili://user/{user_id}/videos?limit={limit}`
- 获取用户视频列表

#### 用户动态资源
- URI: `bili://user/{user_id}/dynamics?type={type}&limit={limit}`
- 获取用户动态更新

## 🚀 使用方法

### 工具调用
```python
# 获取用户视频更新
get_user_video_updates(user_id=123456, limit=10)

# 获取用户动态更新  
get_user_dynamic_updates(username="UP主名字", limit=20, dynamic_type="VIDEO")
```

### 资源访问
```python
# 通过URI直接访问资源
read_resource("bili://user/123456/info")
read_resource("bili://user/123456/videos?limit=10")
read_resource("bili://user/123456/dynamics?type=VIDEO&limit=20")
```

## ✨ 特性

- 支持用户ID或用户名查询
- 智能用户搜索匹配
- 动态类型过滤（视频、文章、番剧）
- 统一的错误处理和返回格式
- 资源和工具双重访问方式
