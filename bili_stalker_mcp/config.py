# Bilibili API and other configurations

# B站动态API URL
BILIBILI_DYNAMIC_API_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"

# 请求间隔时间（秒），用于避免API请求过于频繁
REQUEST_DELAY_MIN = 0.5  # 最小的延迟时间
REQUEST_DELAY_MAX = 1.5  # 最大的延迟时间（随机延迟范围）
REQUEST_DELAY = 1.5      # 默认延迟时间

# 代理配置 - 支持环境变量配置
PROXY_CONFIG = {
    'http': None,  # 可通过环境变量 HTTP_PROXY 设置
    'https': None,  # 可通过环境变量 HTTPS_PROXY 设置
}

# 网络超时配置
REQUEST_TIMEOUT = 60.0
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 45.0

# 默认请求头 - 模拟真实浏览器请求（参考成功项目，使用Chrome/91）
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

# 请求流控配置
REQUEST_CONFIG = {
    'min_delay': 1.0,    # 最小请求间隔(秒)
    'max_delay': 3.0,    # 最大请求间隔(秒)
    'max_retries': 3,    # 最大重试次数
    'backoff_factor': 2.0,  # 重试退避系数
}

# 认证配置 - 多级支持，便于降级
AUTH_CONFIG = {
    'min_credentials': ['sessdata'],  # 最低要求
    'recommended_credentials': ['sessdata', 'bili_jct'],  # 推荐配置
    'full_credentials': ['sessdata', 'bili_jct', 'buvid3']  # 完整配置
}

# 动态类型常量
class DynamicType:
    ALL = "ALL"
    VIDEO = "VIDEO"
    ARTICLE = "ARTICLE"
    ANIME = "ANIME"
    DRAW = "DRAW"
    # 移除不支持的TEXT类型，更新为实际支持的类型
    VALID_TYPES = [ALL, VIDEO, ARTICLE, ANIME, DRAW]
    
    # 动态类型映射（用于API调用）
    TYPE_MAPPINGS = {
        ALL: "all",
        VIDEO: "8",     # 视频动态
        ARTICLE: "64",  # 专栏动态  
        ANIME: "512",   # 番剧动态
        DRAW: "2"       # 图文动态
    }

# 资源URI模板
SCHEMAS_URI = "bili://schemas"
