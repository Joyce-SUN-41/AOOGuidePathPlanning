"""端到端模拟测试脚本（学生注册/登录 → 诊断 → AOO优化 → 轮询）。"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
API_PREFIX = f"{BASE_URL}/api/v1"
TIMEOUT = 120


def print_step(title: str, status_code: int, data: Any) -> None:
    print(f"\n[{title}] status={status_code}")
    if isinstance(data, dict):
        print("summary:", {k: data.get(k) for k in list(data.keys())[:6]})
    else:
        print("summary:", str(data)[:500])


def fail(title: str, resp: httpx.Response) -> None:
    print(f"\n❌ {title} 失败: HTTP {resp.status_code}")
    try:
        print(resp.json())
    except Exception:
        print(resp.text[:1000])
    sys.exit(1)


def build_answers() -> List[Dict[str, Any]]:
    # 题目 ID 需要与后端题库匹配；若不匹配，后端会提示无有效答案
    return [
        {"question_id": "q_ai_001", "selected_option": "A", "time_spent": 12},
        {"question_id": "q_ai_002", "selected_option": "B", "time_spent": 18},
        {"question_id": "q_ai_003", "selected_option": "C", "time_spent": 15},
    ]


def main() -> None:
    username = f"e2e_student_{int(time.time())}"
    email = f"{username}@example.com"
    password = "Passw0rd123!"

    with httpx.Client(timeout=30) as client:
        # 1) 注册
        register_payload = {"username": username, "email": email, "password": password}
        r = client.post(f"{API_PREFIX}/auth/register", json=register_payload)
        if r.status_code not in (200, 201, 409):
            fail("学生注册", r)
        print_step("学生注册", r.status_code, r.json())

        # 2) 登录
        login_payload = {"username": username, "password": password}
        r = client.post(f"{API_PREFIX}/auth/login", json=login_payload)
        if r.status_code != 200:
            fail("学生登录", r)
        login_data = r.json()
        print_step("学生登录", r.status_code, login_data)

        access_token = login_data.get("access_token")
        if not access_token:
            print("❌ 登录返回中缺少 access_token")
            sys.exit(1)
        client.headers.update({"Authorization": f"Bearer {access_token}"})

        # 获取 user_id（/auth/me）
        r_me = client.get(f"{API_PREFIX}/auth/me")
        if r_me.status_code != 200:
            fail("获取当前用户", r_me)
        user_id = r_me.json().get("id")
        if not user_id:
            print("❌ /auth/me 返回中缺少 id")
            sys.exit(1)
        print_step("获取当前用户", r_me.status_code, {"id": user_id, "username": r_me.json().get("username")})

        # 3) 诊断提交
        diagnosis_payload = {
            "student_id": user_id,
            "subject": "人工智能导论",
            "grade": "本科",
            "answers": build_answers(),
        }
        r = client.post(f"{API_PREFIX}/diagnosis/submit", json=diagnosis_payload)
        if r.status_code != 200:
            fail("诊断提交", r)
        diagnosis_resp = r.json()
        print_step("诊断提交", r.status_code, diagnosis_resp)

        diag_data = diagnosis_resp.get("data", {})
        diagnosis_id = diag_data.get("diagnosis_id")
        mastery_levels = diag_data.get("mastery_levels")
        cognitive_load = diag_data.get("cognitive_load")
        if not diagnosis_id or not isinstance(mastery_levels, dict):
            print("❌ 诊断响应缺少 diagnosis_id 或 mastery_levels")
            sys.exit(1)

        # 4) 触发优化
        optimize_payload = {
            "diagnosis_id": diagnosis_id,
            "student_id": user_id,
            "mastery_levels": mastery_levels,
            "cognitive_load": float(cognitive_load or 0.5),
        }
        r = client.post(f"{API_PREFIX}/aoo/optimize", json=optimize_payload)
        if r.status_code != 200:
            fail("触发AOO优化", r)
        optimize_resp = r.json()
        print_step("触发AOO优化", r.status_code, optimize_resp)

        task_id = optimize_resp.get("data", {}).get("task_id")
        if not task_id:
            print("❌ 优化响应缺少 task_id")
            sys.exit(1)

        # 5) 轮询状态（120秒超时）
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            r = client.get(f"{API_PREFIX}/aoo/status/{task_id}")
            if r.status_code != 200:
                fail("轮询优化状态", r)

            body = r.json()
            data = body.get("data", {})
            status = data.get("status")
            progress = data.get("progress")
            print(
                f"[轮询] {datetime.now().strftime('%H:%M:%S')} "
                f"status={status} progress={progress}"
            )

            if status == "completed":
                print_step("AOO优化完成", 200, data)
                print("\n✅ E2E 流程通过")
                return
            if status == "failed":
                print("❌ AOO任务失败:", data.get("error"))
                sys.exit(1)

            time.sleep(2)

        print("❌ 轮询超时（120秒）")
        sys.exit(1)


if __name__ == "__main__":
    main()
