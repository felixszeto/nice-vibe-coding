import os
import re
import uuid
import httpx
import json
import html
import asyncio
import logging
import datetime

from nicegui import app, ui, context
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

import database
import auth
import management_pages
from languages import T, get_lang, set_language

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MANUAL_EDIT_IDENTIFIER = "manual-edit-by-user"

STATUS_RIBBONS = {
    0: ('status_draft', 'bg-gray-500'),
    1: ('status_in_review', 'bg-blue-500'),
    2: ('status_approved', 'bg-green-600'),
    3: ('status_rejected', 'bg-red-600'),
    4: ('status_published', 'bg-teal-500'),
    5: ('status_archived', 'bg-orange-500'),
    6: ('status_deleted', 'bg-red-700'),
}



database.init_db()

def get_base_url(request: Request) -> str:
    """
    Determines the correct base URL, considering reverse proxy headers.
    """
    # Use 'x-forwarded-proto' to determine the scheme (http or https)
    scheme = request.headers.get('x-forwarded-proto', request.url.scheme)
    
    # Use 'x-forwarded-host' if available, otherwise fall back to the request's host
    host = request.headers.get('x-forwarded-host', request.url.netloc)
    
    return f"{scheme}://{host}/"

def create_header(page_title: str):
    """Creates a reusable header with a hamburger menu and navigation drawer."""
    with ui.header(elevated=True).classes('bg-white text-black items-center justify-between px-4'):
        # Left side: Hamburger menu and Title
        with ui.row().classes('items-center'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat dense').classes('text-black')
            ui.label(page_title).classes('text-2xl font-bold')
        
        # Right side: Action Icons
        with ui.row().classes('items-center gap-2'):
            with ui.button(icon='language').props('flat round dense color="black" hover:bg-gray-200'):
                with ui.menu():
                    ui.menu_item(T('language_chinese_traditional'), on_click=lambda: set_language('zh-TW'))
                    ui.menu_item(T('language_chinese_simplified'), on_click=lambda: set_language('zh-CN'))
                    ui.menu_item(T('language_japanese'), on_click=lambda: set_language('ja'))
                    ui.menu_item(T('language_korean'), on_click=lambda: set_language('ko'))
                    ui.menu_item(T('language_english'), on_click=lambda: set_language('en'))
            
            with ui.button(icon='logout', on_click=lambda: (app.storage.user.clear(), ui.navigate.to('/login'))).props('flat round dense color="black" hover:bg-gray-200') as logout_button:
                ui.tooltip(T('logout'))

    with ui.left_drawer().classes('bg-gray-100').props('width=240 bordered') as left_drawer:
        with ui.column().classes('w-full h-full'):
            with ui.scroll_area().classes('w-full flex-grow'):
                with ui.element('q-list').props('separator').classes('w-full'):
                    user_permissions = app.storage.user.get('permissions', [])
                    menu_items = []
                    if 'develop_app' in user_permissions or 'system_admin' in user_permissions:
                        menu_items.append(('/my-apps', T('my_apps'), 'widgets'))
                    
                    menu_items.append(('/store', T('app_store'), 'store'))

                    if 'share_app' in user_permissions or 'system_admin' in user_permissions:
                        menu_items.append(('/my-shares', T('my_shares'), 'share'))

                    for path, title, icon in menu_items:
                        with ui.element('q-item').props('clickable v-ripple').on('click', lambda p=path: ui.navigate.to(p)):
                            with ui.element('q-item-section').props('avatar'):
                                ui.icon(icon)
                            with ui.element('q-item-section'):
                                ui.label(title)

            # Spacer to push the management button to the bottom
            ui.space()

            # Management button at the bottom
            user_permissions = app.storage.user.get('permissions', [])
            if 'system_admin' in user_permissions or 'review_app' in user_permissions:
                with ui.element('q-list').props('separator').classes('w-full'):
                    ui.separator()
                    with ui.element('q-item').props('clickable v-ripple').on('click', lambda: ui.navigate.to('/management')):
                        with ui.element('q-item-section').props('avatar'):
                            ui.icon('admin_panel_settings')
                        with ui.element('q-item-section'):
                            ui.label(T('management_center'))

def parse_ai_response(response_text: str) -> tuple[str | None, str | None]:
    think_content = None
    html_content = None
    remaining_text = response_text
    
    think_match = re.search(r'<think>(.*?)</think>', response_text, re.DOTALL)
    if think_match:
        think_content = think_match.group(1).strip()
        remaining_text = response_text[think_match.end():]
        
    html_match = re.search(r'<output-html>(.*?)</output-html>', remaining_text, re.DOTALL)
    if html_match:
        html_content = html_match.group(1).strip()
        
    return think_content, html_content

def _create_full_html_page(content: str, title: str, extra_styles: str = "") -> str:
    return content

@app.get('/session/render/{uuid_str}')
def render_version(uuid_str: str):
    html_content = database.get_version_html(uuid_str)
    if html_content:
        return HTMLResponse(content=_create_full_html_page(html_content, "Preview"))
    return Response(content=f"Version with ID '{uuid_str}' not found.", status_code=404)

@app.get('/app/{uuid_str}')
def app_page(uuid_str: str):
    html_content = database.get_version_html(uuid_str)
    if html_content:
        return HTMLResponse(content=_create_full_html_page(html_content, "App"))
    else:
        return HTMLResponse(content=f"<h1>Error 404: App with ID '{uuid_str}' not found.</h1>", status_code=404)
from fastapi.responses import HTMLResponse
import database

@app.get("/preview/{version_uuid}", response_class=HTMLResponse)
async def preview_app_version(version_uuid: str):
    """
    提供一個獨立的端點來預覽特定版本的應用程式 HTML。
    這可以將使用者內容與主應用程式隔離，以策安全。
    """
    html_content = database.get_version_html(version_uuid)
    if html_content:
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content=f"<h1>{T('version_not_found')}</h1>", status_code=404)

@app.get("/share/{share_uuid}", response_class=HTMLResponse)
async def shared_app_page(share_uuid: str, request: Request):
    """
    提供一個公開的端點來顯示分享的應用程式版本。
    """
    share_info = database.get_app_share(share_uuid)
    if share_info:
        html_content = database.get_version_html(share_info['version_uuid'])
        if html_content:
            share_url = str(request.url)
            # We need to escape quotes for the JS string
            escaped_notification_text = T('link_copied_to_clipboard').replace("'", "\\'")
            
            copy_script = f"""
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    document.body.addEventListener('click', function() {{
                        navigator.clipboard.writeText('{share_url}').then(function() {{
                            console.log('URL copied to clipboard');
                            var notification = document.createElement('div');
                            notification.textContent = '{escaped_notification_text}';
                            notification.style.cssText = 'position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background-color: #333; color: white; padding: 10px 20px; border-radius: 5px; z-index: 10000; box-shadow: 0 4px 8px rgba(0,0,0,0.2); font-family: sans-serif;';
                            document.body.appendChild(notification);
                            setTimeout(function() {{
                                document.body.removeChild(notification);
                            }}, 2000);
                        }}, function(err) {{
                            console.error('Could not copy text: ', err);
                        }});
                    }}, {{ once: true }});
                }});
            </script>
            """
            if '</body>' in html_content.lower():
                # Case-insensitive replacement
                body_end_index = html_content.lower().rfind('</body>')
                html_content = html_content[:body_end_index] + copy_script + html_content[body_end_index:]
            else:
                html_content += copy_script
            return HTMLResponse(content=html_content)
    return HTMLResponse(content=f"<h1>{T('share_not_found_or_expired')}</h1>", status_code=404)

@ui.page('/login')
def login_page():
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
    
    async def handle_login():
        await asyncio.sleep(0.1) # Add a small delay
        user = database.get_user_by_username(username_input.value)
        if user and database.verify_password(password_input.value, user['password_hash']):
            # 檢查使用者狀態是否為啟用
            if user['status'] == 0:
                ui.notify(T('account_disabled'), color='negative')
                return

            user_permissions = database.get_user_permissions(user['id'])
            
            # 1. 如果用戶擁有 system_admin 權限，則賦予所有權限
            if 'system_admin' in user_permissions:
                all_authorities = database.get_all_authorities()
                user_permissions.update([auth['name'] for auth in all_authorities])

            app.storage.user.update({
                'user_id': user['id'],
                'username': user['username'],
                'authenticated': True,
                'permissions': list(user_permissions)
            })

            # 2. 根據權限決定登入後的跳轉頁面
            if 'develop_app' in user_permissions or 'system_admin' in user_permissions:
                ui.navigate.to('/my-apps')
            else:
                ui.navigate.to('/store')
        else:
            ui.notify(T('login_error'), color='negative')

    ui.query('body').style('background: linear-gradient(135deg, #0c4a6e, #000);')

    with ui.page_sticky(position='top-right', x_offset=20, y_offset=20):
        with ui.button(icon='language').props('flat round dense color="white"'):
            with ui.menu():
                ui.menu_item(T('language_chinese_traditional'), on_click=lambda: set_language('zh-TW'))
                ui.menu_item(T('language_chinese_simplified'), on_click=lambda: set_language('zh-CN'))
                ui.menu_item(T('language_japanese'), on_click=lambda: set_language('ja'))
                ui.menu_item(T('language_korean'), on_click=lambda: set_language('ko'))
                ui.menu_item(T('language_english'), on_click=lambda: set_language('en'))

    ui.add_head_html('''
        <style>
            @keyframes fadeIn-up {
                0% {
                    opacity: 0;
                    transform: translateY(20px);
                }
                100% {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            @keyframes shimmer {
                0% {
                    background-position: -500%;
                }
                100% {
                    background-position: 500%;
                }
            }
            .slogan-animate {
                animation: fadeIn-up 1s ease-out forwards;
            }
            .shimmer-text {
                background: linear-gradient(90deg, #fff, #fff, #fff, #87CEEB, #fff, #fff, #fff);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                background-size: 200% 100%;
                animation: shimmer 8s infinite linear;
            }
        </style>
    ''')
    with ui.column().classes('w-full h-screen items-center justify-center space-y-6'):
        ui.image('vibe_logo.png').classes('w-56')
        ui.label(T('vibe_slogan')).classes('text-xl font-semibold tracking-wider').classes('slogan-animate shimmer-text').style('text-shadow: 0 0 15px rgba(255,255,255,0.5);')
        with ui.card().classes('w-96 gap-0 rounded-2xl shadow-2xl').style('background-color: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px);'):
            with ui.card_section():
                ui.label(T('user_login')).classes('text-3xl font-bold self-center text-white')
            
            with ui.card_section().classes('q-gutter-md w-full'):
                username_input = ui.input(T('username')).props('filled dark').classes('w-full text-white').style('background-color: rgba(255, 255, 255, 0.2);').on('keydown.enter', handle_login)
                password_input = ui.input(T('password'), password=True, password_toggle_button=True).props('filled dark').classes('w-full text-white').style('background-color: rgba(255, 255, 255, 0.2);').on('keydown.enter', handle_login)
            
            with ui.card_actions().classes('px-4 w-full'):
                ui.button(T('login'), on_click=handle_login).props('unelevated').classes('w-full bg-indigo-500 hover:bg-indigo-600 text-white font-bold')

