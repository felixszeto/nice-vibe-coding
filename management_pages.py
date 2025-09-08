import logging
from nicegui import ui, app
import database
import auth
from languages import T
from fastapi import HTTPException
from nicegui.events import ValueChangeEventArguments
import main # Import the main module to access the headless function
from languages import set_language

def create_management_pages():
    """
    創建一個統一的後台管理頁面，採用左右佈局。
    左側是導航菜單，右側是內容顯示區域。
    """
    # API Endpoint for generating risk report
    async def _internal_generate_and_store_report(version_uuid: str, lang: str):
        """
        Internal logic to generate and store a risk report.
        Raises exceptions on failure.
        """
        # 1. Get HTML content from the database
        html_content = database.get_version_html(version_uuid)
        if not html_content:
            raise ValueError("Version not found or has no HTML content")

        # 2. Call the headless AI function to analyze the HTML
        analysis_result = await main._generate_risk_report_headless(html_content, lang)

        if not analysis_result:
            raise RuntimeError("AI analysis failed to generate a report.")

        # 3. Store the analysis results in the database for each language
        for lang_code, report in analysis_result.items():
            risk_types = {
                "critical_risks": "critical_risk",
                "medium_risks": "medium_risk",
                "low_risks": "low_risk"
            }
            for key, feature_type in risk_types.items():
                for risk_name in report.get(key, []):
                    feature_id = database.add_or_get_feature(feature_type, risk_name, lang_code)
                    database.link_feature_to_version(version_uuid, feature_id)

            for category_name in report.get("categories", []):
                feature_id = database.add_or_get_feature('category', category_name, lang_code)
                database.link_feature_to_version(version_uuid, feature_id)
        
            # 4. Store functional description and operating instructions in the versions table (from the primary lang)
            if lang_code == lang:
                functional_description = report.get("functional_description", "")
                operating_instructions = report.get("operating_instructions", "")
                database.update_version_details(version_uuid, functional_description, operating_instructions)
        
        # 5. Return the analysis result directly, as it's already in the correct format for the UI.
        return analysis_result.get(lang, analysis_result.get('en'))

    @app.post('/api/applications/{version_uuid}/generate_report')
    async def generate_application_report(version_uuid: str, lang: str = 'en'):
        try:
            report_data = await _internal_generate_and_store_report(version_uuid, lang)
            return report_data
        except (ValueError, RuntimeError) as e:
            logging.warning(f"Failed to generate report for {version_uuid}: {e}")
            status_code = 404 if isinstance(e, ValueError) else 500
            raise HTTPException(status_code=status_code, detail=str(e))
        except Exception as e:
            logging.error(f"Unexpected error generating report for {version_uuid}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


    @ui.page('/management')
    @auth.authenticated_page
    def management_layout_page():
        ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">')
        # 權限檢查
        user_permissions = app.storage.user.get('permissions', [])
        has_full_access = 'system_admin' in user_permissions
        has_review_access = 'review_app' in user_permissions

        if not has_full_access and not has_review_access:
            ui.label(T('permission_denied')).classes('text-red-500 m-4')
            return

        # 頁面主樣式
        ui.add_head_html('<style>.nicegui-content { padding: 0 !important; }</style>')
        ui.add_head_html('''
            <style>
            .custom-checkbox .q-checkbox__inner--truthy .q-checkbox__bg {
                background: black !important;
                border-color: black !important;
            }
            .custom-checkbox .q-checkbox__inner--truthy .q-checkbox__icon {
                color: white !important;
            }
            </style>
        ''')

        # 頁首
        with ui.header(elevated=True).classes('bg-white text-black items-center justify-between px-4'):
            # Left side: Hamburger menu and Title
            with ui.row().classes('items-center'):
                ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat dense').classes('text-black')
                ui.label(T('management_center')).classes('text-2xl font-bold')
            
            # Right side: Action Icons
            with ui.row().classes('items-center gap-2'):
                with ui.button(icon='language').props('flat round dense color="black" text-black hover:bg-gray-200'):
                    with ui.menu():
                        ui.menu_item(T('language_chinese_traditional'), on_click=lambda: set_language('zh-TW'))
                        ui.menu_item(T('language_chinese_simplified'), on_click=lambda: set_language('zh-CN'))
                        ui.menu_item(T('language_japanese'), on_click=lambda: set_language('ja'))
                        ui.menu_item(T('language_korean'), on_click=lambda: set_language('ko'))
                        ui.menu_item(T('language_english'), on_click=lambda: set_language('en'))
                
                with ui.button(icon='logout', on_click=lambda: (app.storage.user.clear(), ui.navigate.to('/login'))).props('flat round dense color="black" text-black hover:bg-gray-200') as logout_button:
                    ui.tooltip(T('logout'))

        # 左側抽屜導航欄
        with ui.left_drawer().classes('bg-gray-100').props('width=240 bordered') as left_drawer:
            with ui.column().classes('w-full h-full'):
                with ui.element('q-list').props('separator').classes('w-full'):
                    ui.label(T('management_menu')).classes('q-item-label q-item-header p-4 font-bold')
                    
                    menu_items = {
                        'system_dashboard': (T('dashboard'), 'dashboard'),
                        'user_management': (T('user_management'), 'people'),
                        'app_review': (T('app_review'), 'rate_review'),
                        'published_app_management': (T('published_app_management'), 'store'),
                        'system_settings': (T('system_settings'), 'settings'),
                        'user_group_management': (T('user_group_management'), 'group_add'),
                        'permission_management': (T('permission_management'), 'vpn_key'),
                        'prompt_management': (T('prompt_management'), 'text_fields'),
                    }

                    if has_full_access:
                        for key, (title, icon) in menu_items.items():
                            with ui.element('q-item').props(f'clickable v-ripple').on('click', lambda k=key: (content_area.clear(), show_content(k))):
                                with ui.element('q-item-section').props('avatar'):
                                    ui.icon(icon)
                                with ui.element('q-item-section'):
                                    ui.label(title)
                    elif has_review_access:
                        key = 'app_review'
                        title, icon = menu_items[key]
                        with ui.element('q-item').props(f'clickable v-ripple').on('click', lambda k=key: (content_area.clear(), show_content(k))):
                            with ui.element('q-item-section').props('avatar'):
                                ui.icon(icon)
                            with ui.element('q-item-section'):
                                ui.label(title)
                
                # Spacer to push the exit button to the bottom
                ui.space()

                def exit_management_center():
                    user_permissions = app.storage.user.get('permissions', [])
                    if 'develop_app' in user_permissions or 'system_admin' in user_permissions:
                        ui.navigate.to('/my-apps')
                    else:
                        ui.navigate.to('/store')

                # Exit button at the bottom
                with ui.element('q-list').props('separator').classes('w-full'):
                    ui.separator()
                    with ui.element('q-item').props(f'clickable v-ripple').on('click', exit_management_center):
                        with ui.element('q-item-section').props('avatar'):
                            ui.icon('exit_to_app')
                        with ui.element('q-item-section'):
                            ui.label(T('exit_management'))
        
        # 右側主內容區
        content_area = ui.column().classes('w-full p-4 sm:p-6 lg:p-8')

        # --- 內容渲染函式 ---
        def show_content(content_key: str):
            with content_area:
                # Security check: If user doesn't have full access, only allow 'app_review'
                if not has_full_access and content_key != 'app_review':
                    render_app_review()
                    return
                
                if content_key == 'system_dashboard':
                    render_system_dashboard()
                elif content_key == 'user_management':
                    render_user_management()
                elif content_key == 'app_review':
                    render_app_review()
                elif content_key == 'system_settings':
                    render_system_settings()
                elif content_key == 'permission_management':
                    render_permission_management()
                elif content_key == 'user_group_management':
                    render_user_group_management()
                elif content_key == 'prompt_management':
                    render_prompt_management()
                elif content_key == 'published_app_management':
                    render_published_app_management()
                else:
                    # Default view logic is handled at the end of the function
                    if has_full_access:
                        render_system_dashboard()
                    else:
                        render_app_review()
        
        # --- 各管理頁面的渲染邏輯 ---
        def render_system_dashboard():
            ui.label(T('dashboard')).classes('text-2xl font-bold mb-4')

            try:
                stats = database.get_dashboard_stats()
                total_users = stats.get('total_users', 0)
                total_apps = stats.get('total_apps', 0)
                pending_apps = stats.get('pending_apps', 0)
                published_apps = stats.get('published_apps', 0)
                
                # Calculate other apps (e.g., drafts, rejected)
                other_apps = total_apps - pending_apps - published_apps

            except Exception as e:
                ui.notify(T('dashboard_load_error', e=e), color='negative')
                return

            with ui.row().classes('w-full grid grid-cols-1 lg:grid-cols-3 gap-4 items-stretch'):
                # Card for Total Users
                with ui.card().classes('w-full text-center p-6 flex flex-col justify-center items-center'):
                    ui.label(T('active_users')).classes('text-xl font-semibold text-gray-600')
                    ui.label(total_users).classes('text-6xl font-bold mt-2')

                # Chart for App Status Distribution
                with ui.card().classes('w-full lg:col-span-2 p-6'):
                    ui.label(T('app_status_distribution')).classes('text-xl font-semibold text-gray-700 text-center mb-4')
                    with ui.echart({
                        'title': {'text': T('total_apps') + f': {total_apps}', 'left': 'center', 'top': 'top'},
                        'tooltip': {'trigger': 'item'},
                        'legend': {'orient': 'horizontal', 'bottom': 'bottom', 'left': 'center'},
                        'series': [
                            {
                                'name': T('app_status'),
                                'type': 'pie',
                                'radius': '50%',
                                'data': [
                                    {'value': published_apps, 'name': T('published_apps')},
                                    {'value': pending_apps, 'name': T('pending_apps')},
                                    {'value': other_apps, 'name': T('other_apps')}
                                ],
                                'emphasis': {
                                    'itemStyle': {
                                        'shadowBlur': 10,
                                        'shadowOffsetX': 0,
                                        'shadowColor': 'rgba(0, 0, 0, 0.5)'
                                    }
                                }
                            }
                        ]
                    }).classes('w-full h-64'):
                        pass

            with ui.row().classes('w-full grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4'):
                # Card for App Version Trend
                with ui.card().classes('w-full p-6'):
                    ui.label(T('app_version_trend')).classes('text-xl font-semibold text-gray-700 mb-4')
                    version_trends = database.get_version_creation_trends()
                    if version_trends:
                        with ui.echart({
                            'title': {'text': T('versions_created_per_day'), 'left': 'center'},
                            'tooltip': {'trigger': 'axis'},
                            'xAxis': {'type': 'category', 'data': [v['creation_date'] for v in version_trends]},
                            'yAxis': {'type': 'value'},
                            'series': [{'data': [v['version_count'] for v in version_trends], 'type': 'line'}]
                        }).classes('w-full h-64'):
                            pass
                    else:
                        ui.label(T('no_data_available')).classes('text-center text-gray-500')

                # Card for Category Distribution
                with ui.card().classes('w-full p-6'):
                    ui.label(T('published_app_category_distribution')).classes('text-xl font-semibold text-gray-700 mb-4')
                    category_dist = database.get_category_distribution()
                    if category_dist:
                        with ui.echart({
                            'title': {'text': T('published_app_category_distribution'), 'left': 'center'},
                            'tooltip': {'trigger': 'axis'},
                            'xAxis': {'type': 'category', 'data': [c['category_name'] for c in category_dist]},
                            'yAxis': {'type': 'value'},
                            'series': [{'data': [c['app_count'] for c in category_dist], 'type': 'bar'}]
                        }).classes('w-full h-64'):
                            pass
                    else:
                        ui.label(T('no_data_available')).classes('text-center text-gray-500')

        def render_user_management():
            ui.label(T('user_management')).classes('text-2xl font-bold mb-4')


            # --- Table and Columns Definition ---
            columns = [
                {'name': 'id', 'label': T('user_id'), 'field': 'id', 'sortable': True},
                {'name': 'username', 'label': T('username'), 'field': 'username', 'sortable': True},
                {'name': 'status', 'label': T('status'), 'field': 'status'},
                {'name': 'actions', 'label': T('actions'), 'field': 'id'},
            ]
            
            with ui.card().classes('w-full'):
                table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            # --- Data Refresh Logic ---
            def refresh_table():
                try:
                    users = database.get_all_users()
                    rows = []
                    for user in users:
                        user_dict = dict(user)
                        user_dict['status'] = T('active') if user_dict['status'] == 1 else T('inactive')
                        rows.append(user_dict)
                    table.rows = rows
                    table.update()
                except Exception as e:
                    ui.notify(T('user_load_error', e=e), color='negative')

            # --- Dialogs and Event Handlers ---
            with ui.dialog() as user_dialog, ui.card().classes('w-full max-w-md'):
                dialog_title = ui.label(T('add_user')).classes('text-lg font-bold')
                user_id_input = ui.input(T('user_id')).props('readonly').classes('w-full')
                username_input = ui.input(T('username'), validation={T('required_field'): lambda v: bool(v.strip())}).classes('w-full')
                email_input = ui.input(T('email'), validation={T('required_field'): lambda v: '@' in v}).classes('w-full')
                password_input = ui.input(T('password'), password=True).props(f'hint="{T("password_placeholder")}"').classes('w-full')
                status_toggle = ui.toggle({1: T('active'), 0: T('inactive')}, value=1).classes('mt-2')

                def handle_save():
                    if not all([username_input.validate(), email_input.validate()]):
                        return
                    
                    user_id = int(user_id_input.value) if user_id_input.value else None
                    try:
                        if user_id: # Update
                            database.update_user(
                                user_id=user_id,
                                username=username_input.value,
                                email=email_input.value,
                                status=status_toggle.value,
                                password=password_input.value or None
                            )
                            ui.notify(T('user_updated_success', username=username_input.value), type='positive')
                        else: # Create
                            if not password_input.value:
                                ui.notify(T('password_required_for_new_user'), color='negative')
                                return
                            database.create_user(username_input.value, password_input.value, email_input.value)
                            ui.notify(T('user_created_success', username=username_input.value), type='positive')
                        
                        user_dialog.close()
                        refresh_table()
                    except Exception as e:
                        ui.notify(T('save_failed', e=e), color='negative')

                with ui.row().classes('w-full justify-end mt-4'):
                    ui.button(T('save'), on_click=handle_save).classes('bg-black text-white')
                    ui.button(T('cancel'), on_click=user_dialog.close).props('flat').classes('text-black')

            with ui.dialog() as delete_dialog, ui.card():
                ui.label(T('confirm_delete_user_title')).classes('text-lg')
                delete_info = ui.label('')
                with ui.row().classes('w-full justify-end mt-4'):
                    ui.button(T('cancel'), on_click=delete_dialog.close).classes('text-black').props('flat')
                    ui.button(T('confirm_delete'), on_click=lambda: handle_delete()).classes('bg-black text-white')
            
            user_to_delete = {}
            def open_delete_dialog(user_data: dict):
                nonlocal user_to_delete
                user_to_delete = user_data
                delete_info.text = T('deleting_user_info', username=user_data['username'], id=user_data['id'])
                delete_dialog.open()

            async def handle_delete():
                try:
                    database.delete_user(user_to_delete['id'])
                    ui.notify(T('user_deleted', username=user_to_delete['username']), type='positive')
                    delete_dialog.close()
                    refresh_table()
                except Exception as e:
                    ui.notify(T('delete_failed', e=e), color='negative')

            def open_user_dialog(user_id: int | None = None):
                user_data = database.get_user_by_id(user_id) if user_id else None
                user_id_input.value = user_data['id'] if user_data else ''
                username_input.value = user_data['username'] if user_data else ''
                email_input.value = user_data['email'] if user_data else ''
                status_toggle.value = user_data['status'] if user_data else 1
                password_input.value = ''
                
                if user_data:
                    dialog_title.text = T('edit_user')
                    password_input.props(f'hint="{T("password_placeholder")}"')
                else:
                    dialog_title.text = T('add_user')
                    password_input.props(remove='hint')
                
                user_dialog.open()

            # --- Buttons and Final Setup ---
            ui.button(T('add_user'), on_click=lambda: open_user_dialog(), icon='add').classes('mb-4 bg-black text-white')
            
            table.add_slot('body-cell-actions', f'''
                <q-td :props="props">
                    <q-btn flat dense icon="edit" @click="() => $parent.$emit('edit_user', props.row.id)">
                        <q-tooltip>{T('edit')}</q-tooltip>
                    </q-btn>
                    <q-btn flat dense icon="delete" color="negative" @click="() => $parent.$emit('delete_user', props.row)">
                        <q-tooltip>{T('delete')}</q-tooltip>
                    </q-btn>
                </q-td>
            '''.replace('{T(\'edit\')}', T('edit')).replace('{T(\'delete\')}', T('delete')))

            table.on('edit_user', lambda e: open_user_dialog(e.args))
            table.on('delete_user', lambda e: open_delete_dialog(e.args))
            
            refresh_table()

        def render_app_review():
            ui.label(T('app_review')).classes('text-2xl font-bold mb-4')

            columns = [
                {'name': 'app_name', 'label': T('app_name'), 'field': 'app_name', 'sortable': True, 'align': 'left'},
                {'name': 'owner_username', 'label': T('developer'), 'field': 'owner_username', 'sortable': True},
                {'name': 'actions', 'label': T('actions'), 'field': 'id', 'align': 'center'},
            ]
            
            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            def refresh_table():
                try:
                    pending_apps = database.get_pending_applications()
                    table.rows = [dict(row) for row in pending_apps]
                    table.update()
                except Exception as e:
                    ui.notify(T('pending_apps_load_error', e=e), color='negative')

            with ui.dialog() as review_dialog, ui.card().classes('w-full max-w-4xl'):
                with ui.row().classes('w-full justify-between items-center'):
                    dialog_title = ui.label(T('review_app')).classes('text-xl font-bold')
                    ui.button(icon='close', on_click=review_dialog.close).classes('text-black').props('flat dense')
                
                ui.separator()

                with ui.row().classes('w-full p-4 gap-4 overflow-auto h-90'):
                    with ui.column().classes('w-full'):
                        ui.label(T('app_info')).classes('text-lg font-semibold mb-2')
                        info_table_container = ui.html().classes('w-full overflow-auto border rounded p-2 bg-gray-50')
                        
                        ui.label(T('review_actions')).classes('text-lg font-semibold mt-4 mb-2')
                        review_comments = ui.textarea(T('review_comments')).props('filled autogrow').classes('w-full')
                        
                    with ui.column().classes('w-full'):
                        ui.label(T('risk_report')).classes('text-lg font-semibold mb-2')
                        
                        # Button to trigger the report generation
                        report_button = ui.button(T('generate_risk_report'), on_click=lambda: generate_report(current_app_info.get('latest_submitted_version_uuid'))).classes('text-white bg-black')
                        
                        # Area to display the report results
                        report_display_area = ui.html().classes('w-full border rounded p-2 bg-gray-50 overflow-auto')

                ui.separator()
                
                with ui.row().classes('w-full justify-end p-4 gap-2'):
                    reject_button = ui.button(T('reject'), on_click=lambda: handle_decision(False), color='negative')
                    approve_button = ui.button(T('approve'), on_click=lambda: handle_decision(True), color='positive')

            async def handle_decision(is_approved: bool):
                app_id = current_app_info['id']
                version_uuid = current_app_info['latest_submitted_version_uuid']
                reviewer_id = app.storage.user['user_id']
                decision = 1 if is_approved else 2
                comments = review_comments.value

                try:
                    database.add_review(app_id, version_uuid, reviewer_id, decision, comments)
                    ui.notify(T('app_review_decision_success', app_name=current_app_info['app_name'], decision=T('app_approved_text') if is_approved else T('app_rejected_text')),
                              type='positive' if is_approved else 'warning')
                    review_dialog.close()
                    refresh_table()
                except Exception as e:
                    ui.notify(T('review_op_failed', e=e), color='negative')

            current_app_info = {}
            def _render_report_html(data: dict) -> str:
                """Generates a styled HTML string from report data."""
                if not data:
                    return ""

                styles = """
                <style>
                    .report-container { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; padding: 12px; }
                    .report-section { margin-bottom: 16px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
                    .report-section-header { background-color: #f7fafc; padding: 8px 12px; font-weight: 600; border-bottom: 1px solid #e2e8f0; }
                    .report-content { padding: 12px; }
                    .risk-list { list-style-type: none; padding-left: 0; }
                    .risk-item { display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid #edf2f7; }
                    .risk-item:last-child { border-bottom: none; }
                    .risk-level-indicator { width: 10px; height: 10px; border-radius: 50%; margin-right: 10px; }
                    .risk-level-high { background-color: #ef4444; }
                    .risk-level-medium { background-color: #f97316; }
                    .risk-level-low { background-color: #3b82f6; }
                    .category-badge { display: inline-block; background-color: #e5e7eb; color: #4b5563; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 6px; }
                    .description-text { white-space: pre-wrap; word-wrap: break-word; }
                </style>
                """

                # Main container
                html_report = f'{styles}<div class="report-container">'

                # --- Risk Analysis Section ---
                html_report += '<div class="report-section">'
                html_report += f'<div class="report-section-header">{T("risk_analysis")}</div>'
                html_report += '<div class="report-content">'
                
                risk_map = {
                    "critical_risks": (T("high_risk"), "risk-level-high"),
                    "medium_risks": (T("medium_risk"), "risk-level-medium"),
                    "low_risks": (T("low_risk"), "risk-level-low")
                }

                has_risks = any(data.get(key) for key in risk_map)

                if has_risks:
                    html_report += '<ul class="risk-list">'
                    for key, (level_text, level_class) in risk_map.items():
                        risks = sorted(data.get(key, []))
                        if risks:
                            for item in risks:
                                html_report += f'<li class="risk-item"><span class="risk-level-indicator {level_class}"></span>[{level_text}] {item}</li>'
                    html_report += '</ul>'
                else:
                    html_report += f'<p>{T("no_risks_found")}</p>'
                    
                html_report += '</div></div>' # Close risk content and section

                # --- Other Sections ---
                sections = {
                    T("suggested_categories"): ("categories", "category-badge"),
                    T("functional_description"): ("functional_description", "description-text"),
                    T("operating_instructions"): ("operating_instructions", "description-text")
                }

                for title, (key, content_class) in sections.items():
                    content = data.get(key)
                    if content:
                        html_report += '<div class="report-section">'
                        html_report += f'<div class="report-section-header">{title}</div>'
                        html_report += '<div class="report-content">'
                        if isinstance(content, list):
                            html_report += ''.join(f'<span class="{content_class}">{item}</span>' for item in content)
                        else:
                            html_report += f'<p class="{content_class}">{content}</p>'
                        html_report += '</div></div>'

                html_report += '</div>' # Close container
                return html_report

            def open_review_dialog(app_data: dict):
                nonlocal current_app_info
                
                try:
                    full_app_data = database.get_application_by_session(app_data['session_id'])
                    if not full_app_data:
                        ui.notify(T('app_details_not_found'), color='negative')
                        return
                    
                    current_app_info = dict(full_app_data)
                    version_uuid = current_app_info.get('latest_submitted_version_uuid')

                    if not version_uuid:
                        ui.notify(T('app_missing_submitted_version'), color='negative')
                        return
                        
                    dialog_title.text = f"{T('review_app')}: {current_app_info['app_name']}"
                    
                    # Populate the info table
                    info_table_container.content = f"""
                        <table class="w-full text-sm text-left text-gray-500 border">
                            <tbody class="bg-white">
                                <tr class="border-b">
                                    <th scope="row" class="py-2 px-4 font-medium text-gray-900 whitespace-nowrap bg-gray-50 w-1/4">{T('app_name')}</th>
                                    <td class="py-2 px-4">{current_app_info['app_name']}</td>
                                </tr>
                                <tr class="border-b">
                                    <th scope="row" class="py-2 px-4 font-medium text-gray-900 whitespace-nowrap bg-gray-50">{T('developer')}</th>
                                    <td class="py-2 px-4">{app_data['owner_username']}</td>
                                </tr>
                                <tr class="border-b">
                                    <th scope="row" class="py-2 px-4 font-medium text-gray-900 whitespace-nowrap bg-gray-50">{T('submitted_at')}</th>
                                    <td class="py-2 px-4">{app_data['submitted_at']}</td>
                                </tr>
                            </tbody>
                        </table>
                    """
                    review_comments.value = ''
                    
                    # Check for existing report
                    existing_report = database.get_report_data_by_version(version_uuid, T.lang)
                    if existing_report:
                        report_display_area.content = _render_report_html(existing_report)
                        report_button.text = T('regenerate_report')
                    else:
                        report_display_area.content = f'<p class="text-gray-400">{T("click_to_generate_report")}</p>'
                        report_button.text = T('generate_risk_report')
                    
                    # 根據設定決定是否禁用批准按鈕
                    require_report = database.get_setting('REQUIRE_RISK_REPORT_BEFORE_APPROVAL') == 'true'
                    if require_report and not existing_report:
                        approve_button.disable()
                        reject_button.disable()
                        with approve_button:
                            ui.tooltip(T('must_generate_report_to_approve'))
                        with reject_button:
                            ui.tooltip(T('must_generate_report_to_approve'))
                    else:
                        approve_button.enable()
                        reject_button.enable()

                    report_button.enable()
                    review_dialog.open()

                except Exception as e:
                    ui.notify(T('review_dialog_open_error', e=e), color='negative')

            async def generate_report(version_uuid: str):
                if not version_uuid:
                    ui.notify(T('missing_version_info_for_report'), color='negative')
                    return
                
                report_button.disable()
                report_display_area.content = f'<p class="text-blue-500">{T("generating_report_in_progress")}</p>'
                
                try:
                    # Call the internal logic function directly
                    data = await _internal_generate_and_store_report(version_uuid, T.lang)
                    report_display_area.content = _render_report_html(data)
                    ui.notify(T('report_generated_success'), type='positive')
                    
                    # 如果設定要求報告，則啟用批准按鈕
                    if database.get_setting('REQUIRE_RISK_REPORT_BEFORE_APPROVAL') == 'true':
                        approve_button.enable()
                        reject_button.enable()

                except Exception as e:
                    error_message = T('report_generation_error', e=e)
                    logging.error(f"Client-side error during report generation for {version_uuid}: {e}", exc_info=True)
                    report_display_area.content = f'<p class="text-red-500">{error_message}</p>'
                    ui.notify(error_message, color='negative')
                finally:
                    report_button.enable()

            table.add_slot('body-cell-actions', f'''
                <q-td :props="props">
                    <q-btn flat dense icon="visibility" @click="() => $parent.$emit('review_app', props.row)">
                        <q-tooltip>{T('review')}</q-tooltip>
                    </q-btn>
                </q-td>
            '''.replace('{T(\'review\')}', T('review')))

            table.on('review_app', lambda e: open_review_dialog(e.args))

            refresh_table()

        def render_system_settings():
            ui.label(T('system_settings')).classes('text-2xl font-bold mb-4')

            # --- AI Model Management ---
            ui.label(T('ai_model_management')).classes('text-xl font-bold mt-6 mb-2')
            
            columns = [
                {'name': 'name', 'label': T('model_name'), 'field': 'name', 'sortable': True, 'align': 'left'},
                {'name': 'model_name_col', 'label': T('technical_model_name'), 'field': 'model_name', 'align': 'left'},
                {'name': 'is_code_generation_model', 'label': T('code_generation_model'), 'field': 'is_code_generation_model', 'align': 'center'},
                {'name': 'is_preview_generation_model', 'label': T('preview_generation_model'), 'field': 'is_preview_generation_model', 'align': 'center'},
                {'name': 'is_report_generation_model', 'label': T('report_generation_model'), 'field': 'is_report_generation_model', 'align': 'center'},
                {'name': 'actions', 'label': T('actions'), 'field': 'id', 'align': 'center'},
            ]

            with ui.card().classes('w-full'):
                with ui.row().classes('w-full justify-between items-center p-2'):
                    ui.label(T('configured_ai_models')).classes('text-lg font-semibold')
                    ui.button(T('add_model'), on_click=lambda: open_model_dialog(None), icon='add').classes('bg-black text-white')
                
                model_table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            def refresh_model_table():
                try:
                    models_from_db = database.get_all_ai_models()
                    processed_models = []
                    for model in models_from_db:
                        # Ensure model is a mutable dictionary
                        model_dict = dict(model)
                        # Convert integer (0/1) values to booleans for the toggle component
                        model_dict['is_code_generation_model'] = bool(model_dict.get('is_code_generation_model'))
                        model_dict['is_preview_generation_model'] = bool(model_dict.get('is_preview_generation_model'))
                        model_dict['is_report_generation_model'] = bool(model_dict.get('is_report_generation_model'))
                        processed_models.append(model_dict)
                    
                    model_table.rows = processed_models
                    model_table.update()
                except Exception as e:
                    ui.notify(T('ai_model_load_error', e=e), color='negative')

            async def handle_task_toggle(is_enabled: bool, model_id: int, task_type: str):
                try:
                    database.set_active_model_for_task(model_id, task_type, is_enabled)
                    ui.notify(T('model_status_updated_success'), type='positive')
                    # Refresh is important to ensure UI consistency, especially since one toggle can affect others.
                    refresh_model_table()
                except Exception as ex:
                    ui.notify(T('model_status_update_error', e=ex), color='negative')
                    # If there was an error, refresh the table to revert the toggle to the actual DB state.
                    ui.timer(0.1, refresh_model_table, once=True)

            model_table.add_slot('body-cell-is_code_generation_model', '''
                <q-td :props="props">
                    <q-toggle :model-value="props.row.is_code_generation_model" @update:model-value="v => $parent.$emit('toggle', { value: v, id: props.row.id, type: 'code_generation' })" />
                </q-td>
            ''')
            model_table.add_slot('body-cell-is_preview_generation_model', '''
                <q-td :props="props">
                    <q-toggle :model-value="props.row.is_preview_generation_model" @update:model-value="v => $parent.$emit('toggle', { value: v, id: props.row.id, type: 'preview_generation' })" />
                </q-td>
            ''')
            model_table.add_slot('body-cell-is_report_generation_model', '''
                <q-td :props="props">
                    <q-toggle :model-value="props.row.is_report_generation_model" @update:model-value="v => $parent.$emit('toggle', { value: v, id: props.row.id, type: 'report_generation' })" />
                </q-td>
            ''')
            model_table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn flat dense icon="edit" @click="() => $parent.$emit('edit_model', props.row)" />
                    <q-btn flat dense icon="delete" color="negative" @click="() => $parent.$emit('delete_model', props.row)" />
                </q-td>
            ''')

            model_table.on('toggle', lambda e: handle_task_toggle(e.args['value'], e.args['id'], e.args['type']))

            with ui.dialog() as model_dialog, ui.card().classes('w-full max-w-lg'):
                dialog_title = ui.label(T('add_model')).classes('text-lg font-bold')
                model_id_input = ui.input().props('readonly').style('display: none')
                name_input = ui.input(T('custom_model_name'), validation={T('required_field'): bool}).classes('w-full')
                api_key_input = ui.input(T('api_key'), password=True, validation={T('required_field'): bool}).classes('w-full')
                model_name_input = ui.input(T('technical_model_name'), validation={T('required_field'): bool}).classes('w-full')
                endpoint_url_input = ui.input(T('endpoint_url')).classes('w-full')

                def handle_save_model():
                    if not all(v.validate() for v in [name_input, api_key_input, model_name_input]):
                        return
                    try:
                        model_id = int(model_id_input.value) if model_id_input.value else None
                        if model_id:
                            database.update_ai_model(model_id, name_input.value, api_key_input.value, model_name_input.value, endpoint_url_input.value)
                            ui.notify(T('model_updated_success'), type='positive')
                        else:
                            database.create_ai_model(name_input.value, api_key_input.value, model_name_input.value, endpoint_url_input.value)
                            ui.notify(T('model_created_success'), type='positive')
                        model_dialog.close()
                        refresh_model_table()
                    except Exception as e:
                        ui.notify(T('model_save_error', e=e), color='negative')

                with ui.row().classes('w-full justify-end mt-4 gap-2'):
                    ui.button(T('save'), on_click=handle_save_model).classes('bg-black text-white')
                    ui.button(T('cancel'), on_click=model_dialog.close).props('flat')

            def open_model_dialog(model_data: dict | None):
                if model_data:
                    dialog_title.text = T('edit_model')
                    model_id_input.value = model_data['id']
                    name_input.value = model_data['name']
                    api_key_input.value = model_data['api_key']
                    model_name_input.value = model_data['model_name']
                    endpoint_url_input.value = model_data['endpoint_url']
                else:
                    dialog_title.text = T('add_model')
                    model_id_input.value = ''
                    name_input.value = ''
                    api_key_input.value = ''
                    model_name_input.value = ''
                    endpoint_url_input.value = ''
                model_dialog.open()

            with ui.dialog() as delete_dialog, ui.card():
                ui.label(T('confirm_delete_model_title')).classes('text-lg')
                delete_info = ui.label('')
                
                def handle_delete():
                    try:
                        database.delete_ai_model(model_to_delete['id'])
                        ui.notify(T('model_deleted_success'), type='positive')
                        delete_dialog.close()
                        refresh_model_table()
                    except Exception as e:
                        ui.notify(T('model_delete_error', e=e), color='negative')

                with ui.row().classes('w-full justify-end mt-4 gap-2'):
                     ui.button(T('cancel'), on_click=delete_dialog.close).props('flat')
                     ui.button(T('confirm_delete'), on_click=handle_delete).classes('bg-black text-white')

            model_to_delete = {}
            def open_delete_dialog(model_data: dict):
                nonlocal model_to_delete
                model_to_delete = model_data
                delete_info.text = T('deleting_model_info', name=model_data['name'])
                delete_dialog.open()

            model_table.on('edit_model', lambda e: open_model_dialog(e.args))
            model_table.on('delete_model', lambda e: open_delete_dialog(e.args))
            
            refresh_model_table()

            # --- General Settings ---
            ui.label(T('general_settings')).classes('text-xl font-bold mt-8 mb-2')
            with ui.card().classes('w-full p-4'):
                ui.label(T('app_publish_settings')).classes('text-lg font-semibold')
                auto_publish_value = database.get_setting('AUTO_PUBLISH_ON_APPROVAL') == 'true'
                auto_publish_switch = ui.switch(text=T('auto_publish_on_approval'), value=auto_publish_value)
                
                require_report_value = database.get_setting('REQUIRE_RISK_REPORT_BEFORE_APPROVAL') == 'true'
                require_report_switch = ui.switch(text=T('require_risk_report_before_approval'), value=require_report_value)

                def handle_general_settings_save():
                    try:
                        database.update_setting('AUTO_PUBLISH_ON_APPROVAL', str(auto_publish_switch.value).lower())
                        database.update_setting('REQUIRE_RISK_REPORT_BEFORE_APPROVAL', str(require_report_switch.value).lower())
                        ui.notify(T('settings_saved_success'), type='positive')
                    except Exception as e:
                        ui.notify(T('settings_save_error', e=e), color='negative')
                
                ui.button(T('save_settings'), on_click=handle_general_settings_save).classes('mt-4 bg-black text-white')

        def render_permission_management():
            ui.label(T('permission_management')).classes('text-2xl font-bold mb-4')

            state = {'selected_group': None, 'auth_checkboxes': {}}

            def update_auth_panel(group_data: dict | None):
                state['selected_group'] = group_data
                auth_panel.clear()
                
                with auth_panel:
                    if not group_data:
                        with ui.column().classes('w-full h-full items-center justify-center text-gray-500'):
                            ui.icon('vpn_key', size='xl')
                            ui.label(T('select_group_prompt'))
                        return

                    try:
                        all_authorities = database.get_all_authorities()
                        group_authorities = database.get_group_authorities(group_data['id'])
                        state['auth_checkboxes'] = {}

                        with ui.card().classes('w-full'):
                            ui.label(T('editing_group', name=group_data['name'])).classes('text-lg font-semibold')
                            ui.separator()
                            with ui.scroll_area().classes('h-96'):
                                for auth in all_authorities:
                                    has_auth = auth['id'] in group_authorities
                                    cb = ui.checkbox(f"{auth['name']} ({auth.get('description', T('no_description'))})", value=has_auth).classes('custom-checkbox')
                                    state['auth_checkboxes'][auth['id']] = cb
                            
                            ui.separator().classes('my-4')
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.button(T('manage_permissions'), on_click=lambda: manage_authorities_dialog.open(), icon='settings').classes('text-black opacity-0').props('flat dense')
                                ui.button(T('save_changes_permissions'), on_click=save_group_authorities).classes('text-white bg-black')

                    except Exception as e:
                        ui.notify(T('permission_load_error', e=e), color='negative')

            def save_group_authorities():
                group = state['selected_group']
                if not group:
                    ui.notify(T('no_group_selected'), color='negative')
                    return
                
                selected_auth_ids = [aid for aid, cb in state['auth_checkboxes'].items() if cb.value]
                
                try:
                    database.update_group_authorities(group['id'], selected_auth_ids)
                    ui.notify(T('group_permissions_updated_success', name=group['name']), type='positive')
                except Exception as e:
                    ui.notify(T('save_failed', e=e), color='negative')

            # Responsive grid layout
            with ui.row().classes('w-full grid grid-cols-1 lg:grid-cols-3 gap-4'):
                # Left column for group list
                with ui.column().classes('lg:col-span-1'):
                    with ui.card().classes('w-full'):
                        with ui.row().classes('w-full justify-between items-center no-wrap p-2'):
                            ui.label(T('group_list')).classes('text-xl font-bold')
                            ui.button(T('add_group'), on_click=lambda: open_group_dialog(), icon='add').classes('text-black').props('flat dense')
                        ui.separator()
                        group_list_container = ui.column().classes('w-full p-2')

                # Right column for auth panel
                with ui.column().classes('lg:col-span-2'):
                    auth_panel = ui.column().classes('w-full')

            def refresh_group_list():
                try:
                    groups = database.get_all_groups()
                    group_list_container.clear()
                    with group_list_container:
                        if not groups:
                            with ui.column().classes('w-full h-full items-center justify-center text-gray-400'):
                                ui.icon('group_add', size='lg')
                                ui.label(T('no_groups_yet'))
                        else:
                            with ui.list().props('bordered separator').classes('w-full'):
                                for group in groups:
                                    with ui.item().props('clickable').on('click', lambda g=group: update_auth_panel(g)):
                                        with ui.item_section():
                                            ui.item_label(group.get('name', 'N/A'))
                                            ui.item_label(group.get('description', '')).props('caption')
                                        with ui.item_section().props('side'):
                                            ui.button(icon='delete', on_click=lambda g=group: confirm_delete_group(g)).props('flat dense').classes('text-black').on('click.stop')
                except Exception as e:
                    logging.exception("載入群組列表時發生錯誤")
                    ui.notify(T('group_list_load_error', e=e), color='negative')

            with ui.dialog() as group_dialog, ui.card().classes('w-full max-w-lg'):
                ui.label(T('add_group')).classes('text-black')
                group_name_input = ui.input(T('group_name'), validation={T('required_field'): lambda v: bool(v.strip())}).classes('w-full')
                group_desc_input = ui.input(T('description')).classes('w-full')
                
                def handle_save_group():
                    if not group_name_input.validate(): return
                    try:
                        database.create_group(group_name_input.value, group_desc_input.value)
                        ui.notify(T('group_created_success'), type='positive')
                        group_dialog.close()
                        refresh_group_list()
                    except Exception as e:
                        ui.notify(T('group_save_error', e=e), color='negative')

                with ui.row().classes('w-full justify-end'):
                    ui.button(T('save'), on_click=handle_save_group).classes('text-white bg-black')
                    ui.button(T('cancel'), on_click=group_dialog.close).props('flat').classes('text-black')

            def open_group_dialog():
                group_name_input.value = ''
                group_desc_input.value = ''
                group_dialog.open()

            with ui.dialog() as manage_authorities_dialog, ui.card().classes('w-full max-w-lg'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label(T('manage_all_permissions')).classes('text-lg font-semibold')
                    ui.button(T('add_permission'), on_click=lambda: open_auth_dialog(None), icon='add').classes('text-black').props('flat dense')
                
                auth_table_container = ui.column().classes('w-full')

                def refresh_authorities_table():
                    auth_table_container.clear()
                    with auth_table_container:
                        all_authorities = database.get_all_authorities()
                        for auth in all_authorities:
                            with ui.row().classes('w-full items-center justify-between hover:bg-gray-100 p-1 rounded'):
                                ui.label(f"{auth['name']} ({auth.get('description', T('no_description'))})").classes('flex-grow')
                                with ui.row():
                                    ui.button(icon='delete', on_click=lambda a=auth: confirm_delete_auth(a)).props('flat dense').classes('text-black')
                
                refresh_authorities_table()

            with ui.dialog() as auth_dialog, ui.card():
                auth_dialog_title = ui.label(T('add_permission'))
                auth_name_input = ui.input(T('permission_name'), validation={T('required_field'): lambda v: bool(v.strip())})
                auth_desc_input = ui.textarea(T('description'))

                def handle_save_auth():
                    if not auth_name_input.validate(): return
                    try:
                        database.create_authority(auth_name_input.value, auth_desc_input.value)
                        ui.notify(T('permission_created_success'), type='positive')
                        auth_dialog.close()
                        refresh_authorities_table()
                        # Also refresh the main panel if a group is selected
                        if state['selected_group']:
                            update_auth_panel(state['selected_group'])
                    except Exception as e:
                        ui.notify(T('permission_save_error', e=e), color='negative')

                with ui.row().classes('w-full justify-end'):
                    ui.button(T('save'), on_click=handle_save_auth).classes('text-white bg-black')
                    ui.button(T('cancel'), on_click=auth_dialog.close).props('flat').classes('text-black')

            def open_auth_dialog(auth_data=None):
                # This is simplified for creation only for now
                auth_name_input.value = ''
                auth_desc_input.value = ''
                auth_dialog.open()

            dialog_state = {'delete_callback': None}
            with ui.dialog() as delete_dialog, ui.card():
                delete_title = ui.label().classes('text-lg mb-4')
                def execute_delete():
                    callback = dialog_state.get('delete_callback')
                    if callable(callback):
                        callback()
                    delete_dialog.close()
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button(T('cancel'), on_click=delete_dialog.close).classes('text-black').props('flat')
                    ui.button(T('confirm_delete'), on_click=execute_delete).classes('bg-black text-white')

            def handle_delete_group(group_id):
                try:
                    database.delete_group(group_id)
                    ui.notify(T('group_deleted_success'), type='positive')
                    refresh_group_list()
                    update_auth_panel(None)
                except Exception as e:
                    ui.notify(T('group_delete_error', e=e), color='negative')

            def confirm_delete_group(group_data):
                delete_title.text = T('confirm_delete_group_title', name=group_data['name'])
                dialog_state['delete_callback'] = lambda: handle_delete_group(group_data['id'])
                delete_dialog.open()

            def handle_delete_auth(auth_id):
                try:
                    database.delete_authority(auth_id)
                    ui.notify(T('permission_deleted_success'), type='positive')
                    refresh_authorities_table()
                    if state['selected_group']:
                        update_auth_panel(state['selected_group'])
                except Exception as e:
                    ui.notify(T('permission_delete_error', e=e), color='negative')

            def confirm_delete_auth(auth_data):
                delete_title.text = T('confirm_delete_permission_title', name=auth_data['name'])
                dialog_state['delete_callback'] = lambda: handle_delete_auth(auth_data['id'])
                delete_dialog.open()

            refresh_group_list()
            update_auth_panel(None)

        def render_user_group_management():
            ui.label(T('user_group_management')).classes('text-2xl font-bold mb-4')
            
            state = {'selected_user': None, 'group_checkboxes': {}}

            def update_group_panel(user_data: dict | None):
                state['selected_user'] = user_data
                group_panel.clear()
                
                with group_panel:
                    if not user_data:
                        with ui.column().classes('w-full h-full items-center justify-center text-gray-500'):
                            ui.icon('person_outline', size='xl')
                            ui.label(T('select_user_prompt'))
                        return

                    try:
                        all_groups = database.get_all_groups()
                        user_groups = database.get_user_groups(user_data['id'])
                        state['group_checkboxes'] = {}

                        with ui.card().classes('w-full'):
                            ui.label(T('editing_user', username=user_data['username'])).classes('text-lg font-semibold')
                            ui.separator()
                            with ui.scroll_area().classes('h-96'):
                                for group in all_groups:
                                    is_member = group['id'] in user_groups
                                    cb = ui.checkbox(f"{group['name']} ({group.get('description', T('no_description'))})", value=is_member).classes('custom-checkbox')
                                    state['group_checkboxes'][group['id']] = cb
                            
                            ui.separator().classes('my-4')
                            with ui.row().classes('w-full justify-end'):
                                ui.button(T('save_changes_permissions'), on_click=save_user_groups).classes('text-white bg-black')

                    except Exception as e:
                        ui.notify(T('group_load_error', e=e), color='negative')

            def save_user_groups():
                user = state['selected_user']
                if not user:
                    ui.notify(T('no_user_selected'), color='negative')
                    return
                
                selected_group_ids = [gid for gid, cb in state['group_checkboxes'].items() if cb.value]
                
                try:
                    database.update_user_groups(user['id'], selected_group_ids)
                    ui.notify(T('user_groups_updated_success', username=user['username']), type='positive')
                except Exception as e:
                    ui.notify(T('save_failed', e=e), color='negative')

            # Responsive grid layout
            with ui.row().classes('w-full grid grid-cols-1 lg:grid-cols-3 gap-4'):
                # Left column for user list
                with ui.column().classes('lg:col-span-1'):
                     with ui.card().classes('w-full'):
                        ui.label(T('user_list')).classes('text-xl font-bold p-4 mb-2')
                        ui.separator()
                        user_list_container = ui.column().classes('w-full p-2')

                # Right column for group panel
                with ui.column().classes('lg:col-span-2'):
                    group_panel = ui.column().classes('w-full')

            def refresh_user_list():
                try:
                    users = database.get_all_users()
                    user_list_container.clear()
                    with user_list_container:
                        if not users:
                            with ui.column().classes('w-full h-full items-center justify-center text-gray-400'):
                                ui.icon('people_outline', size='lg')
                                ui.label(T('no_users_yet'))
                                ui.button(T('go_add_user'), on_click=lambda: (content_area.clear(), show_content('user_management'))).props('flat color=primary')
                        else:
                            with ui.list().props('bordered separator').classes('w-full'):
                                for user in users:
                                    with ui.item().props('clickable').on('click', lambda u=dict(user): update_group_panel(u)):
                                        with ui.item_section():
                                            ui.item_label(user.get('username', 'N/A'))
                                            ui.item_label(user.get('email', '')).props('caption')
                except Exception:
                    logging.exception("載入使用者列表時發生錯誤")
                    ui.notify(T('user_list_load_error'), color='negative')

            # 初次加載後，設定一個短延遲再次刷新，以確保能獲取到最新的使用者資料
            refresh_user_list()
            
            update_group_panel(None) # Initial state

        def render_prompt_management():
            ui.label(T('prompt_management')).classes('text-2xl font-bold mb-4')
            
            try:
                prompts = database.get_all_prompts()
                inputs = {}
                

                def handle_save(name):
                    try:
                        for input_name, textarea in inputs.items():
                            if input_name == name:
                                database.update_prompt(name, textarea.value)
                        ui.notify(T('prompts_saved_success'), type='positive')
                    except Exception as e:
                        ui.notify(T('prompt_save_error', e=e), color='negative')

                for prompt in prompts:
                    with ui.card().classes('w-full p-6'):
                        name = prompt['name']
                        ui.label(name).classes('text-lg font-semibold text-gray-700 mb-2')
                        inputs[name] = ui.textarea(value=prompt['content']).props('filled autogrow').classes('w-full')
                        ui.button(T('save_prompts'), on_click= lambda n=name:(handle_save(n))).classes('text-white bg-black self-end')

            except Exception as e:
                ui.notify(T('prompt_load_error', e=e), color='negative')

        def render_published_app_management():
            ui.label(T('published_app_management')).classes('text-2xl font-bold mb-4')

            columns = [
                {'name': 'app_name', 'label': T('app_name'), 'field': 'app_name', 'sortable': True, 'align': 'left'},
                {'name': 'owner_username', 'label': T('developer'), 'field': 'owner_username', 'sortable': True},
                {'name': 'published_at', 'label': T('published_at'), 'field': 'published_at', 'sortable': True},
                {'name': 'actions', 'label': T('actions'), 'field': 'id', 'align': 'center'},
            ]
            
            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            def refresh_table():
                try:
                    published_apps = database.get_published_applications()
                    table.rows = published_apps
                    table.update()
                except Exception as e:
                    ui.notify(f"Error loading published apps: {e}", color='negative')

            with ui.dialog() as unpublish_dialog, ui.card():
                ui.label(T('confirm_unpublish_app_title')).classes('text-lg')
                unpublish_info = ui.label('')
                
                async def handle_unpublish():
                    try:
                        database.archive_application(app_to_unpublish['session_id'], as_admin=True)
                        ui.notify(T('app_unpublished_success_admin', name=app_to_unpublish['app_name']), type='positive')
                        unpublish_dialog.close()
                        refresh_table()
                    except Exception as e:
                        ui.notify(T('unpublish_failed', e=e), color='negative')

                with ui.row().classes('w-full justify-end mt-4'):
                    ui.button(T('cancel'), on_click=unpublish_dialog.close).props('flat')
                    ui.button(T('unpublish_app'), on_click=handle_unpublish, color='negative')

            app_to_unpublish = {}
            def open_unpublish_dialog(app_data: dict):
                nonlocal app_to_unpublish
                app_to_unpublish = app_data
                unpublish_info.text = T('unpublishing_app_info', name=app_data['app_name'])
                unpublish_dialog.open()

            table.add_slot('body-cell-actions', f'''
                <q-td :props="props">
                    <q-btn flat dense icon="unpublished" color="negative" @click="() => $parent.$emit('unpublish_app', props.row)">
                        <q-tooltip>{T('unpublish_app')}</q-tooltip>
                    </q-btn>
                </q-td>
            '''.replace('{T(\'unpublish_app\')}', T('unpublish_app')))

            table.on('unpublish_app', lambda e: open_unpublish_dialog(e.args))

            refresh_table()

        # 初始顯示儀表板
        if has_full_access:
            show_content('system_dashboard')
        elif has_review_access:
            show_content('app_review')
