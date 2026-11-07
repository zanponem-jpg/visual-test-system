"""
core/report.py
HTML 测试报告生成器
"""
import os
import time
import datetime
from typing import List
from dataclasses import asdict

from core.runner import StepResult

class ReportGenerator:
    def __init__(self, case_name: str):
        self.case_name = case_name
        self.start_time = datetime.datetime.now()

    def generate(self, results: List["StepResult"], total_duration: float) -> str:
        """生成 HTML 并返回文件路径"""
        # 确保报告目录存在
        os.makedirs("reports", exist_ok=True)
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"reports/report_{timestamp}.html"

        total_steps = len(results)
        passed_steps = sum(1 for r in results if r.status == "PASS")
        failed_steps = total_steps - passed_steps
        pass_rate = (passed_steps / total_steps * 100) if total_steps > 0 else 0

        # 构建表格行
        rows_html = ""
        for r in results:
            status_class = "pass" if r.status == "PASS" else "fail"
            status_icon = "✅" if r.status == "PASS" else "❌"
            
            # 失败时展示错误信息和截图
            error_html = ""
            if r.status == "FAIL":
                shot_html = ""
                if r.screenshot:
                    # 将相对路径转换为 HTML 能够识别的路径（报告在 reports 下，所以需要 ../）
                    img_src = f"../{r.screenshot}"
                    shot_html = f'<div class="evidence"><img src="{img_src}" alt="失败截图" onclick="window.open(this.src)"></div>'
                error_html = f'<div class="error-msg"><strong>错误原因:</strong> {r.error_msg}</div>{shot_html}'

            rows_html += f"""
            <tr>
                <td class="col-idx">{r.step_index}</td>
                <td class="col-action"><span class="badge">{r.action}</span></td>
                <td class="col-desc">
                    <div>{r.desc}</div>
                    {error_html}
                </td>
                <td class="col-time">{r.duration:.2f}s</td>
                <td class="col-status {status_class}">{status_icon} {r.status}</td>
            </tr>
            """

        # HTML 模板 (内联 CSS，保持单文件优雅)
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试报告 - {self.case_name}</title>
    <style>
        :root {{
            --pass: #22c55e; --fail: #ef4444; --bg: #f8fafc; --card: #ffffff; --text: #1e293b;
        }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 40px 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ margin-bottom: 30px; }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 28px; }}
        .meta {{ color: #64748b; font-size: 14px; }}
        
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: var(--card); border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 14px; color: #64748b; margin-bottom: 8px; font-weight: 500; }}
        .card-value {{ font-size: 28px; font-weight: 700; }}
        
        .table-wrap {{ background: var(--card); border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; border: 1px solid #e2e8f0; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th, td {{ padding: 16px 20px; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f1f5f9; font-size: 13px; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; }}
        tr:last-child td {{ border-bottom: none; }}
        
        .badge {{ background: #e2e8f0; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-family: monospace; font-weight: bold; }}
        .col-idx {{ width: 50px; color: #94a3b8; text-align: center; }}
        .col-time {{ width: 80px; color: #64748b; font-family: monospace; }}
        .col-status {{ width: 100px; font-weight: 600; }}
        .col-status.pass {{ color: var(--pass); }}
        .col-status.fail {{ color: var(--fail); }}
        
        .error-msg {{ margin-top: 10px; padding: 12px; background: #fef2f2; border-left: 4px solid var(--fail); color: #991b1b; font-size: 14px; border-radius: 0 8px 8px 0; }}
        .evidence {{ margin-top: 12px; }}
        .evidence img {{ max-width: 300px; border-radius: 8px; border: 1px solid #e2e8f0; cursor: zoom-in; transition: transform 0.2s; }}
        .evidence img:hover {{ transform: scale(1.02); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.case_name}</h1>
            <div class="meta">生成时间: {self.start_time.strftime("%Y-%m-%d %H:%M:%S")} | 执行平台: {self.get_platform()}</div>
        </div>

        <div class="summary">
            <div class="card">
                <div class="card-title">总步骤</div>
                <div class="card-value">{total_steps}</div>
            </div>
            <div class="card">
                <div class="card-title">通过率</div>
                <div class="card-value" style="color: {'var(--pass)' if pass_rate == 100 else 'var(--fail)'}">{pass_rate:.1f}%</div>
            </div>
            <div class="card">
                <div class="card-title">总耗时</div>
                <div class="card-value">{total_duration:.2f}s</div>
            </div>
            <div class="card">
                <div class="card-title">通过 / 失败</div>
                <div class="card-value"><span style="color: var(--pass)">{passed_steps}</span> / <span style="color: var(--fail)">{failed_steps}</span></div>
            </div>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th style="text-align: center;">#</th>
                        <th>动作</th>
                        <th>描述与详情</th>
                        <th>耗时</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
        """
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return filename

    def get_platform(self) -> str:
        # 可以通过读取 yaml 或其他方式动态获取，这里简单返回
        return "Android"