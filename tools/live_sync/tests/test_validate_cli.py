# -*- coding: utf-8 -*-
"""测试GIA验证命令行工具"""
import subprocess
import sys
from pathlib import Path

import pytest

from tools.live_sync.validate import validate_file, format_report
from tools.live_sync.node_catalog import NodeCatalog
from tools.live_sync.gia_utils import save_gia_numeric, make_binary_name
from tools.live_sync.node_catalog import VarType


class TestValidateFile:
    """测试validate_file函数"""

    def test_validate_valid_gia(self, tmp_path):
        """测试验证有效的GIA文件"""
        # 创建一个简单的有效GIA
        ng_entry = {
            '1': {'4': 1073741827},
            '3': make_binary_name("TestGraph"),
            '5': 0,
            '13': {
                '1': {
                    '1': {
                        '3': [
                            {
                                '1': 0,
                                '2': 300001,
                                '3': {},
                                '4': [
                                    {
                                        '1': {'1': 3, '2': 0},
                                        '2': {'1': 3, '2': 0},
                                        '3': {'1': VarType.Str, '2': {'1': make_binary_name("test")}},
                                        '4': VarType.Str,
                                    },
                                ],
                                '5': 100,
                                '6': 200,
                            },
                        ],
                    },
                },
            },
        }
        
        msg = {
            '1': [ng_entry],
            '3': make_binary_name("test.gia"),
        }
        
        gia_path = tmp_path / "test_valid.gia"
        save_gia_numeric(msg, gia_path)
        
        # 验证
        catalog = NodeCatalog.default()
        report = validate_file(gia_path, catalog=catalog)
        
        # 应该通过（可能有警告但没有错误）
        assert report.ok or len(report.errors) == 0

    def test_validate_nonexistent_file(self, tmp_path):
        """测试验证不存在的文件"""
        gia_path = tmp_path / "nonexistent.gia"
        
        with pytest.raises(FileNotFoundError):
            validate_file(gia_path)

    def test_validate_without_catalog(self, tmp_path):
        """测试不使用catalog进行验证"""
        # 创建一个简单的GIA
        ng_entry = {
            '1': {'4': 1073741827},
            '3': make_binary_name("TestGraph"),
            '5': 0,
            '13': {
                '1': {
                    '1': {
                        '3': [],
                    },
                },
            },
        }
        
        msg = {
            '1': [ng_entry],
            '3': make_binary_name("test.gia"),
        }
        
        gia_path = tmp_path / "test_no_catalog.gia"
        save_gia_numeric(msg, gia_path)
        
        # 不使用catalog验证
        report = validate_file(gia_path, catalog=None)
        
        # 基础结构验证应该通过
        assert isinstance(report.errors, list)


class TestFormatReport:
    """测试format_report函数"""

    def test_format_passed_report(self, tmp_path):
        """测试格式化通过的报告"""
        from tools.live_sync.validator import ValidationReport
        
        gia_path = tmp_path / "test.gia"
        gia_path.write_text("dummy")
        
        report = ValidationReport(issues=[])
        text = format_report(gia_path, report, verbose=False)
        
        assert "✅ 验证通过" in text
        assert "test.gia" in text

    def test_format_failed_report(self, tmp_path):
        """测试格式化的失败报告"""
        from tools.live_sync.validator import ValidationReport, ValidationIssue
        
        gia_path = tmp_path / "test.gia"
        gia_path.write_text("dummy")
        
        report = ValidationReport(issues=[
            ValidationIssue(
                severity="error",
                code="TEST_ERROR",
                message="Test error message",
                location="test.location"
            )
        ])
        
        text = format_report(gia_path, report, verbose=False)
        
        assert "❌ 验证失败" in text
        assert "1 个错误" in text

    def test_format_verbose_report(self, tmp_path):
        """测试格式化详细报告"""
        from tools.live_sync.validator import ValidationReport, ValidationIssue
        
        gia_path = tmp_path / "test.gia"
        gia_path.write_text("dummy")
        
        report = ValidationReport(issues=[
            ValidationIssue(
                severity="warning",
                code="TEST_WARNING",
                message="Test warning message",
                location="test.location"
            )
        ])
        
        text = format_report(gia_path, report, verbose=True)
        
        assert "⚠️" in text or "警告" in text
        assert "TEST_WARNING" in text


class TestCLI:
    """测试命令行接口"""

    def test_cli_help(self):
        """测试帮助信息"""
        result = subprocess.run(
            [sys.executable, "-m", "tools.live_sync.validate", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent.parent)
        )
        
        assert result.returncode == 0
        assert "验证GIA文件" in result.stdout or "usage" in result.stdout.lower()

    def test_cli_no_args(self):
        """测试无参数运行"""
        result = subprocess.run(
            [sys.executable, "-m", "tools.live_sync.validate"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent.parent)
        )
        
        # 应该报错（缺少参数）
        assert result.returncode != 0

    def test_cli_nonexistent_file(self):
        """测试验证不存在的文件"""
        result = subprocess.run(
            [sys.executable, "-m", "tools.live_sync.validate", "/nonexistent/path/file.gia"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent.parent)
        )
        
        # 应该报错
        assert result.returncode != 0