@ui.page('/')
@auth.authenticated_page
def root_page_redirector(request: Request):
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
    user_permissions = app.storage.user.get('permissions', [])
    if 'develop_app' in user_permissions or 'system_admin' in user_permissions:
        ui.navigate.to('/my-apps')
    else:
        ui.navigate.to('/store')

@ui.page('/store')
@auth.authenticated_page
def app_store_page(request: Request):
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
    ui.page_title(T('app_store'))


    def show_operating_instructions(name: str, instructions: str | None):
        with ui.dialog() as dialog, ui.card().classes('w-[90vw] max-w-2xl'):
            ui.label(T('operating_instructions_title')).classes('text-xl font-bold')
            ui.separator()
            if instructions:
                ui.label(instructions).classes('mt-4 text-base whitespace-pre-line')
            else:
                ui.label(T('no_instructions_provided')).classes('mt-4 text-base text-gray-500')
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button(T('close'), on_click=dialog.close).props('flat').classes('text-black')
        dialog.open()
    def get_risk_level_info(app_data: dict) -> tuple[str, str, list[str]]:
        critical_risks_str = app_data['critical_risks'] or ''
        medium_risks_str = app_data['medium_risks'] or ''
        low_risks_str = app_data['low_risks'] or ''

        critical_risks = [r.strip() for r in critical_risks_str.split(',') if r.strip()]
        medium_risks = [r.strip() for r in medium_risks_str.split(',') if r.strip()]
        low_risks = [r.strip() for r in low_risks_str.split(',') if r.strip()]

        all_risks = critical_risks + medium_risks + low_risks

        if critical_risks:
            return 'red-500', T('high_risk'), all_risks
        if medium_risks:
            return 'yellow-500', T('medium_risk'), all_risks
        if low_risks:
            return 'blue-500', T('low_risk'), all_risks
        
        return 'green-500', T('no_risk_detected'), []

    create_header(T('app_store'))
                        
    published_apps = database.get_all_live_applications(get_lang())

    ui.label(T('latest_apps')).classes('text-xl font-bold p-4')

    if not published_apps:
        with ui.column().classes('w-full items-center justify-center p-8'):
            ui.icon('cloud_off', size='xl').classes('text-gray-400')
            ui.label(T('no_apps_in_store')).classes('text-gray-500 text-lg')
    else:
        with ui.row().classes('w-full p-4 grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch'):
            for app_data in published_apps:
                # Add 'flex flex-col' to make the card a flex container that grows
                with ui.card().tight().classes("relative w-full rounded-2xl overflow-hidden shadow-lg hover:shadow-2xl transition-shadow duration-300 border border-gray-200 flex flex-col"):
                    # Risk Icon positioned absolutely relative to the card
                    risk_color, risk_text, all_risks = get_risk_level_info(app_data)
                    with ui.element('div').classes('absolute top-3 right-3 z-10'):
                        with ui.button(icon='shield').props('flat round dense').classes(f'text-xl opacity-80 !text-{risk_color} p-0'):
                            if all_risks:
                                with ui.menu().classes('bg-gray-800 text-white shadow-lg rounded-md text-sm'):
                                    with ui.column().classes('gap-1 p-2'):
                                        ui.label(risk_text).classes('font-bold')
                                        ui.separator().classes('my-1 bg-gray-600')
                                        for risk in all_risks:
                                            ui.label(f'- {risk}')
                            else:
                                ui.tooltip(risk_text).classes('bg-gray-900 text-white shadow-lg')
                    
                    app_name = app_data['app_name']
                    app_description = app_data['functional_description'] if 'functional_description' in app_data.keys() and app_data['functional_description'] is not None else T('app_description_placeholder')

                    # Top Section: Two columns for Icon and Info
                    with ui.row().classes('w-full items-start p-4 gap-4 flex-nowrap'):
                        # Left Column: Preview Image
                        with ui.column().classes('w-1/3'):
                            with ui.element('div').classes('relative aspect-square cursor-pointer overflow-hidden rounded-lg').on('click', lambda u=app_data['live_version_uuid']: ui.navigate.to(f'/app/{u}')):
                                template_html = app_data['app_template_html'] or f'<div class="w-full h-full flex items-center justify-center bg-gray-100 text-gray-400">{T("no_preview_available")}</div>'
                                ui.html(f'<div style="width:100%; height:100%; pointer-events:none; overflow: hidden;"><iframe srcdoc="{html.escape(template_html)}" style="width:200%; height:200%; border:none; transform: scale(0.5); transform-origin: 0 0;"></iframe></div>', sanitize=False).classes('w-full h-full')

                        # Right Column: Name and Categories
                        with ui.column().classes('w-2/3 pr-12'): # Add padding to avoid overlap with shield icon
                            ui.label(app_name).classes('text-2xl font-bold text-gray-800')
                            
                            categories = app_data['categories'].split(',') if app_data['categories'] else []
                            if categories:
                                with ui.row().classes('gap-2 mt-2'):
                                    for category in categories[:3]:
                                        ui.badge(category, color='gray-200').classes('text-gray-600 text-xs font-semibold px-2 py-1')

                            # Description moved under categories and above separator
                            with ui.element('div').classes('gap-1 mt-2 cursor-pointer'):
                                ui.label(T('app_functional_description_title')).classes('text-sm font-semibold text-gray-600')
                                ui.label(app_description).classes('text-gray-500 text-sm line-clamp-2')
                                with ui.menu().classes('bg-gray-800 text-white shadow-lg rounded-md text-sm p-3 max-w-xs'):
                                    ui.label(app_description).classes('whitespace-pre-line')

                    # Separator
                    ui.separator().classes('mx-4')

                    # Bottom Section: Information
                    with ui.column().classes('w-full flex flex-col justify-between flex-grow p-4 pt-0'):
                        # Developer Info at the bottom
                        with ui.row().classes('items-center mt-auto pt-4'):
                            ui.icon('person', color='gray-400')
                            ui.label(app_data['owner_username'] or T('unknown_developer')).classes('text-sm text-gray-500 ml-2')

                    # Bottom-right action to open Operating Instructions
                    with ui.element('div').classes('absolute bottom-3 right-3 z-10'):
                        with ui.button(
                            icon='help',
                            on_click=lambda name=app_name, instr=(app_data['operating_instructions'] if 'operating_instructions' in app_data.keys() else None): show_operating_instructions(name, instr)
                        ).props('round dense flat color="black"'):
                            ui.tooltip(T('operating_instructions_title'))


@ui.page('/my-apps')
@auth.authenticated_page
def my_apps_page(request: Request):
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
    user_permissions = app.storage.user.get('permissions', [])
    if 'develop_app' not in user_permissions and 'system_admin' not in user_permissions:
        ui.label(T('permission_denied')).classes('text-red-500 m-4')
        return
    ui.page_title(T('my_apps'))
    create_header(T('my_apps'))
    user_id = app.storage.user.get('user_id')
    my_apps = database.get_apps_by_owner_id(user_id) if user_id else []

    if not my_apps:
        with ui.column().classes('w-full items-center justify-center p-8'):
            ui.icon('widgets', size='xl').classes('text-gray-400')
            ui.label(T('you_have_no_apps')).classes('text-gray-500 text-lg')
    else:
        with ui.row().classes('w-full p-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-6 items-stretch'):
            for app_data in my_apps:
                with ui.card().tight().classes("w-full relative rounded-3xl shadow-lg bg-gray-100"):
                    status = app_data['status']
                    ribbon_info = STATUS_RIBBONS.get(status)
                    if ribbon_info:
                        text, color_class = ribbon_info
                        ui.html(f'<div class="absolute top-2 right-2 px-2 py-1 text-white text-xs font-bold rounded z-10 {color_class} shadow-md">{T(text)}</div>', sanitize=False)

                    preview_status, _ = database.get_application_preview_status(app_data['session_id']) or (0, 0)
                    
                    with ui.column().classes('w-full'):
                        is_loading = preview_status in [1, 2]

                        # Base preview content
                        if preview_status == 3: # Completed
                            preview_content = app_data['app_template_html'] or f'<div class="w-full h-full flex items-center justify-center bg-gray-200 text-gray-500">{T("no_preview_available")}</div>'
                        elif preview_status == 4: # Failed
                            preview_content = f'<div class="w-full h-full flex flex-col items-center justify-center bg-red-100 text-red-700 "><svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg><span class="mt-2">{T("preview_generation_failed")}</span></div>'
                        else: # None, Pending, In Progress or other states
                            preview_content = f'<div class="w-full h-full flex items-center justify-center bg-gray-200 text-gray-500">{T("no_preview_available")}</div>'
                        
                        ui.html(f'<iframe srcdoc="{html.escape(preview_content)}" class="w-full h-full border-none aspect-square rounded-3xl overflow-hidden"></iframe>', sanitize=False).classes('w-full')

                        # Loading overlay
                        if is_loading:
                            with ui.column().classes('absolute top-0 left-0 w-full h-full bg-black/50 flex items-center justify-center rounded-3xl'):
                                ui.spinner(size='lg', color='white')
                                ui.label(T('generating_preview')).classes('text-white mt-2')
                    with ui.card_section().classes('absolute bottom-0 left-0 right-0 flex w-full justify-between items-center p-2 bg-black/20 rounded-b-3xl overflow-hidden'):
                        ui.label(app_data['app_name']).classes('text-base font-semibold text-white')
                        ui.button(T('manage'), on_click=lambda s=app_data['session_id']: ui.navigate.to(f'/session/{s}')).props('dense').classes('bg-black text-white text-xs px-2 py-1 rounded-md')

    with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20).classes('z-10'):
        ui.button(icon='add', on_click=lambda: ui.navigate.to(f'/session/{uuid.uuid4()}')) \
            .props('fab color=black')

