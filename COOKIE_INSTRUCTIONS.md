# B站凭证配置说明

BiliStalkerMCP支持两种方式配置B站凭证：

## 方法1：使用环境变量（推荐用于生产环境）

在运行项目之前，设置以下环境变量：

```bash
export SESSDATA="your_sessdata_value"
export BILI_JCT="your_bili_jct_value"
export BUVID3="your_buvid3_value"
```

或者在Windows上：

```cmd
set SESSDATA=your_sessdata_value
set BILI_JCT=your_bili_jct_value
set BUVID3=your_buvid3_value
```

## 方法2：使用BILI_COOKIE.txt文件（推荐用于开发和测试）

1. 在项目根目录下创建`BILI_COOKIE.txt`文件
2. 将您的B站cookie信息按以下格式写入文件：

```
buvid3=your_buvid3_value; b_nut=...; _uuid=...; SESSDATA=your_sessdata_value; bili_jct=your_bili_jct_value; DedeUserID=...;
```

注意：确保文件末尾没有多余的字符或换行符。

## 如何获取B站凭证

1. 登录B站网站
2. 打开浏览器开发者工具（F12）
3. 切换到Application/存储标签页
4. 在左侧Cookies中找到https://www.bilibili.com
5. 复制以下cookie的值：
   - SESSDATA
   - bili_jct
   - buvid3

## 凭证优先级

项目会按以下优先级读取凭证：

1. 环境变量（最高优先级）
2. BILI_COOKIE.txt文件
3. 如果都不存在则无法运行

## 安全提醒

- 不要将包含真实凭证的文件提交到版本控制系统
- 定期更新您的凭证以确保安全
- BILI_COOKIE.txt已添加到.gitignore中，不会被意外提交