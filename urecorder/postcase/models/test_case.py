"""测试用例数据模型"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class TestCaseStatus(str, Enum):
    """测试用例状态枚举"""
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


class TestStep:
    """测试步骤"""
    def __init__(self, step_number: int, description: str, expected_result: str):
        self.step_number = step_number
        self.description = description
        self.expected_result = expected_result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "description": self.description,
            "expected_result": self.expected_result
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestStep":
        return cls(
            step_number=data.get("step_number", 1),
            description=data.get("description", ""),
            expected_result=data.get("expected_result", "")
        )


class TestCase:
    """测试用例"""
    def __init__(
        self,
        id: Optional[str] = None,
        title: str = "",
        description: str = "",
        preconditions: Optional[str] = None,
        steps: Optional[List[TestStep]] = None,
        priority: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.id = id
        self.title = title
        self.description = description
        self.preconditions = preconditions
        self.steps = steps or []
        self.priority = priority
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "preconditions": self.preconditions,
            "steps": [s.to_dict() for s in self.steps],
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        steps = []
        if data.get("steps"):
            steps = [TestStep.from_dict(s) for s in data["steps"]]

        return cls(
            id=data.get("id"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            preconditions=data.get("preconditions"),
            steps=steps,
            priority=data.get("priority"),
            created_at=data.get("created_at")
        )


# 示例数据
TEST_CASE_EXAMPLE = {
    "id": "TC-001",
    "title": "Verify login functionality",
    "description": "Test the user login process",
    "preconditions": "User account exists in the system",
    "steps": [
        {
            "step_number": 1,
            "description": "Navigate to login page",
            "expected_result": "Login page is displayed"
        },
        {
            "step_number": 2,
            "description": "Enter valid username and password",
            "expected_result": "Credentials are accepted"
        },
        {
            "step_number": 3,
            "description": "Click login button",
            "expected_result": "User is logged in and redirected to dashboard"
        }
    ],
    "priority": "High",
    "created_at": "2025-05-12T10:00:00"
}
