# 网易易盾

在项目根目录运行：

```powershell
python "examples/网易易盾/yidun.py" --proxy http://127.0.0.1:7890 --output yidun.json
```

也可进入本目录运行 `python yidun.py`。默认依次检查代理环境变量、本机 7890，最后直连；
`--direct` 强制直连，`--timeout` 设置总期限（秒）。

页面是网易易盾控制台登录 `https://dun.163.com/dashboard#/login/`，登录表单在 `id.zhiqi.163.com/sdk-login` 的 iframe 里，
其中嵌着易盾「智能无感」验证。流程与 Firefox trace `jscall-detail-desktop-20261022-115900` 一致：
`/s/ngt`、`/auth/urs` -> 易盾 `load.min.js` -> `c.dun.163.com/api/v2/getconf` -> `ir-sdk.dun.163.com/v4/j/up`（设备指纹）->
`/api/v3/get`（type 5 智能无感）-> 鼠标移到并点击「点击完成验证」-> `/api/v3/check`。

trace 中这次 check 判为 false，降级为滑块拼图（type 2）后才通过；ruyijs 中智能检测直接通过（连续多次实测均如此）。
脚本只导航、移动鼠标并点击按钮，不注入脚本、不替换浏览器 API、不生成 check 参数。若易盾降级为滑块拼图，脚本以
`fallback: "slide"` 失败退出（拼图求解未实现）。

`passed: true` 与退出码 0 表示 `/api/v3/check` HTTP 200、组件提示「验证成功」、iframe 里的 `NECaptchaValidate`
拿到 validate（输出只给出长度）。trace 中没有提交账号密码，本示例同样只到拿到 validate 为止。

`scriptErrors` 里的 `Storage.setItem requires a key and value` 来自页面的 music-corona 以单个参数调用 `setItem`，
在 Firefox 中同样抛错（文字为 `Storage.setItem: At least 2 arguments required, but only 1 passed`），不影响验证。

为跑通此页面修复的产品缺口：ruyijs 原先没有 XML 解析器，`DOMParser` 的 XML 媒体类型走 HTML 语法，控制台的 SVG 雪碧图
（`parseFromString(..., "image/svg+xml")`）因此抛 `NamespaceError`，应用启动中断、登录框不出现。现在 Document Model 有了
XML 1.0 + Namespaces 解析器（偏离 D138）。