@ui.page('/my-shares')
@auth.authenticated_page
def my_shares_page(request: Request):
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
    user_permissions = app.storage.user.get('permissions', [])
    if 'share_app' not in user_permissions and 'system_admin' not in user_permissions:
        ui.label(T('permission_denied')).classes('text-red-500 m-4')
        return
    ui.page_title(T('my_shares'))

    create_header(T('my_shares'))

    user_id = app.storage.user.get('user_id')
    
    shares_container = ui.column().classes('w-full p-4 gap-4')

    def copy_link_to_clipboard(link: str):
        ui.run_javascript(f'navigator.clipboard.writeText("{link}")')
        ui.notify(T('link_copied'), type='positive')

    async def handle_delete_share(share_uuid: str, card: ui.card):
        if user_id:
            database.delete_app_share(share_uuid, user_id)
            ui.notify(T('share_link_removed'), type='positive')
            card.visible = False # Hide the card instead of full refresh

    def render_shares():
        shares_container.clear()
        if user_id:
            shares = database.get_user_shares(user_id)
            if not shares:
                with shares_container:
                    with ui.column().classes('w-full items-center justify-center p-8'):
                        ui.label(T('you_have_no_shares')).classes('text-gray-500 text-lg')
                return

            with shares_container:
                for share in shares:
                    share_link = f"{get_base_url(request)}share/{share['share_uuid']}"
                    expires_at = share['expires_at'] or T('permanent')
                    
                    with ui.card().classes('w-full shadow-md rounded-lg') as card:
                        with ui.card_section():
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.label(f"{share['app_name']} (V{share['version_number']})").classes('text-xl font-bold')
                                ui.button(icon='delete', on_click=lambda s=share['share_uuid'], c=card: handle_delete_share(s, c)).props('flat dense color=negative')
                        
                        ui.separator()

                        with ui.card_section().classes('flex flex-col gap-2'):
                            with ui.row().classes('items-center'):
                                ui.label(f"{T('expires_at')}:").classes('font-medium w-24')
                                ui.label(expires_at).classes('text-gray-600')

                            with ui.row().classes('items-center'):
                                ui.label(T('share_link') + ':').classes('font-medium w-24')
                                with ui.row().classes('items-center gap-2'):
                                    link_label = ui.label(share_link).classes('text-blue-600 hover:underline break-all cursor-pointer')
                                    link_label.on('click', lambda sl=share_link: copy_link_to_clipboard(sl))
                                    with link_label:
                                        ui.tooltip(T('click_to_copy'))

    render_shares()

