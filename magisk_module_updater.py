import os
import zipfile
import json
import tempfile
import shutil
import requests
from pathlib import Path
from urllib.parse import urlparse
import hashlib

def extract_module_prop_from_zip(zip_path):
    """
    从 Magisk 模块 ZIP 中提取 module.prop 的内容，并解析为字典。
    返回 None 如果未找到或解析失败。
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            # 查找 module.prop 文件（可能在根目录或子目录，但通常就在根目录）
            for file_info in z.infolist():
                if file_info.filename.endswith('module.prop'):
                    # 只考虑文件名为 module.prop 的，避免路径中包含的
                    if os.path.basename(file_info.filename) == 'module.prop':
                        with z.open(file_info) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            return parse_prop_content(content)
    except Exception as e:
        print(f"Error reading {zip_path}: {e}")
    return None

def parse_prop_content(content):
    """解析 module.prop 键值对，返回字典"""
    props = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    return props

def fetch_remote_json(update_json_url):
    """
    从 updateJson URL 获取 JSON 内容，返回解析后的字典。
    失败返回 None。
    """
    try:
        response = requests.get(update_json_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to fetch {update_json_url}: {e}")
        return None

def download_file(url, dest_path):
    """下载文件到指定路径，返回是否成功"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def get_zip_hash(zip_path):
    """计算文件的 SHA256 哈希，用于校验"""
    sha256 = hashlib.sha256()
    with open(zip_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def process_module_zip(zip_path, backup=True):
    """
    处理单个模块 ZIP 文件。
    如果有更新，下载新版本并替换原文件（可备份）。
    """
    print(f"Checking {zip_path} ...")
    props = extract_module_prop_from_zip(zip_path)
    if not props:
        print("  No module.prop found or invalid.")
        return

    # 必须字段
    module_id = props.get('id')
    local_version_code = props.get('versionCode')
    update_json_url = props.get('updateJson')

    if not module_id:
        print("  Missing module id, skip.")
        return
    if not update_json_url:
        print(f"  No updateJson for module {module_id}, skip.")
        return
    if not local_version_code:
        print(f"  No versionCode for module {module_id}, skip.")
        return

    # 转换为整数进行比较
    try:
        local_vc = int(local_version_code)
    except ValueError:
        print(f"  Invalid local versionCode: {local_version_code}, skip.")
        return

    print(f"  Module ID: {module_id}, local version: {local_vc}")
    print(f"  Update URL: {update_json_url}")

    # 获取远程信息
    remote_data = fetch_remote_json(update_json_url)
    if not remote_data:
        return
    remote_version_code = remote_data.get('versionCode')
    zip_url = remote_data.get('zipUrl')
    if not remote_version_code or not zip_url:
        print(f"  Remote JSON missing versionCode or zipUrl.")
        return

    try:
        remote_vc = int(remote_version_code)
    except ValueError:
        print(f"  Invalid remote versionCode: {remote_version_code}, skip.")
        return

    # 版本比较
    if remote_vc <= local_vc:
        print(f"  Module {module_id} is up-to-date (local: {local_vc}, remote: {remote_vc}).")
        return

    print(f"  New version available: {remote_vc} > {local_vc}. Downloading...")

    # 创建临时文件下载
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
        tmp_path = tmp.name
    try:
        success = download_file(zip_url, tmp_path)
        if not success:
            print(f"  Download failed, skip.")
            return

        # 可选：检查下载的 zip 是否包含正确的 module.prop 且 id 匹配
        new_props = extract_module_prop_from_zip(tmp_path)
        if not new_props or new_props.get('id') != module_id:
            print(f"  Downloaded zip does not match module ID {module_id}, abort.")
            return

        # 备份旧文件（如果启用）
        if backup:
            backup_path = zip_path.with_suffix('.zip.bak')
            shutil.copy2(zip_path, backup_path)
            print(f"  Backup created: {backup_path}")

        # 替换原文件
        os.replace(tmp_path, zip_path)
        print(f"  Updated {zip_path} to version {remote_vc}")

    except Exception as e:
        print(f"  Error during update: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def scan_and_update(directory, recursive=True, backup=True):
    """
    扫描目录下的所有 ZIP 文件，尝试更新。
    """
    path = Path(directory)
    if not path.is_dir():
        print(f"Error: {directory} is not a directory.")
        return

    # 收集所有 .zip 文件
    if recursive:
        zip_files = path.rglob('*.zip')
    else:
        zip_files = path.glob('*.zip')

    for zip_path in zip_files:
        process_module_zip(zip_path, backup=backup)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Auto update Magisk module zip files.')
    parser.add_argument('directory', help='Directory containing module zip files')
    parser.add_argument('--no-recursive', action='store_false', dest='recursive',
                        help='Do not scan subdirectories')
    parser.add_argument('--no-backup', action='store_false', dest='backup',
                        help='Do not create backup files')
    args = parser.parse_args()

    scan_and_update(args.directory, recursive=args.recursive, backup=args.backup)
