"""创建 Demo 用户账号"""
import asyncio, httpx, json

async def main():
    async with httpx.AsyncClient() as c:
        base = "http://localhost:8000/api/v1/auth"

        users = [
            ("student_demo", "123456", "学生Demo", "student"),
            ("teacher_demo", "123456", "教师Demo", "teacher"),
        ]

        for username, password, nickname, role in users:
            # 先尝试登录，如果已存在则跳过
            r = await c.post(f"{base}/login", json={"username": username, "password": password})
            if r.status_code == 200:
                print(f"✅ {username} 已存在，跳过创建")
                continue

            # 注册
            r = await c.post(f"{base}/register", json={
                "username": username, "password": password,
                "nickname": nickname, "role": role
            })
            if r.status_code in (201, 200):
                d = r.json()
                print(f"✅ {username} 创建成功 (role={role})")
            else:
                print(f"❌ {username} 创建失败: {r.status_code} {r.text}")

asyncio.run(main())
