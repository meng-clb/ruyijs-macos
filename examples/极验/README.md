# 极验一键通过模式

在项目根目录运行：

```powershell
python "examples/极验一键通过模式/geetest_fullpage.py" --proxy http://127.0.0.1:7890 --output geetest.json
```

也可进入本目录运行 `python geetest_fullpage.py`。默认依次检查代理环境变量、本机 7890，最后直连；
`--direct` 强制直连，`--timeout` 设置总期限（秒）。

页面 `https://demos.geetest.com/fullpage.html` 是极验 v3「一键通过」（fullpage）demo。流程与 Firefox trace
`jscall-detail-desktop-20261022-114517` 一致：页面 `gt/register-fullpage` 取 challenge，`gettype.php`/`get.php`
加载 fullpage.js；点击「点击按钮进行验证」后 `ajax.php` 判定：

- `result: success`：一键通过；
- `result: slide`（trace 与目前实测都是这一分支）：加载 slide.js 与拼图，拖动滑块后 `ajax.php` 返回 `validate`。

最后点击「提交」，页面 POST `gt/validate-fullpage` 做服务端二次校验。

缺口由求解端自己"看图"：另开一个 ruyijs Context（同源 `static.geetest.com`）取回 bg/fullbg/slice，用 `ImageDecoder`
解码，按 `restore_map.json`（slide.7.9.3 的 52 条 10×80 条带还原表，取自 trace 中的 getImageData/putImageData）
还原两张图，取差异最左列，减去拼图块自身的透明左边距即为拖动距离。挑战页面里不注入脚本、不替换浏览器 API、
不生成 `w` 参数；鼠标移动、按下、拖动、松开都是可信的 pointer/mouse 事件。

`passed: true` 与退出码 0 表示：验证码通过（一键或滑块），`validate-fullpage` HTTP 200，且提交后组件仍是「验证成功」
（服务端校验失败时 demo 会调用 `captchaObj.reset()` 让组件回到初始状态）、没有页面脚本异常。

已知差异：ruyijs 的 Canvas 2D `drawImage` 目前不绘制像素，页面里的拼图画布是空白的；slide.js 只用这些像素显示，
不参与提交，所以不影响验证，但这是一个待修的环境保真缺口。
