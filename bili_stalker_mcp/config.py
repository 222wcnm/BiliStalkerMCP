# Bilibili API and other configurations

# B站动态API URL
BILIBILI_DYNAMIC_API_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"

# 请求间隔时间（秒），用于避免API请求过于频繁
REQUEST_DELAY = 0.3

# 默认请求头
DEFAULT_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Origin': 'https://www.bilibili.com',
}

# 动态类型常量
class DynamicType:
    ALL = "ALL"
    VIDEO = "VIDEO"
    ARTICLE = "ARTICLE"
    ANIME = "ANIME"
    DRAW = "DRAW"
    VALID_TYPES = [ALL, VIDEO, ARTICLE, ANIME, DRAW]

# 资源URI模板
SCHEMAS_URI = "bili://schemas"
