"""뒤에서 도는 작업 시작 — asyncio 는 참조가 없는 작업을 중간에 지울 수 있어서(가비지 컬렉션) 끝날 때까지 참조를 들고 있음
(2026-11-26 점검: 알림 메일·다시 계산 요청이 드물게 사라질 수 있던 것)"""
import asyncio

_running: set = set()


def spawn(coro) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(coro)
    _running.add(task)
    task.add_done_callback(_running.discard)
    return task
