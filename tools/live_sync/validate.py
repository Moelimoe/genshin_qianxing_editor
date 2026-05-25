# -*- coding: utf-8 -*-
"""GIA文件验证命令行工具

Usage:
    python -m tools.live_sync.validate <gia_file> [options]
    python -m tools.live_sync.validate <pattern> [options]

Options:
    -v, --verbose    显示详细报告
    -f, --fix        尝试自动修复问题
    -o, --output     输出报告到文件

Examples:
    python -m tools.live_sync.validate my_level.gia
    python -m tools.live_sync.validate levels/*.gia --verbose
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from tools.live_sync.gia_loader import GIALoader
from tools.live_sync.gia_utils import load_gia_numeric
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.validator import GIAValidator, ValidationReport


def validate_file(gia_path: Path, catalog: Optional[NodeCatalog] = None, verbose: bool = False) -> ValidationReport:
    """验证单个GIA文件
    
    Args:
        gia_path: GIA文件路径
        catalog: 可选的节点注册表
        verbose: 是否显示详细信息
        
    Returns:
        验证报告
    """
    if not gia_path.exists():
        raise FileNotFoundError(f"GIA文件不存在: {gia_path}")
    
    # 加载GIA文件
    try:
        num = load_gia_numeric(gia_path)
    except Exception as e:
        from tools.live_sync.validator import ValidationIssue, ValidationReport
        return ValidationReport(issues=[
            ValidationIssue(
                severity="error",
                code="LOAD_ERROR",
                message=f"无法加载GIA文件: {e}",
                location=""
            )
        ])
    
    # 验证结构
    validator = GIAValidator(catalog=catalog)
    report = validator.validate_numeric(num)
    
    # 如果有catalog，尝试加载为GraphBuilder进行额外验证
    if catalog and report.ok:
        try:
            loader = GIALoader(catalog=catalog)
            loaded = loader.load(gia_path)
            
            for i in range(loaded.get_graph_count()):
                try:
                    graph = loaded.get_graph(i, catalog=catalog)
                    graph_report = validator.validate_graph_builder(graph)
                    report.issues.extend(graph_report.issues)
                except Exception as e:
                    from tools.live_sync.validator import ValidationIssue
                    # 语义验证失败不是致命错误（可能是type_id格式不支持等）
                    report.issues.append(ValidationIssue(
                        severity="warning",
                        code="GRAPH_LOAD_ERROR",
                        message=f"无法加载节点图[{i}]进行语义验证: {e}",
                        location=f"graph[{i}]"
                    ))
        except Exception as e:
            from tools.live_sync.validator import ValidationIssue
            report.issues.append(ValidationIssue(
                severity="warning",
                code="LOADER_ERROR",
                message=f"GIA加载器错误（结构验证已通过）: {e}",
                location=""
            ))
    
    return report


def format_report(gia_path: Path, report: ValidationReport, verbose: bool = False) -> str:
    """格式化验证报告
    
    Args:
        gia_path: GIA文件路径
        report: 验证报告
        verbose: 是否显示详细信息
        
    Returns:
        格式化的报告字符串
    """
    lines: List[str] = []
    
    # 文件信息
    file_size = gia_path.stat().st_size if gia_path.exists() else 0
    lines.append(f"📄 {gia_path.name} ({file_size} bytes)")
    
    # 验证结果
    if report.ok:
        lines.append("   ✅ 验证通过")
        if verbose and report.warnings:
            lines.append(f"   ⚠️  {len(report.warnings)} 个警告")
            for issue in report.warnings:
                lines.append(f"      [{issue.code}] {issue.message}")
        if verbose and report.infos:
            lines.append(f"   ℹ️  {len(report.infos)} 个提示")
    else:
        lines.append(f"   ❌ 验证失败: {len(report.errors)} 个错误")
        
        if verbose:
            # 按严重程度分组
            for issue in report.errors:
                loc = f"[{issue.location}] " if issue.location else ""
                lines.append(f"      [ERROR] {issue.code}: {loc}{issue.message}")
            for issue in report.warnings:
                loc = f"[{issue.location}] " if issue.location else ""
                lines.append(f"      [WARN] {issue.code}: {loc}{issue.message}")
    
    lines.append("")
    return "\n".join(lines)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="验证GIA文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m tools.live_sync.validate my_level.gia
    python -m tools.live_sync.validate levels/*.gia --verbose
    python -m tools.live_sync.validate my_level.gia -o report.txt
        """
    )
    
    parser.add_argument(
        "files",
        nargs="+",
        help="GIA文件路径或通配符模式"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细报告"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="输出报告到文件"
    )
    
    parser.add_argument(
        "--no-catalog",
        action="store_true",
        help="不使用节点注册表（只进行基础结构验证）"
    )
    
    args = parser.parse_args()
    
    # 加载节点注册表
    catalog = None if args.no_catalog else NodeCatalog.default()
    
    # 收集所有文件
    all_files: List[Path] = []
    for pattern in args.files:
        path = Path(pattern)
        if path.exists():
            all_files.append(path)
        else:
            # 尝试作为通配符
            import glob
            matched = glob.glob(pattern)
            all_files.extend(Path(p) for p in matched if p.endswith('.gia'))
    
    if not all_files:
        print("❌ 未找到GIA文件", file=sys.stderr)
        sys.exit(1)
    
    # 去重并保持顺序
    seen = set()
    unique_files = []
    for f in all_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    
    # 验证所有文件
    all_reports: List[tuple[Path, ValidationReport]] = []
    total_errors = 0
    total_warnings = 0
    
    print(f"🔍 验证 {len(unique_files)} 个GIA文件...\n")
    
    for gia_path in unique_files:
        try:
            report = validate_file(gia_path, catalog=catalog, verbose=args.verbose)
            all_reports.append((gia_path, report))
            total_errors += len(report.errors)
            total_warnings += len(report.warnings)
            print(format_report(gia_path, report, args.verbose), end="")
        except Exception as e:
            print(f"❌ {gia_path.name}: 验证失败 - {e}\n")
            total_errors += 1
    
    # 总结
    print("=" * 60)
    print(f"📊 总结: {len(unique_files)} 个文件")
    
    if total_errors == 0:
        print(f"   ✅ 全部通过 ({total_warnings} 个警告)")
        exit_code = 0
    else:
        print(f"   ❌ {total_errors} 个错误, {total_warnings} 个警告")
        exit_code = 1
    
    # 输出到文件
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"GIA验证报告\n")
            f.write(f"=" * 60 + "\n\n")
            for gia_path, report in all_reports:
                f.write(format_report(gia_path, report, verbose=True))
        print(f"\n📝 报告已保存到: {args.output}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