@ui.page('/session/{session_id}')
@auth.authenticated_page
async def main_page(session_id: str, request: Request):
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
    ui.page_title(T('window_title'))
    ui.add_css(".nicegui-content{padding: 0; height: 100%; position: absolute; top: 0; bottom: 0; left: 0; right: 0;}")
    
    state = {
        'versions': [],
        'uuid_to_v_num': {},
        'current_preview_uuid': None,
        'ai_call_task': None,
        'last_prompt': '',
        'application_info': None,
        'session_to_delete': None,
    }

    with ui.dialog() as delete_confirm_dialog:
        with ui.card().classes('w-[90vw] max-w-md'):
            ui.label(T('confirm_delete_app_title')).classes('text-lg')
            with ui.row().classes('w-full justify-end mt-4'):
                ui.button(T('cancel'), on_click=delete_confirm_dialog.close).props('flat').classes('text-black')
                def do_delete():
                    if state['session_to_delete']:
                        database.delete_application(state['session_to_delete'])
                        ui.notify(T('app_deleted'), type='positive')
                        delete_confirm_dialog.close()
                        ui.navigate.to('/my-apps')
                ui.button(T('confirm_delete'), on_click=do_delete).classes('bg-black text-white')

    with ui.dialog() as history_dialog, ui.card().classes('w-[90vw] max-w-lg'):
        ui.label(T('version_history')).classes('text-lg font-bold')
        version_container = ui.row().classes('flex-wrap gap-2 p-3 items-center')
        with ui.row().classes('w-full justify-end mt-4'):
            ui.button(T('close'), on_click=history_dialog.close).props('flat').classes('text-black')

    # Top header removed; all actions will be provided inside the Assistant floating panel.
    # Variables preview_title_container, menu_button, edit_code_button, publish_button, and share_button
    # will be created within the Assistant panel toolbar.

    def open_delete_dialog(session_id_to_delete: str):
        app_info = state.get('application_info')
        if app_info and (app_info.get('status') == 5 or app_info.get('status') == 0):
            state['session_to_delete'] = session_id_to_delete
            delete_confirm_dialog.open()
        else:
            ui.notify(T('archive_before_delete'), type='warning')

    def open_share_dialog():
        share_link_input.set_value('')
        share_dialog.open()

    async def open_code_editor():
        if current_uuid := state.get('current_preview_uuid'):
            html_content = database.get_version_html(current_uuid) or ""
            code_dialog.open()
            ui.run_javascript(f'''
(function() {{
    const container = document.getElementById('codemirror_editor_area');
    if (!container) return;
    if (window.cmInstance && window.cmInstance.getWrapperElement) {{
        window.cmInstance.getWrapperElement().remove();
        window.cmInstance = null;
    }}
    const resources = [
        {{ type: 'style', content: `.CodeMirror {{ height: 100% !important; font-size: 16px; }}` }},
        {{ type: 'css', href: '/static/css/codemirror.min.css' }},
        {{ type: 'css', href: '/static/css/material-darker.min.css' }},
        {{ type: 'js', src: '/static/js/codemirror.min.js' }},
        {{ type: 'js', src: '/static/js/xml.min.js' }},
        {{ type: 'js', src: '/static/js/javascript.min.js' }},
        {{ type: 'js', src: '/static/js/css.min.js' }},
        {{ type: 'js', src: '/static/js/htmlmixed.min.js' }}
    ];
    let loadedCount = 0;
    function loadResource(res, onLoad) {{
        let el;
        if (res.type === 'css') {{
            el = document.createElement('link'); el.rel = 'stylesheet'; el.href = res.href; el.onload = onLoad;
        }} else if (res.type === 'js') {{
            el = document.createElement('script'); el.src = res.src; el.onload = onLoad;
        }} else if (res.type === 'style') {{
            el = document.createElement('style'); el.textContent = res.content; document.head.appendChild(el);
            setTimeout(onLoad, 0); return;
        }}
        el.onerror = () => console.error(`Failed to load resource: ${{res.href || res.src || 'inline style'}}`);
        if(el) document.head.appendChild(el);
    }}
    function onAllResourcesLoaded() {{
        if (window.CodeMirror) {{
            window.cmInstance = CodeMirror(container, {{
                value: {json.dumps(html_content)},
                lineNumbers: true, mode: "htmlmixed", theme: "material-darker",
                autofocus: true, lineWrapping: true,
            }});
            setTimeout(() => window.cmInstance.refresh(), 100);
        }} else {{ console.error('CodeMirror object not found after loading scripts.'); }}
    }}
    function loadNext() {{
        if (loadedCount < resources.length) {{
            loadResource(resources[loadedCount], () => {{ loadedCount++; loadNext(); }});
        }} else {{ onAllResourcesLoaded(); }}
    }}
    if (window.CodeMirror) {{ onAllResourcesLoaded(); }} else {{ loadNext(); }}
}})();
            ''')

    async def save_manual_edit():
        base_uuid = state.get('current_preview_uuid')
        new_html_content = await ui.run_javascript('return window.cmInstance ? window.cmInstance.getValue() : "";')
        if not base_uuid or not new_html_content:
            ui.notify(T('cannot_save_no_base'), type='negative')
            return
        code_dialog.close()
        ui.notify(T('saving_changes'), type='info')
        await _create_and_display_new_version(
            session_id=session_id, html_content=new_html_content, user_request=MANUAL_EDIT_IDENTIFIER, base_uuid=base_uuid,
            raw_ai_response=f"<think>{T('manual_edit_by_user')}</think><output-html>...</output-html>"
        )
    
    def open_publish_dialog():
        app_info = state.get('application_info')
        if not app_info:
            ui.notify(T('app_info_not_loaded'), type='negative')
            return

        app_name = app_info.get('app_name', '')
        status = app_info.get('status', 0)
        
        dialog_title.set_text(T('manage_publish'))
        app_name_input.set_value(app_name)
        confirmation_label.set_content('')
        confirmation_label.set_visibility(False)

        # Default state
        unpublish_button_in_dialog.set_visibility(False)
        cancel_submission_button.set_visibility(False)
        go_live_button.set_visibility(False)
        publish_button_in_dialog.set_visibility(True)
        app_name_input.set_visibility(True)

        if status == 1: # In Review
            dialog_title.set_text(T('managing_review_app'))
            publish_button_in_dialog.set_visibility(False)
            cancel_submission_button.set_visibility(True)
            app_name_input.set_visibility(False)
            confirmation_label.set_content(T('confirm_cancel_submission_text', name=f'<b>{html.escape(app_name)}</b>'))
            confirmation_label.set_visibility(True)

        elif status == 2: # Approved
            dialog_title.set_text(T('go_live'))
            publish_button_in_dialog.set_visibility(False)
            go_live_button.set_visibility(True)
            app_name_input.set_visibility(False)
            confirmation_label.set_content(T('confirm_go_live_text', name=f'<b>{html.escape(app_name)}</b>'))
            confirmation_label.set_visibility(True)

        elif status == 4: # Published
            dialog_title.set_text(T('manage_published_version'))
            publish_button_in_dialog.set_visibility(False)
            unpublish_button_in_dialog.set_visibility(True)
            app_name_input.set_visibility(False)
            confirmation_label.set_content(T('confirm_unpublish_text', name=f'<b>{html.escape(app_name)}</b>'))
            confirmation_label.set_visibility(True)
        
        publish_dialog.open()

    preview_frame = ui.html(f'<iframe src="about:blank" class="w-full h-full"></iframe>', sanitize=False).classes('w-full h-full')

    # Bottom footer (input bar) removed; input will be provided inside the Assistant floating panel.

    # Assistant Floating Panel: replaces header/footer UI, anchored near bottom-right with FAB trigger
    ui.add_css("""
    :root { --assistant-width-desktop: 440px; --assistant-width-tablet: 360px; --assistant-radius: 20px; }
    @media (max-width: 1024px) { :root { --assistant-width-desktop: 400px; } }
    .assistant-panel {
      position: fixed;
      right: max(env(safe-area-inset-right), 16px);
      bottom: calc(max(env(safe-area-inset-bottom), 16px) + 64px);
      width: var(--assistant-width-desktop);
      max-width: 100vw;
      height: 50vh;
      min-height: 45vh;
      max-height: 84vh;
      background: var(--q-color-white, #fff);
      color: var(--q-color-dark, #111);
      border-radius: var(--assistant-radius);
      box-shadow: 0 14px 40px rgba(0,0,0,.24);
      z-index: 2000;
      overflow: hidden;
      border: 1px solid rgba(0,0,0,.06);
    }
    @media (max-width: 768px) {
      .assistant-panel {
        width: 100%;
        left: 0;
        right: 0;
        bottom: 0;
        border-radius: 20px 20px 0 0;
        box-shadow: 0 -10px 30px rgba(0,0,0,.15);
      }
      .assistant-pointer { display: none; }
    }
    body.body--dark .assistant-panel {
      background: #111827;
      color: #E5E7EB;
      border-color: rgba(255,255,255,.08);
    }
    .q-message {
        width: 100% !important;
    }
    .assistant-panel.assistant-hidden { transform: translateY(12px) scale(.98); opacity: 0; pointer-events: none; }
    .assistant-panel.assistant-visible { transform: translateY(0) scale(1); opacity: 1; }
    .assistant-anim { transition: transform 240ms cubic-bezier(.4,0,.2,1), opacity 240ms cubic-bezier(.4,0,.2,1), height 300ms cubic-bezier(.4,0,.2,1); }
    .assistant-header { display:flex; align-items:center; justify-content:space-between; padding:8px 10px; border-bottom:1px solid rgba(0,0,0,.08); padding-top: 14px; }
    body.body--dark .assistant-header { border-color: rgba(255,255,255,.12); }
    .assistant-content { height: calc(100% - 58px); display:flex; flex-direction:column; overflow-x:hidden; }
    .assistant-messages { flex:1; overflow:auto; padding:8px; background: var(--q-color-grey-2, #f8f9fa); overflow-x:hidden;}
    body.body--dark .assistant-messages { background: #0f172a; }
    .assistant-input { display:flex; gap:8px; padding:8px; border-top:1px solid rgba(0,0,0,.08); background: inherit; }
    body.body--dark .assistant-input { border-color: rgba(255,255,255,.12); }
    .assistant-drag { position:absolute; top:0; left:0; width:100%; height:12px; background:transparent; cursor: pointer; z-index: 1; display: flex; align-items: center; justify-content: center; }
    .assistant-drag::after { content: ''; display: block; width: 40px; height: 4px; border-radius: 2px; background-color: rgba(0,0,0,.2); }
    body.body--dark .assistant-drag::after { background-color: rgba(255,255,255,.3); }
    .assistant-pointer { position:absolute; right:20px; bottom:-16px; width:26px; height:26px; background: inherit; transform: rotate(45deg); border-bottom:1px solid rgba(0,0,0,.08); border-right:1px solid rgba(0,0,0,.08); }
    body.body--dark .assistant-pointer { border-color: rgba(255,255,255,.12); }
    [dir="rtl"] .assistant-panel { left: max(env(safe-area-inset-left), 16px); right: auto; }
    [dir="rtl"] .assistant-pointer { left: 20px; right: auto; }
    .fab-robot { position: relative; }
    .fab-badge { position:absolute; top:-4px; right:-4px; min-width:18px; height:18px; border-radius:9999px; background:#ef4444; color:white; font-size:11px; display:flex; align-items:center; justify-content:center; padding:0 4px; box-shadow: 0 0 0 2px var(--q-color-white, #fff); }
    body.body--dark .fab-badge { box-shadow: 0 0 0 2px #111827; }
    .assistant-toolbar { display:flex; gap:6px; align-items:center; }
    .assistant-breadcrumb { font-size: 12px; opacity: .8; }
    .assistant-messages .nicegui-chat-message-sent { align-self: flex-end; width: 100%; position: relative; }
    .truncate-text {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .can-shrink {
        flex-shrink: 1;
        min-width: 0;
    }
    """)
    assistant_state = {
        'open': bool(app.storage.user.get('assistant_open', True)),
        'height': float(app.storage.user.get('assistant_height', 0.5)),
        'unread': 0,
    }

    # Floating Action Button (Robot) with badge and accessibility
    with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20):
        with ui.button(icon='smart_toy', on_click=lambda: toggle_assistant(None)) \
                .props('fab round color=black aria-label="Assistant"').classes('fab-robot shadow-2xl hover:shadow-3xl') as assistant_fab:
            ui.tooltip(T('conversation'))
        fab_badge = ui.html('<div class="fab-badge" style="display:none" aria-label="unread">0</div>', sanitize=False)

    # Assistant panel shell
    assistant_panel = ui.element('div').classes('assistant-panel assistant-anim')
    # set initial visibility and height
    assistant_panel.classes(add='assistant-visible' if assistant_state['open'] else 'assistant-hidden')
    assistant_panel.style(f'height: {int(assistant_state["height"]*100)}vh')
    # Set initial FAB icon based on state
    assistant_fab.props(f'icon={"close" if assistant_state["open"] else "smart_toy"}')

    # Bubble pointer and drag handle
    with assistant_panel:
        ui.element('div').classes('assistant-drag').props('aria-hidden="true"')
        ui.element('div').classes('assistant-pointer').props('aria-hidden="true"')

        # Header: breadcrumb/title on left; actions on right
        with ui.element('div').classes('assistant-header'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('chat').classes('opacity-80')
                preview_title_container = ui.row().classes('items-center gap-2 can-shrink')
                ui.label('·').classes('opacity-40')
                ui.label(T('my_apps')).classes('assistant-breadcrumb')
            with ui.element('div').classes('assistant-toolbar'):
                # Page-level actions (re-hosted from previous header/menu)
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/my-apps')) \
                    .props('flat round dense aria-label="Back to list"')

                ui.separator().props('vertical inset').classes('mx-1')
                
                with ui.button(icon='more_vert').props('flat round dense aria-label="More"') as menu_button:
                    with ui.menu().classes('bg-white shadow-lg rounded-lg border border-gray-200'):
                        with ui.menu_item(on_click=lambda: ui.navigate.to(f'/session/{uuid.uuid4()}')):
                            with ui.row().classes('items-center gap-3 px-2 py-1'):
                                ui.icon('add', size='sm').classes('opacity-70')
                                ui.label(T('new_app'))
                        with ui.menu_item(on_click=lambda: history_dialog.open()):
                            with ui.row().classes('items-center gap-3 px-2 py-1'):
                                ui.icon('history', size='sm').classes('opacity-70')
                                ui.label(T('version_history'))
                        
                        ui.separator().classes('my-1')

                        edit_code_button = ui.menu_item(on_click=lambda: open_code_editor())
                        with edit_code_button:
                            with ui.row().classes('items-center gap-3 px-2 py-1'):
                                ui.icon('code', size='sm').classes('opacity-70')
                                ui.label(T('edit_code'))

                        publish_button = ui.menu_item(on_click=lambda: open_publish_dialog())
                        with publish_button:
                            with ui.row().classes('items-center gap-3 px-2 py-1'):
                                ui.icon('publish', size='sm').classes('opacity-70')
                                publish_button_label = ui.label(T('publish_app'))

                        share_button = ui.menu_item(on_click=lambda: open_share_dialog())
                        with share_button:
                            with ui.row().classes('items-center gap-3 px-2 py-1'):
                                ui.icon('share', size='sm').classes('opacity-70')
                                ui.label(T('share'))
                        
                        ui.separator().classes('my-1')

                        with ui.menu_item(on_click=lambda: open_delete_dialog(session_id)):
                            with ui.row().classes('items-center gap-3 px-2 py-1 text-red-600'):
                                ui.icon('delete', size='sm').classes('opacity-70')
                                ui.label(T('delete_app'))

                ui.button(icon='close', on_click=lambda: toggle_assistant(False)) \
                    .props('flat round dense aria-label="Close"')

        # Content: messages and input
        with ui.element('div').classes('assistant-content'):
            # Message list with ARIA live region for polite announcements
            chat_area = ui.scroll_area().classes('assistant-messages').props('aria-live="polite" aria-atomic="false" role="log"')
            live_region = ui.html('<div class="sr-only" aria-live="polite" aria-atomic="true"></div>', sanitize=False)

            with ui.element('div').classes('assistant-input'):
                user_input = ui.textarea(placeholder=T('input_placeholder')) \
                    .props('outlined dense autogrow rounded aria-label="Message input" id="assistant_input"').classes('flex-grow')
                with ui.row().classes('items-center gap-2'):
                    send_button = ui.button(T('send'), on_click=lambda: handle_send()).props('dense rounded aria-label="Send" id="assistant_send_btn"').classes('bg-black text-white m-0')
                    stop_button = ui.button(T('stop'), on_click=lambda: cancel_ai_call()).props('flat dense rounded aria-label="Stop" id="assistant_stop_btn"').classes('bg-black text-white m-0')
                    stop_button.set_visibility(False)

    # JS: height drag and persistence, ESC close, and mobile two-stage height
    ui.run_javascript('''
    (function(){
      const panel = document.querySelector('.assistant-panel');
      const drag = panel?.querySelector('.assistant-drag');
      const badge = document.querySelector('.fab-badge');
      const input = document.getElementById('assistant_input');
      const sendBtn = document.getElementById('assistant_send_btn');
      const messages = document.querySelector('.assistant-messages');
      if(!panel || !drag) return;

      function setVHHeight(ratio){
        ratio = Math.max(0.45, Math.min(0.84, ratio));
        panel.style.height = (ratio*100) + 'vh';
        window.__assistant_height = ratio;
        window.localStorage.setItem('assistant_height', String(ratio));
      }
      // initialize from localStorage if present
      const saved = parseFloat(window.localStorage.getItem('assistant_height') || '0');
      if (!isNaN(saved) && saved>0){ setVHHeight(saved); }

      // Restore scroll position
      const savedScroll = parseFloat(window.localStorage.getItem('assistant_scroll') || '0');
      if (messages && !isNaN(savedScroll)) { messages.scrollTop = savedScroll; }

      // Click to cycle height
      const heightCycle = [0.45, 0.84]; // The cycle: 45% -> 84%
      let currentHeightIndex = -1;

      // Sets the starting point for the cycle based on the panel's current height
      const initializeIndex = () => {
          const currentHeightRatio = Math.round((panel.getBoundingClientRect().height / window.innerHeight) * 100) / 100;
          const foundIndex = heightCycle.indexOf(currentHeightRatio);
          currentHeightIndex = (foundIndex !== -1) ? foundIndex : -1;
      };
      
      // Initialize after panel is rendered to get correct initial height
      setTimeout(initializeIndex, 100);

      drag.addEventListener('click', () => {
        // Cycle to the next index
        currentHeightIndex = (currentHeightIndex + 1) % heightCycle.length;
        const newRatio = heightCycle[currentHeightIndex];
        setVHHeight(newRatio);
      });

      // Save draft to localStorage to preserve across reloads (server persistence handled separately)
      if (input) {
        const savedDraft = window.localStorage.getItem('assistant_draft') || '';
        if (savedDraft && !input.value) input.value = savedDraft;
        input.addEventListener('input', () => {
          window.localStorage.setItem('assistant_draft', input.value || '');
        });
        // Enter to send, Shift+Enter for newline
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendBtn && sendBtn.click();
          }
        });
      }

      // Persist scroll position on scroll
      if (messages) {
        messages.addEventListener('scroll', () => {
          window.localStorage.setItem('assistant_scroll', String(messages.scrollTop || 0));
        }, {passive: true});
      }

      // ESC to close: dispatch event (server sync) and close panel
      document.addEventListener('keydown', (e)=>{
        if(e.key === 'Escape'){
          window.dispatchEvent(new CustomEvent('assistant-close'));
          window.__assistant && window.__assistant.close();
        }
      });

      // expose helpers
      window.__assistant = {
        open(){ panel.classList.remove('assistant-hidden'); panel.classList.add('assistant-visible'); },
        close(){
          // persist current scroll
          const list = document.querySelector('.assistant-messages');
          if (list) { window.localStorage.setItem('assistant_scroll', String(list.scrollTop || 0)); }
          panel.classList.remove('assistant-visible'); panel.classList.add('assistant-hidden');
        },
        setBadge(n){ if(!badge) return; if(n>0){ badge.style.display='flex'; badge.textContent=String(n); } else { badge.style.display='none'; } }
      };
    })();
    ''')

    def set_unread(n: int):
        assistant_state['unread'] = max(0, n)
        ui.run_javascript(f'window.__assistant && window.__assistant.setBadge({assistant_state["unread"]});')

    def toggle_assistant(open_or_toggle: bool | None = None):
        nonlocal assistant_panel, assistant_state, assistant_fab
        target = (not assistant_state['open']) if open_or_toggle is None else bool(open_or_toggle)
        
        if target == assistant_state['open']: return
        
        assistant_state['open'] = target
        app.storage.user['assistant_open'] = target
        
        assistant_fab.props(f'icon={"close" if target else "smart_toy"}')

        if target:
            assistant_panel.classes(remove='assistant-hidden', add='assistant-visible')
            draft = app.storage.user.get('assistant_draft', '')
            if draft: user_input.set_value(draft)
            set_unread(0)
            ui.timer(0.25, lambda: user_input.focus(), once=True)
            ui.run_javascript("(function(){ const list=document.querySelector('.assistant-messages'), y=parseFloat(localStorage.getItem('assistant_scroll')||'0'); if(list&&!isNaN(y)) list.scrollTop=y; })();")
        else:
            assistant_panel.classes(remove='assistant-visible', add='assistant-hidden')
            ui.run_javascript("(function(){ const list=document.querySelector('.assistant-messages'); if(list) localStorage.setItem('assistant_scroll',String(list.scrollTop||0)); })();")
            ui.timer(0.25, lambda: assistant_fab.focus(), once=True)

    # Close on ESC without masking the page; keep server-side state in sync
    ui.on('assistant-close', lambda: toggle_assistant(False))
    # Persist draft to server-side session periodically (for cross-page navigation)
    ui.timer(0.8, lambda: app.storage.user.__setitem__('assistant_draft', user_input.value))
    
    # edit_code_button and publish_button are now menu items, their visibility is controlled by the parent menu.
    # edit_code_button.set_visibility(False)
    # publish_button.set_visibility(False)

    with ui.dialog() as publish_dialog:
        with ui.card().classes('w-[90vw] max-w-lg rounded-lg shadow-xl'):
            dialog_title = ui.label().classes('text-lg font-bold')
            confirmation_label = ui.html(sanitize=False).classes('mt-4 text-base')
            app_name_input = ui.input(label=T('app_name_label')).props('outlined dense rounded-lg').classes('w-full mt-4')
            with ui.row().classes('w-full justify-end gap-2 mt-6') as button_row:
                unpublish_button_in_dialog = ui.button(T('unpublish'), on_click=lambda: handle_unpublish()).props('flat dense').classes('text-black hover:bg-gray-200 rounded-lg')
                cancel_submission_button = ui.button(T('cancel_submission'), on_click=lambda: handle_cancel_submission()).props('flat dense').classes('text-black hover:bg-gray-200 rounded-lg')
                go_live_button = ui.button(T('go_live'), on_click=lambda: handle_go_live()).props('flat dense').classes('text-white bg-black hover:bg-gray-800 rounded-lg')
                ui.button(T('cancel'), on_click=publish_dialog.close).props('flat dense').classes('text-black hover:bg-gray-200 rounded-lg')
                publish_button_in_dialog = ui.button(T('publish'), on_click=lambda: handle_publish(app_name_input.value)).props('dense').classes('bg-black text-white hover:bg-gray-800 rounded-lg')

    with ui.dialog() as share_dialog:
        with ui.card().classes('w-full max-w-md'):
            ui.label(T('share_app_version')).classes('text-lg font-bold')
            duration_select = ui.select({
                '1': T('1_day'),
                '7': T('7_days'),
                '30': T('1_month'),
                '0': T('permanent')
            }, label=T('share_duration'), value='7').classes('w-full')
            share_link_input = ui.input(T('share_link')).props('readonly outlined dense').classes('w-full mt-4')
            
            def handle_share():
                user_permissions = app.storage.user.get('permissions', [])
                if 'share_app' not in user_permissions and 'system_admin' not in user_permissions:
                    ui.notify(T('permission_denied'), type='negative')
                    return
                duration = int(duration_select.value)
                expires_at = None
                if duration > 0:
                    expires_at = datetime.datetime.now() + datetime.timedelta(days=duration)
                
                current_uuid = state.get('current_preview_uuid')
                user_id = app.storage.user.get('user_id')
                
                if current_uuid and user_id:
                    share_uuid = database.create_app_share(current_uuid, user_id, expires_at)
                    link = f"{get_base_url(request)}share/{share_uuid}"
                    share_link_input.set_value(link)
                    ui.run_javascript(f'navigator.clipboard.writeText("{link}")')
                    ui.notify(f"{T('share_link_generated')} - {T('link_copied')}", type='positive')
                else:
                    ui.notify(T('cannot_generate_share_link'), type='negative')

            with ui.row().classes('w-full justify-end mt-4'):
                ui.button(T('generate_link'), on_click=handle_share).classes('bg-black text-white')
                ui.button(T('close'), on_click=share_dialog.close).props('flat').classes('text-black')

    with ui.dialog().props('maximized no-padding') as code_dialog:
        with ui.card().classes('w-full h-full flex flex-col p-0 relative'):
            ui.html('<div id="codemirror_editor_area" style="height: 100%;"></div>', sanitize=False).classes('w-full h-full pb-16')
            with ui.row().classes('w-full p-3 bg-gray-100 border-t justify-end gap-2 absolute bottom-0 left-0 right-0 h-16'):
                ui.button(T('cancel'), on_click=code_dialog.close).props('flat dense').classes('text-black')
                ui.button(T('save_changes'), on_click=lambda: save_manual_edit()).props('dense').classes('bg-black text-white')

    with ui.dialog().props('persistent').style('z-index: 99999') as loading_dialog:
        with ui.card().classes('bg-transparent shadow-none items-center'):
            ui.spinner(size='lg', color='white')
            ui.label(T('processing_request')).classes('ml-4 text-white')

    async def cancel_ai_call():
        if state['ai_call_task']:
            state['ai_call_task'].cancel()
            # keep panel open; restore input for edit
            user_input.set_value(state.get('last_prompt', ''))

    def set_ui_interactive(interactive: bool):
        user_input.set_enabled(interactive)
        send_button.set_enabled(interactive)
        for child in version_container.default_slot.children:
            if isinstance(child, ui.button):
                child.set_enabled(interactive)
        
        has_preview = state.get('current_preview_uuid') is not None
        
        def set_element_enabled(element: ui.element, enabled: bool):
            element.props(remove='disable') if enabled else element.props('disable')

        menu_button.set_enabled(interactive and has_preview)
        
        user_permissions = app.storage.user.get('permissions', [])
        can_publish = 'publish_app' in user_permissions or 'system_admin' in user_permissions
        set_element_enabled(publish_button, can_publish and interactive and has_preview)
        set_element_enabled(edit_code_button, interactive and has_preview)
        user_permissions = app.storage.user.get('permissions', [])
        can_share = 'share_app' in user_permissions or 'system_admin' in user_permissions
        set_element_enabled(share_button, can_share and interactive and has_preview)

        stop_button.set_visibility(not interactive)

    async def _run_ai_generation_task(prompt_text: str, output_container: ui.html, chat_area: ui.scroll_area) -> dict | None:
        # ... (AI generation logic remains the same)
        full_response_content = ""
        try:
            active_model = database.get_active_model_for_task('code_generation')
            if not active_model:
                user_permissions = app.storage.user.get('permissions', [])
                error_message = T('ai_settings_incomplete')
                
                if 'system_admin' in user_permissions:
                    error_message += T('go_to_management_for_config')

                logger.error("No active code generation model found. Please configure it in the management settings.")
                output_container.set_content(f'<div style="color: red;">{error_message}</div>')
                return None

            AI_API_KEY = active_model['api_key']
            AI_MODEL = active_model['model_name']
            AI_ENDPOINT = active_model['endpoint_url']
            system_prompt_template = database.get_prompt(database.DEFAULT_PROMPT_NAME)
            if not system_prompt_template: raise ValueError(T('system_prompt_not_found'))
            current_uuid = state.get('current_preview_uuid')
            previous_html = database.get_version_html(current_uuid) if current_uuid else f"<!-- {T('new_application')} -->"
            conversation_history_str = _build_conversation_history_string(current_uuid)
            final_prompt = system_prompt_template.format(
                previous_html_code=previous_html, conversation_history=conversation_history_str, user_request=prompt_text
            )
            async with httpx.AsyncClient(timeout=600.0, verify=False) as client:
                async with client.stream("POST", AI_ENDPOINT, headers={"Authorization": f"Bearer {AI_API_KEY}"}, json={"model": AI_MODEL, "messages": [{"role": "system", "content": final_prompt}], "stream": True}) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_text():
                        for line in chunk.splitlines():
                            if line.startswith("data: "):
                                data_str = line[len("data: "):].strip()
                                if data_str == "[DONE]": break
                                try:
                                    data = json.loads(data_str)
                                    if 'content' in (delta := data['choices'][0]['delta']) and delta['content']:
                                        token = delta['content']
                                        full_response_content += token
                                        escaped_content = html.escape(full_response_content)
                                        output_container.set_content(f'<pre style="white-space: pre-wrap; word-break: break-word;">{escaped_content}</pre>')
                                        chat_area.scroll_to(percent=1.0, duration=0)
                                except (json.JSONDecodeError, KeyError, IndexError): continue
            _think_text, html_content = parse_ai_response(full_response_content)
            if not html_content: raise ValueError(T('ai_no_html'))
            return {"html_content": html_content, "raw_ai_response": full_response_content}
        except asyncio.CancelledError:
            return None
        except Exception as e:
            error_message = ""
            if isinstance(e, httpx.HTTPStatusError):
                try:
                    error_message = f"{T('api_request_failed')}<br><pre>{html.escape(e.response.text)}</pre>"
                except httpx.ResponseNotRead:
                    error_message = T('ai_busy_or_no_response')
            elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
                error_message = T('cannot_connect_ai')
            elif isinstance(e, httpx.ResponseNotRead):
                error_message = T('ai_busy_or_no_response')
            else:
                error_message = f"{T('unexpected_error')}<br><pre>{html.escape(str(e))}</pre>"
            
            with chat_area:
                notification_message = T('ai_busy_or_no_response') if isinstance(e, httpx.ResponseNotRead) else T('error_notification', e=e)
            
            output_container.set_content(f'<div style="color: red;">{error_message}</div>')
            return None
    
    async def _generate_app_template(app_html_code: str, output_container: ui.html, chat_area: ui.scroll_area) -> str | None:
        """使用 AI 為應用生成一個預覽模板。"""
        full_response_content = ""
        try:
            # 直接使用預設的 AI 設定，不再從資料庫讀取
            active_model = database.get_active_model_for_task('preview_generation')
            if not active_model:
                logger.error(T('ai_settings_incomplete_for_preview'))
                raise ValueError(T('ai_settings_incomplete_for_preview'))

            AI_API_KEY = active_model['api_key']
            AI_MODEL = active_model['model_name']
            AI_ENDPOINT = active_model['endpoint_url']

            template_prompt = database.get_prompt(database.APP_TEMPLATE_PROMPT_NAME)
            if not template_prompt:
                raise ValueError("App template prompt not found.")

            final_prompt = template_prompt.format(app_html_code=app_html_code)

            async with httpx.AsyncClient(timeout=600.0, verify=False) as client:
                async with client.stream("POST", AI_ENDPOINT, headers={"Authorization": f"Bearer {AI_API_KEY}"}, json={"model": AI_MODEL, "messages": [{"role": "system", "content": final_prompt}], "stream": True}) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_text():
                        for line in chunk.splitlines():
                            if line.startswith("data: "):
                                data_str = line[len("data: "):].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    if 'content' in (delta := data['choices'][0]['delta']) and delta['content']:
                                        token = delta['content']
                                        full_response_content += token
                                        escaped_content = html.escape(full_response_content)
                                        output_container.set_content(f'<pre style="white-space: pre-wrap; word-break: break-word;">{escaped_content}</pre>')
                                        chat_area.scroll_to(percent=1.0, duration=0)
                                except (json.JSONDecodeError, KeyError, IndexError):
                                    continue
            
            _, html_content = parse_ai_response(full_response_content)
            if not html_content:
                raise ValueError("AI failed to generate valid template HTML.")
            
            return html_content

        except Exception as e:
            error_message = f"<b>{T('template_generation_failed')}:</b><br><pre>{html.escape(str(e))}</pre>"
            output_container.set_content(f'<div style="color: red;">{error_message}</div>')
            return None

    async def handle_send():
        prompt_text = user_input.value
        if not prompt_text:
            return

        # Ensure panel is open for immediate feedback
        if not assistant_state['open']:
            toggle_assistant(True)

        state['last_prompt'] = prompt_text
        set_ui_interactive(False)
        user_input.set_value('')

        # Preserve existing messages and append, do not clear scroll history
        with chat_area:
            ui.chat_message(prompt_text, name=T('chat_you'), sent=True)
            with ui.chat_message(name=T('chat_ai'), sent=False):
                output_container = ui.html(T('ai_thinking'), sanitize=False)

        task = asyncio.create_task(_run_ai_generation_task(prompt_text, output_container, chat_area))
        state['ai_call_task'] = task

        try:
            result = await task
            if result:
                current_uuid = state.get('current_preview_uuid')
                await _create_and_display_new_version(
                    session_id=session_id, html_content=result['html_content'],
                    user_request=prompt_text, base_uuid=current_uuid,
                    raw_ai_response=result['raw_ai_response']
                )
            else:
                # AI call failed, restore the input
                user_input.set_value(state.get('last_prompt', ''))
        except asyncio.CancelledError:
            pass
        finally:
            set_ui_interactive(True)
            state['ai_call_task'] = None
            # If panel is collapsed during streaming, increment unread
            if not assistant_state['open']:
                set_unread(assistant_state['unread'] + 1)

    def update_version_buttons_display():
        app_info = state.get('application_info')
        live_uuid = app_info['live_version_uuid'] if app_info and app_info.get('live_version_uuid') else None
        
        version_container.clear()
        with version_container:
            for i, ver_info in enumerate(state['versions']):
                v_num = i + 1
                is_live = ver_info['uuid'] == live_uuid
                btn_text = f'V{v_num}'
                
                button = ui.button(on_click=lambda u=ver_info['uuid']: show_version(u)).props('flat dense').classes('text-black hover:bg-gray-200 rounded-lg px-3 py-1')
                with button:
                    if is_live:
                        ui.icon('star', size='xs').classes('mr-1 text-black')
                    ui.label(btn_text)

                tooltip_text = T('based_on_v', v_num=state["uuid_to_v_num"][ver_info['base_uuid']]) if (base_uuid := ver_info.get('base_uuid')) and base_uuid in state['uuid_to_v_num'] else ''
                if is_live:
                    tooltip_text += f" {T('published_mark')}"
                if tooltip_text:
                    with button:
                        ui.tooltip(tooltip_text.strip())

    def update_publish_button_text():
        app_info = state.get('application_info')
        text = T('publish_app') # Default text
        if app_info:
            status = app_info.get('status', 0)
            status_map = {
                1: T('under_review'),
                2: T('go_live'),
                4: T('manage_published_version'),
            }
            text = status_map.get(status, T('publish_app'))
        
        publish_button_label.set_text(text)

    async def handle_cancel_submission():
        database.cancel_submission(session_id)
        app_info = database.get_application_by_session(session_id)
        state['application_info'] = dict(app_info) if app_info else None
        update_publish_button_text()
        ui.notify(T('submission_cancelled'), type='positive')
        publish_dialog.close()

    async def handle_go_live():
        database.publish_application(session_id)
        app_info = database.get_application_by_session(session_id)
        state['application_info'] = dict(app_info) if app_info else None
        update_publish_button_text()
        ui.notify(T('app_live_success'), type='positive')
        publish_dialog.close()

    async def handle_publish(app_name: str):
        user_permissions = app.storage.user.get('permissions', [])
        if 'publish_app' not in user_permissions and 'system_admin' not in user_permissions:
            ui.notify(T('permission_denied'), type='negative')
            return
        if not app_name:
            ui.notify(T('app_name_required'), type='warning')
            return
        
        current_uuid = state.get('current_preview_uuid')
        if not current_uuid: return
        
        user_id = app.storage.user.get('user_id')
        if not user_id:
            ui.notify(T('user_info_error'), type='negative')
            return

        publish_dialog.close()
        loading_dialog.open()
        
        try:
            # 先創建或更新應用程式記錄，但不立即生成預覽
            database.create_or_update_application(session_id, current_uuid, app_name, user_id)
            
            app_info = state.get('application_info')
            latest_live_uuid = app_info.get('live_version_uuid') if app_info else None

            # 如果沒有最新的 live UUID，則標記為待處理，讓後台任務來生成預覽
            database.update_preview_generation_status(session_id, 1) # 1: Pending
            ui.notify(T('app_submitted_for_review'), type='info')
            
            # if not latest_live_uuid:
            #     # 標記為待處理，讓後台任務來生成
            #     database.update_preview_generation_status(session_id, 1) # 1: Pending
            #     ui.notify("應用已提交審核，預覽圖將在後台生成。", type='info')
            # else:
            #     # 如果重用舊範本，直接複製
            #     old_template_html = database.get_version_template(latest_live_uuid)
            #     if old_template_html:
            #         database.update_version_template(current_uuid, old_template_html)
            #         database.update_preview_generation_status(session_id, 3) # 3: Completed
            #         ui.notify("已重用舊版本的應用模版。", type='info')
            #     else:
            #         # 如果舊範本不存在，也交給後台處理
            #         database.update_preview_generation_status(session_id, 1) # 1: Pending
            #         ui.notify("找不到舊版預覽，將在後台為您生成新的預覽。", type='info')

            new_app_info = database.get_application_by_session(session_id)
            state['application_info'] = dict(new_app_info) if new_app_info else None
            update_publish_button_text()

        except Exception as e:
            ui.notify(T('publish_failed', e=e), type='negative')
        finally:
            loading_dialog.close()

    async def handle_unpublish():
        database.archive_application(session_id)
        app_info = database.get_application_by_session(session_id)
        state['application_info'] = dict(app_info) if app_info else None
        update_publish_button_text()
        ui.notify(T('app_unpublished_success'), type='positive')
        publish_dialog.close()

    async def _create_and_display_new_version(session_id: str, html_content: str, user_request: str, base_uuid: str | None, raw_ai_response: str):
        new_uuid = str(uuid.uuid4())
        
        base_template = None
        if base_uuid:
            base_template = database.get_version_template(base_uuid)

        version_data = {
            "uuid": new_uuid, "session_id": session_id, "user_request": user_request,
            "base_version_uuid": base_uuid, "raw_ai_response": raw_ai_response,
            "html_content": html_content, "app_template_html": base_template
        }
        database.add_version(version_data)
        
        new_v_num = len(state['versions']) + 1
        state['versions'].append({'uuid': new_uuid, 'base_uuid': base_uuid, 'request': user_request, 'raw_ai_response': raw_ai_response, 'app_template_html': base_template})
        state['uuid_to_v_num'][new_uuid] = new_v_num
        
        if not base_uuid: # This is the first version (V1)
            user_id = app.storage.user.get('user_id')
            if user_id:
                database.create_draft_application(session_id, new_uuid, user_id)
                # Refresh application info in state after creating draft
                app_info = database.get_application_by_session(session_id)
                if app_info:
                    state['application_info'] = dict(app_info)
                    update_publish_button_text()
                    menu_button.set_visibility(True)

        update_version_buttons_display()
        await show_version(new_uuid)
        
        v_num_text = T('generated_v', v_num=new_v_num)
        base_text = ""
        if base_uuid and base_uuid in state['uuid_to_v_num']:
            base_text = T('based_on_v_suffix', v_num=state['uuid_to_v_num'][base_uuid])
        
        ui.notify(f"{v_num_text}{base_text}")

    async def show_version(uuid_to_show: str):
        state['current_preview_uuid'] = uuid_to_show
        
        v_num = state['uuid_to_v_num'].get(uuid_to_show, '?')
        version_info = next((v for v in state['versions'] if v['uuid'] == uuid_to_show), None)
        base_text = ""
        if version_info and (base_uuid := version_info.get('base_uuid')) and base_uuid in state['uuid_to_v_num']:
            base_text = T('based_on_v_suffix', v_num=state['uuid_to_v_num'][base_uuid])

        with preview_title_container:
            preview_title_container.clear()
            ui.label(T('preview_title', v_num=v_num, base_text=base_text)).classes('text-lg font-bold truncate-text')

        preview_frame.set_content(f'<iframe src="/session/render/{uuid_to_show}" class="w-full h-full border-none"></iframe>')
        
        user_input.set_value('')
        user_input.props(f'placeholder="{T("request_changes_for_v", v_num=v_num)}"')
        
        chat_area.clear()
        with chat_area:
            history = reconstruct_chat_history(uuid_to_show)
            for item in history:
                # User's request
                request_text = T('manual_edit_request') if item['request'] == MANUAL_EDIT_IDENTIFIER else item['request']
                ui.chat_message(request_text, name=T('chat_you'), sent=True)

                # AI's full response
                raw_response = item.get('raw_ai_response')
                if raw_response:
                    think_text, html_content = parse_ai_response(raw_response)
                    with ui.chat_message(name=T('chat_ai'), sent=False):
                        if think_text:
                            ui.html(f'<pre style="white-space: pre-wrap; word-break: break-word;">{html.escape(think_text)}</pre>', sanitize=False)
                        
                        # Also add a confirmation that a version was generated, if HTML was produced
                        if html_content:
                            v_num = state['uuid_to_v_num'].get(item['uuid'], '?')
                            ui.label(T('generated_v', v_num=v_num)).classes('text-sm text-gray-500 mt-2')
            
            # Scroll to the bottom after a short delay to ensure the UI has updated
            ui.timer(0.2, lambda: chat_area.scroll_to(percent=1.0, duration=0.1), once=True)

        edit_code_button.set_visibility(True)
        user_permissions = app.storage.user.get('permissions', [])
        if 'publish_app' in user_permissions or 'system_admin' in user_permissions:
            publish_button.set_visibility(True)
        if 'share_app' in user_permissions or 'system_admin' in user_permissions:
            share_button.set_visibility(True)

    def reconstruct_chat_history(target_uuid: str):
        history = []
        current_uuid = target_uuid
        versions_map = {v['uuid']: v for v in state['versions']}
        while current_uuid and current_uuid in versions_map:
            version_info = versions_map[current_uuid]
            if version_info.get('request'):
                history.append(version_info)
            current_uuid = version_info.get('base_uuid')
        return history[::-1]

    def _build_conversation_history_string(target_uuid: str | None) -> str:
        if not target_uuid:
            return T('no_history')
        raw_history = reconstruct_chat_history(target_uuid)
        history_items = []
        for item in raw_history:
            request_text = T('manual_edit_request') if item['request'] == MANUAL_EDIT_IDENTIFIER else item['request']
            history_items.append(T('user_request_history', v_num=state['uuid_to_v_num'].get(item['uuid'], '?'), request=request_text))
        return "\n".join(history_items) if history_items else T('no_history')

    # 實現使用者需求：當輸入框為空時，禁用發送按鈕，使其變灰且不可點擊。
    send_button.bind_enabled_from(user_input, 'value', lambda value: bool(value and value.strip()))

    # Load application info
    application_info = database.get_application_by_session(session_id)
    if application_info:
        state['application_info'] = dict(application_info)
        menu_button.set_visibility(True)

    session_versions_rows = database.get_session_versions(session_id)
    for i, row in enumerate(session_versions_rows):
        v_num = i + 1
        version_info = dict(row)
        # Ensure the key 'base_uuid' exists for history reconstruction, matching what the app expects.
        version_info['base_uuid'] = version_info.get('base_version_uuid')
        version_info['request'] = version_info.get('user_request')
        state['versions'].append(version_info)
        state['uuid_to_v_num'][row['uuid']] = v_num

    update_version_buttons_display()
    update_publish_button_text()

    if state['versions']:
        await show_version(state['versions'][-1]['uuid'])
        edit_code_button.set_visibility(True)
        
        user_permissions = app.storage.user.get('permissions', [])
        if 'publish_app' in user_permissions or 'system_admin' in user_permissions:
            publish_button.set_visibility(True)
    else:
        # For new creations, show a welcome message in the chat and preview
        with chat_area:
            ui.chat_message(T('welcome_message'), name=T('chat_system'), sent=False)
        preview_frame.set_content(f'<div class="w-full h-full flex items-center justify-center bg-gray-100 text-gray-600">{T("welcome_message")}</div>')
        edit_code_button.set_visibility(False)
        publish_button.set_visibility(False)
        share_button.set_visibility(False)
        menu_button.set_enabled(False)


app.add_static_files('/static', 'static')

async def preview_generation_worker():
    """後台工作線程，負責生成應用預覽。"""
    while True:
        try:
            apps_to_process = database.get_applications_for_preview_generation()
            if not apps_to_process:
                await asyncio.sleep(30) # 如果沒有任務，等待30秒
                continue

            for app_row in apps_to_process:
                session_id = app_row['session_id']
                version_uuid = app_row['latest_submitted_version_uuid']
                html_content = app_row['html_content']
                
                logger.info(f"開始為 session {session_id} 生成預覽...")
                database.update_preview_generation_status(session_id, 2) # 2: In Progress

                try:
                    # 這裡我們需要一個簡化的 _generate_app_template 版本，它不需要 UI 元件
                    # 我們可以創建一個新的輔助函數來處理這個問題
                    template_html = await _generate_app_template_headless(html_content)

                    if template_html:
                        database.update_version_template(version_uuid, template_html)
                        database.update_preview_generation_status(session_id, 3) # 3: Completed
                        logger.info(f"成功為 session {session_id} 生成預覽。")
                    else:
                        raise ValueError(T('template_generation_failed'))

                except Exception as e:
                    logger.error(T('preview_generation_failed_for_session', session_id=session_id, e=e))
                    database.increment_preview_generation_retries(session_id)
                    database.update_preview_generation_status(session_id, 4) # 4: Failed
            
            await asyncio.sleep(10) # 完成一輪後等待10秒

        except Exception as e:
            logger.error(T('preview_worker_error', e=e))
            await asyncio.sleep(60) # 如果發生嚴重錯誤，等待1分鐘再試

async def _generate_app_template_headless(app_html_code: str) -> str | None:
    """一個無頭版本的應用模板生成函數，不依賴 UI。"""
    try:
        active_model = database.get_active_model_for_task('preview_generation')
        if not active_model:
            raise ValueError(T('ai_settings_incomplete_for_preview'))

        AI_API_KEY = active_model['api_key']
        AI_MODEL = active_model['model_name']
        AI_ENDPOINT = active_model['endpoint_url']

        template_prompt = database.get_prompt(database.APP_TEMPLATE_PROMPT_NAME)
        if not template_prompt:
            raise ValueError(T('app_template_prompt_not_found'))

        final_prompt = template_prompt.format(app_html_code=app_html_code)
        full_response_content = ""

        async with httpx.AsyncClient(timeout=600.0, verify=False) as client:
            async with client.stream("POST", AI_ENDPOINT, headers={"Authorization": f"Bearer {AI_API_KEY}"}, json={"model": AI_MODEL, "messages": [{"role": "system", "content": final_prompt}], "stream": True}) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    for line in chunk.splitlines():
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                if 'content' in (delta := data['choices'][0]['delta']) and delta['content']:
                                    full_response_content += delta['content']
                            except (json.JSONDecodeError, KeyError, IndexError): continue
        
        _, html_content = parse_ai_response(full_response_content)
        return html_content if html_content else None

    except Exception as e:
        logger.error(T('headless_template_generation_failed', e=e))
        return None
    
def _fix_broken_json(json_str: str) -> str:
    """
    A desperate attempt to fix the broken JSON returned by the AI.
    This is brittle and should be replaced if the AI model is improved.
    """
    # Add missing quotes around keys
    json_str = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', json_str)
    
    # Ensure there's a comma between the risks and categories arrays
    # Ensure there's a comma between adjacent array definitions
    json_str = re.sub(r'(]\s*)"(\w+)"\s*:', r'\1, "\2":', json_str)

    # Ensure the keys are correct
    json_str = json_str.replace('"ks":', '"risks":') # Legacy fix
    json_str = json_str.replace('"critical_risks":', '"critical_risks":')
    json_str = json_str.replace('"medium_risks":', '"medium_risks":')
    json_str = json_str.replace('"low_risks":', '"low_risks":')

    # Try to fix unterminated strings and add missing brackets/braces
    # This is getting very risky
    if '"critical_risks"' in json_str and '"categories"' not in json_str:
        # This is a bit of a guess, but if we have risks, we probably need categories
        json_str = json_str.replace('categories', '"categories"')

    # Add missing closing bracket for risks array if it looks like it's missing
    if json_str.count('[') > json_str.count(']'):
        json_str += ']'
        
    # Add missing closing brace if it looks like it's missing
    if json_str.count('{') > json_str.count('}'):
        json_str += '}'

    return json_str

async def _generate_risk_report_headless(app_html_code: str, lang: str) -> dict | None:
    """A headless function to generate a risk and category analysis report for an application."""
    try:
        active_model = database.get_active_model_for_task('report_generation')
        if not active_model:
            raise ValueError("AI settings for preview/analysis are incomplete.")

        AI_API_KEY = active_model['api_key']
        AI_MODEL = active_model['model_name']
        AI_ENDPOINT = active_model['endpoint_url']

        # get_prompt now handles language code replacement automatically
        risk_prompt_template = database.get_prompt(database.RISK_ANALYSIS_PROMPT_NAME)
        if not risk_prompt_template:
            raise ValueError(T('risk_analysis_prompt_not_found'))

        # Get existing risk and category tags
        existing_critical_risks = database.get_features_by_type('critical_risk')
        existing_medium_risks = database.get_features_by_type('medium_risk')
        existing_low_risks = database.get_features_by_type('low_risk')
        existing_categories = database.get_features_by_type('category')

        # 格式化標籤列表以供提示使用
        critical_risks_str = "\n".join(f"- {r}" for r in existing_critical_risks) if existing_critical_risks else T('no_existing_risks')
        medium_risks_str = "\n".join(f"- {r}" for r in existing_medium_risks) if existing_medium_risks else T('no_existing_risks')
        low_risks_str = "\n".join(f"- {r}" for r in existing_low_risks) if existing_low_risks else T('no_existing_risks')
        categories_str = "\n".join(f"- {c}" for c in existing_categories) if existing_categories else T('no_existing_risks')

        temp_prompt = risk_prompt_template.replace('{app_html_code}', app_html_code)
        temp_prompt = temp_prompt.replace('{existing_critical_risks}', critical_risks_str)
        temp_prompt = temp_prompt.replace('{existing_medium_risks}', medium_risks_str)
        temp_prompt = temp_prompt.replace('{existing_low_risks}', low_risks_str)
        final_prompt = temp_prompt.replace('{existing_categories}', categories_str)
        final_prompt = final_prompt.replace('{app_lang_code}', lang) # Pass the user's language
        full_response_content = ""

        async with httpx.AsyncClient(timeout=300.0, verify=False) as client:
            async with client.stream("POST", AI_ENDPOINT, headers={"Authorization": f"Bearer {AI_API_KEY}"}, json={"model": AI_MODEL, "messages": [{"role": "system", "content": final_prompt}], "stream": True}) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    for line in chunk.splitlines():
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                if 'content' in (delta := data['choices'][0]['delta']) and delta['content']:
                                    full_response_content += delta['content']
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', full_response_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = full_response_content.strip()

        json_str = _fix_broken_json(json_str)

        try:
            report_data = json.loads(json_str)
            # The new format will have language keys
            if isinstance(report_data, dict) and ('en' in report_data or lang in report_data):
                return report_data
            else:
                logger.error(f"JSON missing language keys. Got: {report_data}")
                raise ValueError(f"JSON missing language keys. Got: {report_data}")
        except json.JSONDecodeError:
            logger.error(f"{T('invalid_json_response')}. Response was: {full_response_content}")
            raise ValueError(T('invalid_json_response'))

    except Exception as e:
        logger.error(T('headless_risk_report_failed', e=e), exc_info=True)
        raise e
def startup_background_tasks():
    """在應用啟動時運行後台任務。"""
    loop = asyncio.get_event_loop()
    loop.create_task(preview_generation_worker())
    logger.info(T('preview_worker_started'))

if __name__ in {"__main__", "__mp_main__"}:
    # 註冊所有管理頁面路由
    management_pages.create_management_pages()
    
    app.on_startup(startup_background_tasks)

    ui.run(title="Vibe", port=8462, show=True, storage_secret='Sk-sd23As8966y2@#CW$%Cys7v98923yv@#23892c23er@#ED328rc23', favicon='vibe_logo.png')

