"""stale-while-revalidate 캐시 — 오래 걸리는 조회를 기다리지 않고 바로 보여주기

- 받은 지 `fresh` 초 안이면 캐시 그대로.
- 그보다 오래됐지만 `max_stale` 초 안이면 **기존 값을 바로 돌려주고** 뒤에서 새로 받는다
  (화면은 다음 갱신 때 새 값을 받음). 응답에 `updated_at`·`refreshing` 이 붙어 화면에 기준 시각을 표시.
- 값이 없거나 너무 오래됐으면 새로 받을 때까지 기다린다. 같은 키를 동시에 요청해도 조회는 한 번만.
- 새로 받기가 실패하면: 기다리던 요청은 오류 그대로(빈 값으로 숨기지 않음),
  기존 값을 보여주는 중이면 기존 값 + `refresh_error`(실패 사유)를 같이 돌려준다.
"""
import asyncio
import time
from datetime import datetime
from typing import Any, Awaitable, Callable


class SWRCache:
    def __init__(self, name: str, fresh: float, max_stale: float,
                 fresh_for: Callable[[Any], float] | None = None):
        """fresh_for(value): 값마다 fresh 를 다르게 (예: 일부 실패한 결과는 짧게) — 없으면 fresh"""
        self.name, self.fresh, self.max_stale, self.fresh_for = name, fresh, max_stale, fresh_for
        self._data: dict = {}     # key -> (ts, value)
        self._errors: dict = {}   # key -> 마지막 백그라운드 갱신 실패 사유
        self._tasks: dict = {}    # key -> 진행 중인 조회 Task

    def _start(self, key, fn: Callable[[], Awaitable[Any]]) -> asyncio.Task:
        task = self._tasks.get(key)
        if task and not task.done():
            return task

        async def run():
            try:
                value = await fn()
                now = time.time()
                # 더 이상 쓸 수 없는 오래된 값 정리 (목록이 바뀌면 키가 바뀌는 캐시가 쌓이지 않도록)
                for k in [k for k, (ts, _) in self._data.items() if now - ts > self.max_stale + 60]:
                    self._data.pop(k, None)
                self._data[key] = (now, value)
                self._errors.pop(key, None)
                return value
            except BaseException as e:
                # httpx 시간 초과 등은 str(e) 가 빈 문자열 → 오류 종류라도 보이게
                self._errors[key] = str(getattr(e, "detail", None) or e) or type(e).__name__
                raise
            finally:
                self._tasks.pop(key, None)

        task = asyncio.create_task(run())
        # 뒤에서 돌다 실패해도 "Task exception was never retrieved" 경고가 안 나도록
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        self._tasks[key] = task
        return task

    async def get(self, key, fn: Callable[[], Awaitable[Any]], wrap: bool = True):
        """wrap=True 이고 값이 dict 면 updated_at(값에 이미 있으면 그대로)·refreshing·refresh_error 를 붙여서 돌려줌"""
        hit = self._data.get(key)
        age = time.time() - hit[0] if hit else None
        fresh = self.fresh_for(hit[1]) if hit and self.fresh_for else self.fresh
        if hit and age < fresh:
            return self._wrap(key, hit, False) if wrap else hit[1]
        if hit and age < self.max_stale:
            self._start(key, fn)
            return self._wrap(key, hit, True) if wrap else hit[1]
        # asyncio.shield: 브라우저가 기다리다 끊어도 조회는 끝까지 해서 캐시에 남김
        value = await asyncio.shield(self._start(key, fn))
        return self._wrap(key, self._data.get(key, (time.time(), value)), False) if wrap else value

    def peek(self, key):
        hit = self._data.get(key)
        return hit[1] if hit else None

    def invalidate(self, key=None):
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)

    def warm(self, key, fn):
        """미리 받아 두기 (서버 시작 직후 등) — 이미 받는 중이면 그대로"""
        return self._start(key, fn)

    def _wrap(self, key, hit, refreshing: bool):
        ts, value = hit
        if not isinstance(value, dict):
            return value
        out = {"updated_at": datetime.fromtimestamp(ts).isoformat(timespec="seconds"), **value,
               "refreshing": refreshing or bool(self._tasks.get(key))}
        if self._errors.get(key):
            out["refresh_error"] = self._errors[key]
        return out
