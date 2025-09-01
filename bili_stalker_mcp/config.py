# Bilibili API and other configurations

# B站动态API URL
BILIBILI_DYNAMIC_API_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"

# 请求间隔时间（秒），用于避免API请求过于频繁
REQUEST_DELAY_MIN = 1.0  # 最小的延迟时间
REQUEST_DELAY_MAX = 3.0  # 最大的延迟时间（随机延迟范围）
REQUEST_DELAY = 1.5      # 默认延迟时间

# 代理配置 - 支持环境变量配置
PROXY_CONFIG = {
    'http': None,  # 可通过环境变量 HTTP_PROXY 设置
    'https': None,  # 可通过环境变量 HTTPS_PROXY 设置
}

# 网络超时配置
REQUEST_TIMEOUT = 30.0
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0

# 默认请求头 - 模拟真实浏览器请求（参考成功参考项目）
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
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
