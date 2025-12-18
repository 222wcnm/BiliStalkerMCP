# Bilibili API and other configurations

# 默认请求头 - 模拟真实浏览器请求（针对云环境优化反爬策略）
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'sec-ch-ua': '"Google Chrome";v="131", "Not=A?Brand";v="8", "Chromium";v="131"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua-model': '""',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-bitness': '"64"',
    'sec-ch-ua-full-version-list': '"Google Chrome";v="131.0.0.0", "Not=A?Brand";v="8.0.0.0", "Chromium";v="131.0.0.0"',
    'Upgrade-Insecure-Requests': '1',
    'Connection': 'keep-alive',
    'DNT': '1',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'sec-gpc': '1',
}

# 请求间隔时间（秒），用于避免API请求过于频繁
REQUEST_DELAY = 3.0

# 网络超时配置
REQUEST_TIMEOUT = 60.0
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 45.0

# 动态类型常量
class DynamicType:
    ALL = "ALL"
    VIDEO = "VIDEO"
    ARTICLE = "ARTICLE"
    ANIME = "ANIME"
    DRAW = "DRAW"
    VALID_TYPES = [ALL, VIDEO, ARTICLE, ANIME, DRAW]
    
    # 动态类型映射（用于API调用）
    TYPE_MAPPINGS = {
        ALL: "all",
        VIDEO: "8",     # 视频动态
        ARTICLE: "64",  # 专栏动态  
        ANIME: "512",   # 番剧动态
        DRAW: "2"       # 图文动态
    }

