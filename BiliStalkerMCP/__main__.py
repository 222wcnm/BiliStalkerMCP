import os
from typing import Any, Dict
from bilibili_api import user, sync, Credential, search
from bilibili_api.exceptions import ApiException
from mcp.server.fastmcp import FastMCP

# 从环境变量中获取SESSDATA
SESSDATA = os.environ.get("SESSDATA", "")
BILI_JCT = os.environ.get("BILI_JCT", "")
BUVID3 = os.environ.get("BUVID3", "")

# 创建凭证对象
cred = Credential(
    sessdata=SESSDATA,
    bili_jct=BILI_JCT,
    buvid3=BUVID3
)

mcp = FastMCP("BiliStalkerMCP")

@mcp.tool()
def get_user_video_updates(user_id: int = None, username: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    获取指定B站用户的最新视频更新信息。
    可以通过 user_id 或 username 指定用户。
    
    Args:
        user_id: B站用户ID (user_id 和 username 必须提供一个)
        username: B站用户名 (当提供 user_id 时，此项将被忽略)
        limit: 获取视频数量限制（默认10，最大50）
        
    Returns:
        包含用户和视频信息的字典
    """
    if not SESSDATA:
        return {"error": "SESSDATA environment variable is not set."}
        
    if not user_id and not username:
        return {"error": "Either user_id or username must be provided."}

    if not (1 <= limit <= 50):
        return {"error": "Limit must be between 1 and 50."}

    try:
        target_uid = user_id
        if not target_uid and username:
            # 如果只提供了用户名，则通过搜索获取 UID（使用按类型搜索，用户类型）
            search_result = sync(search.search_by_type(
                keyword=username,
                search_type=search.SearchObjectType.USER,
                order_type=search.OrderUser.FANS
            ))
            # 兼容不同版本返回结构，提取用户列表
            result_list = None
            if isinstance(search_result, dict):
                if 'result' in search_result and isinstance(search_result['result'], list):
                    result_list = search_result['result']
                elif 'data' in search_result and isinstance(search_result['data'], dict) and isinstance(search_result['data'].get('result'), list):
                    result_list = search_result['data']['result']
            if not result_list:
                return {"error": f"User '{username}' not found."}
            
            # 筛选出完全匹配的用户
            exact_match = [u for u in result_list if u.get('uname') == username]
            if len(exact_match) == 1:
                target_uid = exact_match[0]['mid']
            elif len(exact_match) > 1:
                return {"error": f"Multiple users found with the exact name '{username}'. Please use user_id."}
            else:
                # 如果没有精确匹配，可以考虑返回最相关的用户或错误
                return {"error": f"No exact match for user '{username}' found."}

        if not target_uid:
             return {"error": "Failed to determine user_id."}

        # 创建用户对象
        u = user.User(uid=target_uid, credential=cred)
        
        # 获取用户信息
        user_info = sync(u.get_user_info())
        
        # 获取视频列表
        video_list = sync(u.get_videos(ps=limit))
        
        # 处理视频列表，确保包含 bvid 和 url
        raw_videos = video_list.get("list", {}).get("vlist", [])
        processed_videos = []
        for video in raw_videos:
            processed_video = {
                "bvid": video.get("bvid"),
                "aid": video.get("aid"),
                "title": video.get("title"),
                "description": video.get("description"),
                "created": video.get("created"),
                "length": video.get("length"),
                "pic": video.get("pic"),
                "play": video.get("play"),
                "favorites": video.get("favorites"),
                "author": video.get("author"),
                "mid": video.get("mid"),
                # 构造完整 URL
                "url": f"https://www.bilibili.com/video/{video.get('bvid')}" if video.get('bvid') else None
            }
            processed_videos.append(processed_video)

        return {
            "user": {
                "mid": user_info.get("mid"),
                "name": user_info.get("name"),
                "face": user_info.get("face"),
                "sign": user_info.get("sign"),
                "level": user_info.get("level"),
            },
            "videos": processed_videos,
            "total": video_list.get("page", {}).get("count", 0)
        }
    except ApiException as e:
        return {"error": f"Bilibili API Error: {e.msg}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}

def main():
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
