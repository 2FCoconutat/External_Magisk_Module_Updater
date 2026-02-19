# External_Magisk_Module_Updater
Auto update Magisk module package
##Magisk 模块自动更新工具 v1.0.0

这是 Magisk 模块自动更新工具的第一个正式版本 🎉

###  主要功能

- 图形界面批量管理 Magisk 模块
- 基于 `updateJson` 自动检查更新
- 支持递归扫描和自动备份
- 配置持久化，记住上次设置
- 实时显示更新日志

### 📥 下载

-Windows **[Magisk模块自动更新工具.exe](链接)** - 便携版，直接运行
  

### 🔧 系统要求

- Windows 不知道哪个版本
 
### ⚠️ 注意事项

- 确保模块文件夹中有正确的 Magisk 模块 ZIP 文件
- 包含 `updateJson` 字段的模块才能自动更新
- 首次运行会创建配置文件 `~/.magisk_updater_config.json`

### 📝 更新日志

#### v1.0.0 (2024-xx-xx)
- ✨ 初始版本发布
- 🎨 实现基本的 GUI 界面
- 🔧 完成模块扫描和更新核心功能
- 💾 添加配置持久化
- 📊 添加实时日志显示
