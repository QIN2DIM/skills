#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "pyyaml",
# ]
# ///
"""
Clash-Meta 配置自动更新脚本

自动完成以下操作：
1. 备份配置文件
2. 读取 .proxies.yaml 并更新 config.yaml 的 proxies
3. 核验并清理 proxy-groups 中的失效代理
4. 输出 diff 供确认

使用方法:
    uv run scripts/update_clash_config.py

或使用 shebang:
    ./scripts/update_clash_config.py
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: uv pip install pyyaml", file=sys.stderr)
    sys.exit(1)


WORK_DIR = Path(".")
CONFIG_FILE = WORK_DIR / "config.yaml"
PROXIES_FILE = WORK_DIR / ".proxies.yaml"
BACKUP_FILE = WORK_DIR / "config.yaml.bak"
EDITING_FILE = WORK_DIR / "config.yaml.editing"


def load_yaml(path: Path) -> dict:
    """安全加载 YAML 文件"""
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    
    content = path.read_text(encoding='utf-8')
    return yaml.safe_load(content) or {}


def save_yaml(data: dict, path: Path) -> None:
    """保存 YAML 文件，保留格式"""
    yaml.add_representer(
        type(None),
        lambda self, _: self.represent_scalar('tag:yaml.org,2002:null', '')
    )
    
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=1000
        )


def backup_config() -> None:
    """创建配置备份"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_with_ts = WORK_DIR / f"config.yaml.bak.{timestamp}"
    
    shutil.copy2(CONFIG_FILE, BACKUP_FILE)
    shutil.copy2(CONFIG_FILE, backup_with_ts)
    shutil.copy2(CONFIG_FILE, EDITING_FILE)
    
    print(f"✓ 已备份: {BACKUP_FILE.name}")
    print(f"✓ 已备份(带时间戳): {backup_with_ts.name}")
    print(f"✓ 编辑文件: {EDITING_FILE.name}")


def update_proxies(config: dict, new_proxies: list) -> dict:
    """用新代理列表覆盖 config 中的 proxies"""
    old_count = len(config.get('proxies', []))
    new_count = len(new_proxies)
    
    config['proxies'] = new_proxies
    
    print(f"\n✓ Proxies 已更新: {old_count} -> {new_count} 个节点")
    # 打印新增和移除的节点名
    old_names = {p.get('name') for p in (config.get('proxies') or [])}
    new_names = {p.get('name') for p in new_proxies}
    
    added = new_names - old_names
    removed = old_names - new_names
    
    if added:
        print(f"  + 新增: {', '.join(added)}")
    if removed:
        print(f"  - 移除: {', '.join(removed)}")
    
    return config


def review_proxy_groups(config: dict) -> tuple[dict, list]:
    """
    核验 proxy-groups，返回更新后的 config 和变更记录
    
    对于每个 proxy-groups[*].proxies 中的 name:
    - 如果不在 proxies 列表中，则注释掉（添加 # 前缀）
    """
    proxy_names = {p.get('name') for p in config.get('proxies', []) if p.get('name')}
    proxy_groups = config.get('proxy-groups', [])
    
    changed_groups = []
    
    for group in proxy_groups:
        group_name = group.get('name', 'unnamed')
        group_proxies = group.get('proxies', [])
        
        if not isinstance(group_proxies, list):
            continue
            
        new_proxies = []
        group_changes = []
        
        for proxy_ref in group_proxies:
            if not isinstance(proxy_ref, str):
                new_proxies.append(proxy_ref)
                continue
                
            # 检查是否已注释
            is_commented = proxy_ref.strip().startswith('#')
            proxy_name = proxy_ref.lstrip('#').strip()
            
            if is_commented:
                # 保持注释状态
                new_proxies.append(proxy_ref)
            elif proxy_name not in proxy_names:
                # 失效代理，添加注释
                commented = f"# {proxy_ref}  # [AUTO] 节点已失效"
                new_proxies.append(commented)
                group_changes.append(f"- {proxy_name}")
            else:
                new_proxies.append(proxy_ref)
        
        group['proxies'] = new_proxies
        
        if group_changes:
            changed_groups.append({
                'group': group_name,
                'disabled': group_changes
            })
    
    config['proxy-groups'] = proxy_groups
    
    # 输出变更报告
    if changed_groups:
        print(f"\n✓ Proxy-Groups 已核验，发现 {len(changed_groups)} 个组有失效节点:")
        for cg in changed_groups:
            print(f"  [{cg['group']}]")
            for node in cg['disabled']:
                print(f"    {node}")
    else:
        print("\n✓ Proxy-Groups 已核验，无失效节点")
    
    return config, changed_groups


