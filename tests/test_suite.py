import os
import sys
import json
import logging
import argparse
import asyncio
from pathlib import Path

# 将项目根目录添加到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bili_stalker_mcp import core

# --- 配置日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BiliStalkerTestSuite")

def load_credentials():
    """
    从 BILI_COOKIE.txt 或环境变量加载凭证。
    文件优先。
    """
    cookie_file_path = project_root / 'BILI_COOKIE.txt'
    
    try:
        with open(cookie_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        import re
        cookie_pairs = re.findall(r'([^=;]+)=([^;]*)', content)
        for key, value in cookie_pairs:
            key_upper = key.strip().upper()
            if key_upper in ['SESSDATA', 'BILI_JCT', 'BUVID3']:
                os.environ[key_upper] = value.strip()
                logger.info(f"从文件加载凭证: {key_upper}")
        
    except FileNotFoundError:
        logger.warning(f"未找到 {cookie_file_path}，将尝试从环境变量加载。")
    except Exception as e:
        logger.error(f"读取凭证文件时出错: {e}")

    sessdata = os.environ.get("SESSDATA")
    bili_jct = os.environ.get("BILI_JCT")
    buvid3 = os.environ.get("BUVID3")

    if not all([sessdata, bili_jct, buvid3]):
        logger.error("凭证不完整 (SESSDATA, BILI_JCT, BUVID3 都需要)。请检查 BILI_COOKIE.txt 或环境变量。")
        return None
        
    # 类型断言：这里我们已经确认了所有凭证都不为 None
    assert sessdata is not None and bili_jct is not None and buvid3 is not None
    return core.get_credential(sessdata, bili_jct, buvid3)

async def test_user_info(cred, user_id, username):
    """测试用户信息获取"""
    logger.info("--- 测试: 获取用户信息 ---")
    target_uid = user_id or await core.get_user_id_by_username(username)
    if not target_uid:
        logger.error(f"找不到用户 '{username or user_id}'")
        return None

    user_info = await core.fetch_user_info(target_uid, cred)
    if "error" in user_info:
        logger.error(f"获取用户信息失败: {user_info['error']}")
        return None
    
    logger.info(f"成功获取用户 '{user_info['name']}' (ID: {user_info['mid']}) 的信息。")
    logger.info(f"  - 粉丝: {user_info.get('follower')}, 关注: {user_info.get('following')}")
    return target_uid

async def test_videos(cred, user_id, limit):
    """测试视频和字幕获取"""
    logger.info(f"--- 测试: 获取最新 {limit} 个视频 ---")
    video_result = await core.fetch_user_videos(user_id, 1, limit, cred)
    if "error" in video_result:
        logger.error(f"获取视频失败: {video_result['error']}")
        return

    videos = video_result.get("videos", [])
    logger.info(f"成功获取 {len(videos)} 个视频。")
    
    for video in videos:
        bvid = video.get('bvid', 'None')
        aid = video.get('aid', 'None')
        subtitle_info = video.get('subtitle', {})
        has_subtitle = subtitle_info.get('has_subtitle', False)
        subtitle_count = subtitle_info.get('subtitle_count', 0)
        
        logger.info(f"  - [视频] {video['title']}")
        logger.info(f"    BVID: {bvid}, AID: {aid}")
        logger.info(f"    字幕: {has_subtitle} (数量: {subtitle_count})")
        logger.info(f"    URL: {video.get('url', 'None')}")

async def test_dynamics(cred, user_id, limit):
    """测试动态获取和解析"""
    logger.info(f"--- 测试: 获取最新 {limit} 条动态 (所有类型) ---")
    dynamics_result = await core.fetch_user_dynamics(user_id, 0, limit, cred, dynamic_type="ALL")
    if "error" in dynamics_result:
        logger.error(f"获取动态失败: {dynamics_result['error']}")
        return

    dynamics = dynamics_result.get("dynamics", [])
    logger.info(f"成功获取 {len(dynamics)} 条动态。")

    for dynamic_item in dynamics:
        dynamic_type = dynamic_item.get('type', 'UNKNOWN')
        type_id = dynamic_item.get('type_id', 'N/A')
        text = dynamic_item.get('text_content', '(无文本)')
        text_preview = text.replace('\n', ' ').strip()[:30] + "..." if text != '(无文本)' else "(无文本)"
        
        logger.info(f"  - [动态] 类型: {dynamic_type} (ID: {type_id}), 内容: {text_preview}")
        
        # 显示特殊字段
        if 'images' in dynamic_item:
            images_count = len(dynamic_item['images'])
            logger.info(f"    图片数量: {images_count}")
        if 'video' in dynamic_item:
            video_info = dynamic_item['video']
            logger.info(f"    视频: {video_info.get('title', 'N/A')} (BVID: {video_info.get('bvid', 'N/A')})")
        if 'error' in dynamic_item:
            logger.warning(f"    解析错误: {dynamic_item['error']}")

async def test_articles(cred, user_id, limit):
    """测试专栏文章获取"""
    logger.info(f"--- 测试: 获取最新 {limit} 篇专栏文章 ---")
    article_result = await core.fetch_user_articles(user_id, 1, limit, cred)
    if "error" in article_result:
        logger.error(f"获取专栏文章失败: {article_result['error']}")
        return

    articles = article_result.get("articles", [])
    logger.info(f"成功获取 {len(articles)} 篇文章。")
    for article in articles:
        logger.info(f"  - [文章] {article['title']}")

async def test_followings(cred, user_id, limit):
    """测试关注列表获取"""
    logger.info(f"--- 测试: 获取最新 {limit} 个关注 ---")
    followings_result = await core.fetch_user_followings(user_id, 1, limit, cred)
    if "error" in followings_result:
        if "隐私" in followings_result['error']:
            logger.warning(f"获取关注列表失败: {followings_result['error']}")
        else:
            logger.error(f"获取关注列表失败: {followings_result['error']}")
        return


    followings = followings_result.get("followings", [])
    logger.info(f"成功获取 {len(followings)} 个关注。")
    for following in followings:
        logger.info(f"  - [关注] {following['uname']}")

async def main():
    parser = argparse.ArgumentParser(description="BiliStalkerMCP 测试套件")
    parser.add_argument("-u", "--user", help="要测试的用户名或用户ID", default="35847683")
    parser.add_argument("-l", "--limit", type=int, help="获取内容的数量限制", default=10)
    parser.add_argument("-t", "--tests", nargs='+', help="指定要运行的测试模块 (all, user, video, dynamic, article, followings)", default=["all"])
    args = parser.parse_args()

    cred = load_credentials()
    if not cred:
        sys.exit(1)

    user_input = args.user
    user_id = None
    username = None
    if user_input.isdigit():
        user_id = int(user_input)
        logger.info(f"输入被识别为用户ID: {user_id}")
    else:
        username = user_input
        logger.info(f"输入被识别为用户名: {username}")

    run_all = "all" in args.tests

    target_uid = await test_user_info(cred, user_id, username)
    if not target_uid:
        sys.exit(1)

    if run_all or "video" in args.tests:
        await test_videos(cred, target_uid, args.limit)

    if run_all or "dynamic" in args.tests:
        await test_dynamics(cred, target_uid, args.limit)

    if run_all or "article" in args.tests:
        await test_articles(cred, target_uid, args.limit)

    if run_all or "followings" in args.tests:
        await test_followings(cred, target_uid, args.limit)

    logger.info("--- 测试套件运行完毕 ---")

if __name__ == "__main__":
    asyncio.run(main())
