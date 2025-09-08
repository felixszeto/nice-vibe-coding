from functools import wraps
from typing import Callable

from nicegui import app, ui

# 儲存匿名使用者可以訪問的路徑
# We use a set for efficient checking
unrestricted_page_routes = {'/login'}

def is_authenticated() -> bool:
    """檢查使用者是否已經登入"""
    return app.storage.user.get('authenticated', False)

import inspect
from starlette.requests import Request

def authenticated_page(func: Callable) -> Callable:
    """
    一個頁面裝飾器，用於保護需要登入才能訪問的頁面。
    如果使用者未登入，則將其重定向到登入頁面。
    此裝飾器能同時處理同步和非同步的頁面函式。
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request: Request | None = kwargs.get('request')
        
        # 對於沒有 request 的情況 (例如，非頁面函式)，直接執行
        if not request:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        # 檢查請求的路徑是否在允許的匿名路徑中
        if request.url.path not in unrestricted_page_routes:
            if not is_authenticated():
                app.storage.user['referrer_path'] = request.url.path
                ui.navigate.to('/login')
                return
        
        # 根據原始函式是同步還是非同步來執行
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wrapper