def generate_diff() -> str:
    """生成配置文件差异对比"""
    import difflib
    
    old_content = BACKUP_FILE.read_text(encoding='utf-8').splitlines(keepends=True)
    new_content = EDITING_FILE.read_text(encoding='utf-8').splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_content,
        new_content,
        fromfile='config.yaml.bak',
        tofile='config.yaml.editing',
        lineterm=''
    )
    
    return ''.join(diff)


def main():
    print("=" * 60)
    print("Clash-Meta 配置自动更新")
    print("=" * 60)
    
    # 检查工作目录
    if not WORK_DIR.exists():
        print(f"\nError: 工作目录不存在: {WORK_DIR}", file=sys.stderr)
        sys.exit(1)
    
    if not CONFIG_FILE.exists():
        print(f"\nError: 配置文件不存在: {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)
    
    if not PROXIES_FILE.exists():
        print(f"\nError: 新代理配置不存在: {PROXIES_FILE}", file=sys.stderr)
        sys.exit(1)
    
    print(f"\n工作目录: {WORK_DIR}")
    
    # 1. 备份
    print("\n[1/4] 备份配置文件...")
    backup_config()
    
    # 2. 加载配置
    print("\n[2/4] 加载配置...")
    config = load_yaml(EDITING_FILE)
    proxies_data = load_yaml(PROXIES_FILE)
    new_proxies = proxies_data.get('proxies', [])
    
    if not new_proxies:
        print("Warning: .proxies.yaml 中没有找到代理节点", file=sys.stderr)
        sys.exit(1)
    
    print(f"✓ 当前配置节点数: {len(config.get('proxies', []))}")
    print(f"✓ 新配置节点数: {len(new_proxies)}")
    
    # 3. 更新 proxies
    print("\n[3/4] 更新 proxies...")
    config = update_proxies(config, new_proxies)
    
    # 4. 核验 proxy-groups
    print("\n[4/4] 核验 proxy-groups...")
    config, _ = review_proxy_groups(config)
    
    # 保存编辑后的配置
    save_yaml(config, EDITING_FILE)
    print(f"\n✓ 已保存: {EDITING_FILE}")
    
    # 5. 生成 diff
    print("\n" + "=" * 60)
    print("配置差异对比 (diff)")
    print("=" * 60)
    diff = generate_diff()
    
    if diff:
        print(diff)
    else:
        print("(无变化)")
    
    # 输出摘要
    print("\n" + "=" * 60)
    print("更新摘要")
    print("=" * 60)
    print(f"备份文件: {BACKUP_FILE}")
    print(f"编辑文件: {EDITING_FILE}")
    print(f"目标文件: {CONFIG_FILE}")
    print("\n请检查 diff 输出确认无误后，手动执行重命名:")
    print(f"  mv {EDITING_FILE} {CONFIG_FILE}")
    print("\n如需回滚:")
    print(f"  cp {BACKUP_FILE} {CONFIG_FILE}")
    
    return diff


if __name__ == "__main__":
    diff_output = main()
    # 将 diff 输出到文件供模型读取
    diff_file = WORK_DIR / ".update.diff"
    diff_file.write_text(diff_output if diff_output else "(no changes)", encoding='utf-8')
