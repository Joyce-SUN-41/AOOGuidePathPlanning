"""教师端接口 Schema。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.aoo import CamelModel


class StudentSummary(CamelModel):
    student_id: str = Field(..., description="学生ID")
    name: str = Field(..., description="学生名")
    avg_mastery: float = Field(default=0.0, ge=0, le=1)
    cognitive_load: float = Field(default=0.0, ge=0, le=1)
    path_completion: float = Field(default=0.0, ge=0, le=100)
    last_active_date: Optional[str] = Field(default=None, description="最近活跃时间ISO字符串")
    completed_tasks: int = Field(default=0, ge=0)
    total_tasks: int = Field(default=0, ge=0)
    weak_point_count: int = Field(default=0, ge=0)


class TeacherStudentsResponse(CamelModel):
    students: List[StudentSummary] = Field(default_factory=list)
    total: int = 0
