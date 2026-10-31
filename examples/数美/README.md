# 数美滑动验证码

在项目根目录运行：

```powershell
python "examples/数美/shumei.py" --proxy http://127.0.0.1:7890 --output shumei.json
```

也可进入本目录运行 `python shumei.py`。默认依次检查代理环境变量、本机 7890，最后直连；`--direct` 强制直连，
`--timeout` 设置总期限（秒，默认 60），`--attempts` 设置被拒时最多尝试的次数（默认 3）。一次运行约 30 秒，其中页面加载约 20 秒。

页面是数美官网注册页 `https://www.ishumei.com/account/register.html`。流程与 Firefox trace
`jscall-detail-desktop-20261022-130216` 一致：`smcp.min.js` -> `ca/v1/conf` -> `fp.min.js` 设备指纹
（`fp-it.portal101.cn/deviceprofile/v4`）-> `captcha-sdk.min.js` -> `ca/v1/register`（背景 600x300、拼图块 90x300）->
鼠标移到滑块上（拼图在悬停时显示）、按下、拖动、松开 -> `ca/v2/fverify`。

求解端只做人会做的事：

- **看图**：另开一个同源（`castatic.fengkongcloud.cn`）的 ruyijs Context，取回 bg/fg，用 `ImageDecoder` 解码。缺口是盖在
  原图上的一层半透明白色，形状、高度与拼图块相同（背景里还有一个高度不同的假缺口）。把拼图块的形状放在它自己那几行上横向
  滑动，取“形状内平均亮度 - 外圈平均亮度”最大的位置。页面显示比例是 0.5（300/600）。
- **拖动**：按真实时间进行。SDK 在按下后每 100 ms 采样一次指针位置，得到 `[dx, dy, t]` 轨迹。拖动约 0.5 s 快速滑到缺口前，
  约 0.8 s 慢慢靠上，读取页面上拼图块的位置对准后停留 0.2–0.45 s 再松开，整体约 2 s，与 trace 中通过的那次（2.26 s，
  末段缓慢修正后停住）相当。

脚本不注入脚本、不替换浏览器 API、不生成 fverify 参数；鼠标事件都是可信的 pointer/mouse 事件。

`passed: true` 与退出码 0 表示 fverify 返回 `riskLevel: PASS`（滑轨显示 `slide_success`“验证成功”），并且没有数美脚本异常。
`attempts` 中记录了每次的缺口位置（`gapX`，背景像素）、目标位置（`goal`，显示像素）、松开时拼图块的位置（`releasedAt`）、
拖动步数，以及滑轨状态（`widget`）。

`scriptErrors` 里 `safe.cdn.bcebos.com/js/dfxaf3.js`、`affim.js` 的异常来自页面嵌入的百度脚本，与数美无关。

## 跑通过程中定位的问题

- **拖动节奏**：早先每一步都按固定的 `advance` 毫秒数推进，但每次分发事件的真实开销约 140 ms，一次拖动实际用了 8 秒，轨迹
  明显不像人，即使位置准确也会被判 `slide_fail`。改为按真实时钟计算位置后通过。
- **frame 里的同步脚本获取**：360 统计 iframe 插入的 JSONP 请求指向解析到 127.0.0.1 的主机，经代理时隧道建立后又被关闭，
  Necko 会重试到 15 秒预算用完；frame 中动态脚本原先同步获取，主线程每个脚本卡 15 秒，宿主管道超时。现在 frame 用自己的
  请求上下文在后台获取；失败的预加载直接作为该元素的 `error`，不再同步重新请求。
- **Necko helper 池**：原先整个进程最多 6 个 helper（Firefox 的 6 是每个服务器的上限）。几个耗满预算的请求占满了 helper，
  `captcha-sdk.min.js` 等不到 helper 而失败。现在最多 18 个，每个 origin 最多 6 个。
- **样式表重复解析**：`fp.min.js` 的字体探测每改一次字体就读一次 `offsetWidth`，每次都重新解析全部 1711 条规则。现在按内容
  指纹复用解析结果（7.9 s -> 6.6 s）。剩余开销是每次读取都整页重算样式和盒布局，记为债务。
