# 网上房地产

在项目根目录运行：

```powershell
python "examples/网上房地产/fangdi.py" --proxy http://127.0.0.1:7890 --html fangdi_home.html
```

也可进入本目录运行 `python fangdi.py`。默认依次检查代理环境变量、本机 7890，最后直连；
`--direct` 强制直连，`--timeout 60` 设置总期限。

脚本使用项目自带的 Python 绑定和 `dist/js.exe`，由原生运行时执行当前挑战、维护 cookie，
然后用同一会话再次获取首页。无需第三方 Python 包或 trace 文件。

`passed: true` 和退出码 0 表示最终首页 HTTP 200、标题为“网上房地产”且含链接。
`homepageStatuses` 可查看 412 → 200 的过程；`scriptErrors` 单独记录页面脚本异常。
`--html` 保存服务器返回的完整 HTML，`--dom` 可另存执行脚本后的 DOM。
输出只显示 cookie 名称。`RUYIJS_SHELL` 可指定另一份运行时。
