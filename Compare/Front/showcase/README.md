# 见微前端展示页

`Show/` 文件夹就是完整的独立前端交付物。复制整个文件夹即可带走，不需要同时复制 `Front/` 或 `Back/`。入口包含登录页、项目池和一套完整的脱敏演示材料。

- `见微-前端展示页.html`：真正的单文件版，程序、样式和展示图片都已内嵌；只发送这一份即可。默认账号为 `business`，密码为 `123456`。
- `mock-materials/`、`reference-images/`：仅供静态服务器版本使用，单文件版不依赖它们。
- `index.html`、`assets/`：用于静态服务器或网站托管的版本。

如果浏览器限制直接打开本地 HTML，可在 `Show/` 目录启动任意静态文件服务器：

```powershell
C:\Users\22673\Desktop\JW\Back\.venv\Scripts\python.exe -m http.server 4321 --bind 127.0.0.1
```

然后打开 `http://127.0.0.1:4321/`。

重新生成展示包：

```powershell
cd C:\Users\22673\Desktop\JW\Compare\Front
npm.cmd run showcase:build
```
