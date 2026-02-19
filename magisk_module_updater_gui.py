import os
import json
import threading
import queue
import tempfile
import shutil
import zipfile
import hashlib
import requests
from pathlib import Path
from tkinter import *
from tkinter import filedialog, messagebox, scrolledtext

# ---------- 核心更新逻辑（略作调整以支持回调输出）----------
def parse_prop_content(content):
    props = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    return props

def extract_module_prop_from_zip(zip_path):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for file_info in z.infolist():
                if file_info.filename.endswith('module.prop') and os.path.basename(file_info.filename) == 'module.prop':
                    with z.open(file_info) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        return parse_prop_content(content)
    except Exception as e:
        return None
    return None

def fetch_remote_json(update_json_url, timeout=10):
    try:
        response = requests.get(update_json_url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

def download_file(url, dest_path, timeout=30):
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception:
        return False

def process_module_zip(zip_path, backup, log_queue):
    """处理单个模块，通过 log_queue 发送消息"""
    def log(msg):
        log_queue.put(msg)

    log(f"检查: {zip_path}")
    props = extract_module_prop_from_zip(zip_path)
    if not props:
        log("  未找到 module.prop 或格式错误，跳过")
        return

    module_id = props.get('id')
    local_version_code = props.get('versionCode')
    update_json_url = props.get('updateJson')

    if not module_id:
        log("  缺少模块 id，跳过")
        return
    if not update_json_url:
        log(f"  模块 {module_id} 无 updateJson 字段，跳过")
        return
    if not local_version_code:
        log(f"  模块 {module_id} 无 versionCode 字段，跳过")
        return

    try:
        local_vc = int(local_version_code)
    except ValueError:
        log(f"  本地 versionCode 无效: {local_version_code}，跳过")
        return

    log(f"  模块ID: {module_id}, 本地版本: {local_vc}")
    remote_data = fetch_remote_json(update_json_url)
    if not remote_data:
        log(f"  获取远程信息失败: {update_json_url}")
        return

    remote_version_code = remote_data.get('versionCode')
    zip_url = remote_data.get('zipUrl')
    if not remote_version_code or not zip_url:
        log("  远程 JSON 缺少 versionCode 或 zipUrl")
        return

    try:
        remote_vc = int(remote_version_code)
    except ValueError:
        log(f"  远程 versionCode 无效: {remote_version_code}")
        return

    if remote_vc <= local_vc:
        log(f"  模块 {module_id} 已是最新 (本地 {local_vc} <= 远程 {remote_vc})")
        return

    log(f"  发现新版本: {remote_vc} > {local_vc}，开始下载...")
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
        tmp_path = tmp.name
    try:
        if not download_file(zip_url, tmp_path):
            log("  下载失败，跳过")
            return

        # 验证下载的模块 ID 是否匹配
        new_props = extract_module_prop_from_zip(tmp_path)
        if not new_props or new_props.get('id') != module_id:
            log("  下载的模块 ID 不匹配，中止")
            return

        if backup:
            backup_path = zip_path.with_suffix('.zip.bak')
            shutil.copy2(zip_path, backup_path)
            log(f"  备份已创建: {backup_path}")

        os.replace(tmp_path, zip_path)
        log(f"  更新成功: {zip_path} -> 版本 {remote_vc}")
    except Exception as e:
        log(f"  更新过程中出错: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def scan_and_update(directory, recursive, backup, log_queue):
    """扫描目录并将任务推入队列（此处直接调用，但在线程中运行）"""
    path = Path(directory)
    if not path.is_dir():
        log_queue.put(f"错误: {directory} 不是有效目录")
        return

    if recursive:
        zip_files = path.rglob('*.zip')
    else:
        zip_files = path.glob('*.zip')

    for zip_path in zip_files:
        process_module_zip(zip_path, backup, log_queue)
    log_queue.put("=== 全部处理完成 ===")

# ---------- GUI 部分 ----------
class MagiskUpdaterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Magisk 模块自动更新工具")
        self.root.geometry("700x500")
        self.root.resizable(True, True)

        # 配置持久化文件
        self.config_file = Path.home() / ".magisk_updater_config.json"
        self.config = self.load_config()

        # 变量
        self.folder_path = StringVar(value=self.config.get("last_directory", ""))
        self.recursive = BooleanVar(value=self.config.get("recursive", True))
        self.backup = BooleanVar(value=self.config.get("backup", True))

        # 创建界面
        self.create_widgets()

        # 日志队列和定时更新
        self.log_queue = queue.Queue()
        self.poll_log_queue()

        # 关闭时保存配置
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 文件夹选择
        frame_dir = LabelFrame(self.root, text="模块文件夹", padx=5, pady=5)
        frame_dir.pack(fill="x", padx=10, pady=5)

        self.entry_dir = Entry(frame_dir, textvariable=self.folder_path, width=60)
        self.entry_dir.pack(side=LEFT, padx=5, pady=5, fill="x", expand=True)

        btn_browse = Button(frame_dir, text="浏览...", command=self.browse_folder)
        btn_browse.pack(side=RIGHT, padx=5, pady=5)

        # 选项
        frame_options = LabelFrame(self.root, text="选项", padx=5, pady=5)
        frame_options.pack(fill="x", padx=10, pady=5)

        chk_recursive = Checkbutton(frame_options, text="递归扫描子目录", variable=self.recursive)
        chk_recursive.pack(anchor="w")

        chk_backup = Checkbutton(frame_options, text="更新前创建备份 (.zip.bak)", variable=self.backup)
        chk_backup.pack(anchor="w")

        # 开始按钮
        btn_start = Button(self.root, text="开始更新", command=self.start_update, bg="lightblue", height=2)
        btn_start.pack(pady=10)

        # 日志区域
        frame_log = LabelFrame(self.root, text="更新日志", padx=5, pady=5)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(frame_log, wrap=WORD, height=15)
        self.log_text.pack(fill="both", expand=True)

    def browse_folder(self):
        folder_selected = filedialog.askdirectory(initialdir=self.folder_path.get() or os.path.expanduser("~"))
        if folder_selected:
            self.folder_path.set(folder_selected)

    def log(self, message):
        """在主线程中向日志文本框追加消息"""
        self.log_text.insert(END, message + "\n")
        self.log_text.see(END)

    def poll_log_queue(self):
        """定期检查日志队列并更新GUI"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log(msg)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_log_queue)

    def start_update(self):
        folder = self.folder_path.get().strip()
        if not folder:
            messagebox.showerror("错误", "请先选择模块文件夹")
            return
        if not Path(folder).is_dir():
            messagebox.showerror("错误", "选择的文件夹无效")
            return

        # 保存当前配置（下次启动时自动加载）
        self.save_config()

        # 清空旧日志
        self.log_text.delete(1.0, END)
        self.log(f"开始扫描文件夹: {folder}")
        self.log(f"递归: {self.recursive.get()}, 备份: {self.backup.get()}")
        self.log("正在检查更新，请稍候...\n")

        # 在后台线程中执行更新，避免阻塞GUI
        def task():
            scan_and_update(
                directory=folder,
                recursive=self.recursive.get(),
                backup=self.backup.get(),
                log_queue=self.log_queue
            )

        thread = threading.Thread(target=task, daemon=True)
        thread.start()

    def load_config(self):
        """加载配置文件，不存在则返回默认值"""
        default = {
            "last_directory": "",
            "recursive": True,
            "backup": True
        }
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保键都存在
                    for key in default:
                        if key not in data:
                            data[key] = default[key]
                    return data
            except Exception:
                return default
        return default

    def save_config(self):
        """保存当前设置到配置文件"""
        config = {
            "last_directory": self.folder_path.get(),
            "recursive": self.recursive.get(),
            "backup": self.backup.get()
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def on_closing(self):
        """关闭窗口时保存配置并退出"""
        self.save_config()
        self.root.destroy()

if __name__ == "__main__":
    root = Tk()
    app = MagiskUpdaterGUI(root)
    root.mainloop()
