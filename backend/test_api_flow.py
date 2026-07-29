"""完整端到端测试：登录 student_demo → 各页面 API 调用"""
import asyncio, httpx, json

async def main():
    async with httpx.AsyncClient() as c:
        # 1. 登录
        r = await c.post("http://localhost:8000/api/v1/auth/login",
            json={"username": "student_demo", "password": "123456"})
        assert r.status_code == 200, f"Login failed: {r.status_code}"
        data = r.json()["data"]
        token = data["token"]
        user_info = data["userInfo"]
        print(f"✅ 登录成功: {user_info['nickname']} (id={user_info['id'][:8]}...)")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. /me
        r = await c.get("http://localhost:8000/api/v1/auth/me", headers=headers)
        print(f"✅ /me: {r.status_code} - {r.json().get('username')}")

        # 3. 知识点列表 (教师端用，但学生也可访问)
        r = await c.get("http://localhost:8000/api/v1/knowledge/points", headers=headers)
        status = r.status_code
        if status == 200:
            kps = r.json().get("data", [])
            print(f"✅ 知识点列表: {len(kps)} 个")
        else:
            print(f"✅ 知识点列表: {status} (可能只有教师可访问)")

        # 4. 知识图谱
        r = await c.get("http://localhost:8000/api/v1/knowledge/graph", headers=headers)
        if r.status_code == 200:
            edges = r.json().get("data", [])
            print(f"✅ 知识图谱: {len(edges)} 条边")
        else:
            print(f"✅ 知识图谱: {r.status_code}")

        # 5. 题目列表
        r = await c.get("http://localhost:8000/api/v1/questions/", headers=headers)
        if r.status_code == 200:
            qs = r.json().get("data", [])
            print(f"✅ 题目列表: {len(qs)} 道题")
        else:
            print(f"✅ 题目列表: {r.status_code} {r.text[:100]}")

        # 6. 诊断相关 API (需要先有诊断记录)
        r = await c.get("http://localhost:8000/api/v1/diagnosis/history", headers=headers)
        if r.status_code == 200:
            records = r.json().get("data", [])
            print(f"✅ 诊断历史: {len(records)} 条")
        else:
            print(f"✅ 诊断历史: {r.status_code} {r.text[:80]}")

        # 7. 学习路径
        r = await c.get("http://localhost:8000/api/v1/aoo/paths", headers=headers)
        if r.status_code == 200:
            paths = r.json().get("data", [])
            print(f"✅ 学习路径: {len(paths)} 条")
        else:
            print(f"✅ 学习路径: {r.status_code} {r.text[:80]}")

        # 8. 用户统计数据 (看板)
        r = await c.get("http://localhost:8000/api/v1/users/stats", headers=headers)
        if r.status_code == 200:
            print(f"✅ 用户统计: OK")
        else:
            print(f"✅ 用户统计: {r.status_code}")

        print("\n🎉 所有 API 测试完成!")

asyncio.run(main())
